from datetime import date, timedelta
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import Base, SessionLocal, engine, get_db
from app.models import Appointment, Client, Service, User
from app.n8n import send_appointment_to_n8n
from app.schemas import (
    AppointmentCreate,
    AppointmentOut,
    AppointmentStatusUpdate,
    AppointmentUpdate,
    ClientCreate,
    ClientOut,
    ClientUpdate,
    DashboardOut,
    LoginRequest,
    ServiceOut,
    TokenResponse,
)
from app.security import create_access_token, get_current_user, hash_password, verify_password

app = FastAPI(
    title="Barbearia Vintage API",
    description="API do case técnico Insper Jr. Tech.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == settings.admin_email))
        if not user:
            db.add(User(name="Administrador", email=settings.admin_email, password_hash=hash_password(settings.admin_password)))

        existing_services = db.scalars(select(Service)).all()
        if not existing_services:
            db.add_all(
                [
                    Service(name="Corte", duration_minutes=30, price=50),
                    Service(name="Barba", duration_minutes=30, price=35),
                    Service(name="Corte + Barba", duration_minutes=60, price=75),
                ]
            )
        db.commit()
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="E-mail ou senha inválidos.")
    return TokenResponse(access_token=create_access_token(user.id))


@app.get("/clients", response_model=list[ClientOut])
def list_clients(
    search: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(Client).order_by(Client.name)
    if search:
        stmt = stmt.where(func.lower(Client.name).contains(search.lower()))
    return db.scalars(stmt).all()


@app.post("/clients", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
def create_client(payload: ClientCreate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    client = Client(**payload.model_dump())
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


@app.put("/clients/{client_id}", response_model=ClientOut)
def update_client(client_id: int, payload: ClientUpdate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    for key, value in payload.model_dump().items():
        setattr(client, key, value)
    db.commit()
    db.refresh(client)
    return client


@app.delete("/clients/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_client(client_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    has_appointments = db.scalar(select(func.count(Appointment.id)).where(Appointment.client_id == client_id))
    if has_appointments:
        raise HTTPException(status_code=409, detail="Não é possível remover um cliente que possui agendamentos.")
    db.delete(client)
    db.commit()


@app.get("/services", response_model=list[ServiceOut])
def list_services(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(Service).order_by(Service.name)).all()


def _appointment_query():
    return select(Appointment).options(joinedload(Appointment.client), joinedload(Appointment.service))


def _validate_relations(payload, db: Session):
    if not db.get(Client, payload.client_id):
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    if not db.get(Service, payload.service_id):
        raise HTTPException(status_code=404, detail="Serviço não encontrado.")


def _ensure_slot_available(db: Session, appointment_date, start_time, ignore_id: int | None = None):
    stmt = select(Appointment).where(
        Appointment.date == appointment_date,
        Appointment.start_time == start_time,
        Appointment.status != "cancelled",
    )
    if ignore_id:
        stmt = stmt.where(Appointment.id != ignore_id)
    if db.scalar(stmt):
        raise HTTPException(status_code=409, detail="Este horário já possui um agendamento.")


@app.get("/appointments", response_model=list[AppointmentOut])
def list_appointments(
    appointment_date: date | None = Query(default=None, alias="date"),
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = _appointment_query().order_by(Appointment.date, Appointment.start_time)
    if appointment_date:
        stmt = stmt.where(Appointment.date == appointment_date)
    if status_filter:
        stmt = stmt.where(Appointment.status == status_filter)
    return db.scalars(stmt).unique().all()


@app.post("/appointments", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
async def create_appointment(
    payload: AppointmentCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    _validate_relations(payload, db)
    _ensure_slot_available(db, payload.date, payload.start_time)

    appointment = Appointment(**payload.model_dump())
    db.add(appointment)
    db.commit()

    appointment = db.scalar(_appointment_query().where(Appointment.id == appointment.id))
    background_tasks.add_task(send_appointment_to_n8n, appointment)
    return appointment


@app.put("/appointments/{appointment_id}", response_model=AppointmentOut)
def update_appointment(
    appointment_id: int,
    payload: AppointmentUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    appointment = db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado.")
    _validate_relations(payload, db)
    _ensure_slot_available(db, payload.date, payload.start_time, ignore_id=appointment_id)

    for key, value in payload.model_dump().items():
        setattr(appointment, key, value)
    db.commit()
    return db.scalar(_appointment_query().where(Appointment.id == appointment_id))


@app.patch("/appointments/{appointment_id}/status", response_model=AppointmentOut)
def update_appointment_status(
    appointment_id: int,
    payload: AppointmentStatusUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    appointment = db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado.")
    appointment.status = payload.status
    db.commit()
    return db.scalar(_appointment_query().where(Appointment.id == appointment_id))


@app.delete("/appointments/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_appointment(appointment_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    appointment = db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado.")
    db.delete(appointment)
    db.commit()


@app.get("/dashboard", response_model=DashboardOut)
def dashboard(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    def count_for(status_name: str | None = None):
        stmt = select(func.count(Appointment.id)).where(Appointment.date == today)
        if status_name:
            stmt = stmt.where(Appointment.status == status_name)
        return db.scalar(stmt) or 0

    appointments_this_week = db.scalar(
        select(func.count(Appointment.id)).where(Appointment.date.between(week_start, week_end))
    ) or 0

    popular = db.execute(
        select(Service.name, func.count(Appointment.id).label("qty"))
        .join(Appointment, Appointment.service_id == Service.id)
        .where(Appointment.status != "cancelled")
        .group_by(Service.name)
        .order_by(func.count(Appointment.id).desc())
        .limit(1)
    ).first()

    return DashboardOut(
        appointments_today=count_for(),
        completed_today=count_for("completed"),
        cancelled_today=count_for("cancelled"),
        no_show_today=count_for("no_show"),
        appointments_this_week=appointments_this_week,
        most_popular_service=popular[0] if popular else None,
    )
