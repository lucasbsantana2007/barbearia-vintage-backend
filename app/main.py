from datetime import date, timedelta
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import Base, SessionLocal, engine, get_db
from app.models import Appointment, Client, Expense, Service, User
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
    ExpenseCreate,
    ExpenseOut,
    ExpenseUpdate,
    FinancePasscodeRequest,
    LoginRequest,
    ServiceOut,
    TokenResponse,
)
from app.security import create_access_token, get_current_user, hash_password, verify_password

tags_metadata = [
    {
        "name": "Autenticação",
        "description": "Login e emissão de token JWT para acesso às rotas protegidas.",
    },
    {
        "name": "Clientes",
        "description": "Cadastro, consulta, atualização e remoção de clientes da barbearia.",
    },
    {
        "name": "Serviços",
        "description": "Consulta dos serviços oferecidos pela barbearia (corte, barba, etc.).",
    },
    {
        "name": "Agendamentos",
        "description": "Criação, consulta, atualização e cancelamento de agendamentos, incluindo o controle de conflito de horários.",
    },
    {
        "name": "Dashboard",
        "description": "Indicadores e métricas operacionais da barbearia (agendamentos do dia, da semana e serviço mais popular).",
    },
    {
        "name": "Financeiro",
        "description": "Cadastro e consulta de despesas da barbearia, usadas no cálculo do faturamento e lucro mensal.",
    },
    {
        "name": "Sistema",
        "description": "Rotas utilitárias de infraestrutura, como verificação de saúde da API.",
    },
]

app = FastAPI(
    title="Barbearia Vintage API",
    description=(
        "API REST do sistema de gestão da **Barbearia Vintage**, desenvolvida com FastAPI.\n\n"
        "Permite o gerenciamento completo de clientes, serviços e agendamentos, além de "
        "métricas operacionais para o painel administrativo.\n\n"
        "### Autenticação\n"
        "A maior parte das rotas exige um token JWT. Faça login em **Autenticação → "
        "Autenticar usuário** para obter o token e clique em **Authorize** para usá-lo "
        "automaticamente nas próximas requisições.\n\n"
        "### Integrações\n"
        "Ao criar um agendamento, os dados são encaminhados de forma assíncrona para um "
        "workflow do n8n."
    ),
    version="1.0.0",
    openapi_tags=tags_metadata,
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


@app.get(
    "/health",
    tags=["Sistema"],
    summary="Verificar status da API",
    description="Endpoint simples de *health check*, usado para confirmar que a API está no ar.",
    responses={200: {"description": "API operando normalmente."}},
)
def health():
    return {"status": "ok"}


@app.post(
    "/auth/login",
    response_model=TokenResponse,
    tags=["Autenticação"],
    summary="Autenticar usuário",
    description="Valida e-mail e senha do usuário administrativo e retorna um token JWT para uso nas demais rotas.",
    responses={
        200: {"description": "Login realizado com sucesso. Retorna o token de acesso."},
        401: {"description": "E-mail ou senha inválidos."},
    },
)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="E-mail ou senha inválidos.")
    return TokenResponse(access_token=create_access_token(user.id))


@app.post(
    "/auth/token",
    response_model=TokenResponse,
    tags=["Autenticação"],
    summary="Autenticar via formulário OAuth2 (uso exclusivo do Swagger)",
    description=(
        "Rota auxiliar exigida pelo fluxo *OAuth2 Password* do Swagger UI, usada apenas pelo botão "
        "**Authorize** da documentação. O campo `username` do formulário deve receber o e-mail do "
        "usuário. O frontend da aplicação deve continuar utilizando **/auth/login**."
    ),
    responses={
        200: {"description": "Login realizado com sucesso. Retorna o token de acesso."},
        401: {"description": "E-mail ou senha inválidos."},
    },
)
def login_for_swagger(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == form_data.username))
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="E-mail ou senha inválidos.")
    return TokenResponse(access_token=create_access_token(user.id))


@app.get(
    "/clients",
    response_model=list[ClientOut],
    tags=["Clientes"],
    summary="Listar clientes",
    description="Retorna todos os clientes cadastrados, ordenados por nome. Aceita busca opcional por nome parcial.",
    responses={
        200: {"description": "Lista de clientes retornada com sucesso."},
        401: {"description": "Usuário não autenticado."},
    },
)
def list_clients(
    search: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(Client).order_by(Client.name)
    if search:
        stmt = stmt.where(func.lower(Client.name).contains(search.lower()))
    return db.scalars(stmt).all()


@app.post(
    "/clients",
    response_model=ClientOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Clientes"],
    summary="Criar cliente",
    description="Cadastra um novo cliente na barbearia.",
    responses={
        201: {"description": "Cliente criado com sucesso."},
        400: {"description": "Dados inválidos para criação do cliente."},
        401: {"description": "Usuário não autenticado."},
    },
)
def create_client(payload: ClientCreate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    client = Client(**payload.model_dump())
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


@app.put(
    "/clients/{client_id}",
    response_model=ClientOut,
    tags=["Clientes"],
    summary="Atualizar cliente",
    description="Atualiza os dados cadastrais de um cliente existente.",
    responses={
        200: {"description": "Cliente atualizado com sucesso."},
        400: {"description": "Dados inválidos para atualização do cliente."},
        401: {"description": "Usuário não autenticado."},
        404: {"description": "Cliente não encontrado."},
    },
)
def update_client(client_id: int, payload: ClientUpdate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    for key, value in payload.model_dump().items():
        setattr(client, key, value)
    db.commit()
    db.refresh(client)
    return client


@app.delete(
    "/clients/{client_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Clientes"],
    summary="Remover cliente",
    description="Remove um cliente do sistema. Não é permitido remover clientes que já possuem agendamentos.",
    responses={
        204: {"description": "Cliente removido com sucesso."},
        401: {"description": "Usuário não autenticado."},
        404: {"description": "Cliente não encontrado."},
        409: {"description": "Cliente possui agendamentos e não pode ser removido."},
    },
)
def delete_client(client_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    has_appointments = db.scalar(select(func.count(Appointment.id)).where(Appointment.client_id == client_id))
    if has_appointments:
        raise HTTPException(status_code=409, detail="Não é possível remover um cliente que possui agendamentos.")
    db.delete(client)
    db.commit()


@app.get(
    "/services",
    response_model=list[ServiceOut],
    tags=["Serviços"],
    summary="Listar serviços",
    description="Retorna todos os serviços oferecidos pela barbearia, ordenados por nome.",
    responses={
        200: {"description": "Lista de serviços retornada com sucesso."},
        401: {"description": "Usuário não autenticado."},
    },
)
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


@app.get(
    "/appointments",
    response_model=list[AppointmentOut],
    tags=["Agendamentos"],
    summary="Listar agendamentos",
    description="Retorna os agendamentos cadastrados, com filtros opcionais por data e por status.",
    responses={
        200: {"description": "Lista de agendamentos retornada com sucesso."},
        401: {"description": "Usuário não autenticado."},
    },
)
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


@app.post(
    "/appointments",
    response_model=AppointmentOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Agendamentos"],
    summary="Criar agendamento",
    description=(
        "Cria um novo agendamento para um cliente e serviço existentes. "
        "Verifica se o horário está disponível e envia os dados para o workflow do n8n em segundo plano."
    ),
    responses={
        201: {"description": "Agendamento criado com sucesso."},
        400: {"description": "Dados inválidos para criação do agendamento."},
        401: {"description": "Usuário não autenticado."},
        404: {"description": "Cliente ou serviço não encontrado."},
        409: {"description": "Já existe um agendamento para o horário informado."},
    },
)
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


@app.put(
    "/appointments/{appointment_id}",
    response_model=AppointmentOut,
    tags=["Agendamentos"],
    summary="Atualizar agendamento",
    description="Atualiza os dados de um agendamento existente, validando cliente, serviço e disponibilidade do novo horário.",
    responses={
        200: {"description": "Agendamento atualizado com sucesso."},
        400: {"description": "Dados inválidos para atualização do agendamento."},
        401: {"description": "Usuário não autenticado."},
        404: {"description": "Agendamento, cliente ou serviço não encontrado."},
        409: {"description": "Já existe um agendamento para o horário informado."},
    },
)
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


@app.patch(
    "/appointments/{appointment_id}/status",
    response_model=AppointmentOut,
    tags=["Agendamentos"],
    summary="Atualizar status do agendamento",
    description="Altera o status de um agendamento (ex.: concluído, cancelado, não compareceu).",
    responses={
        200: {"description": "Status do agendamento atualizado com sucesso."},
        400: {"description": "Status informado é inválido."},
        401: {"description": "Usuário não autenticado."},
        404: {"description": "Agendamento não encontrado."},
    },
)
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


@app.delete(
    "/appointments/{appointment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Agendamentos"],
    summary="Remover agendamento",
    description="Remove definitivamente um agendamento do sistema.",
    responses={
        204: {"description": "Agendamento removido com sucesso."},
        401: {"description": "Usuário não autenticado."},
        404: {"description": "Agendamento não encontrado."},
    },
)
def delete_appointment(appointment_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    appointment = db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado.")
    db.delete(appointment)
    db.commit()


@app.get(
    "/expenses",
    response_model=list[ExpenseOut],
    tags=["Financeiro"],
    summary="Listar despesas",
    description="Retorna as despesas cadastradas, com filtro opcional por mês (formato YYYY-MM).",
    responses={
        200: {"description": "Lista de despesas retornada com sucesso."},
        401: {"description": "Usuário não autenticado."},
    },
)
def list_expenses(
    month: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(Expense).order_by(Expense.month.desc(), Expense.category)
    if month:
        stmt = stmt.where(Expense.month == month)
    return db.scalars(stmt).all()


@app.post(
    "/expenses",
    response_model=ExpenseOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Financeiro"],
    summary="Criar despesa",
    description="Cadastra uma nova despesa (ex.: produtos, funcionários, aluguel, impostos) para um mês de referência.",
    responses={
        201: {"description": "Despesa criada com sucesso."},
        400: {"description": "Dados inválidos para criação da despesa."},
        401: {"description": "Usuário não autenticado."},
    },
)
def create_expense(payload: ExpenseCreate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    expense = Expense(**payload.model_dump())
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return expense


@app.put(
    "/expenses/{expense_id}",
    response_model=ExpenseOut,
    tags=["Financeiro"],
    summary="Atualizar despesa",
    description="Atualiza os dados de uma despesa existente.",
    responses={
        200: {"description": "Despesa atualizada com sucesso."},
        400: {"description": "Dados inválidos para atualização da despesa."},
        401: {"description": "Usuário não autenticado."},
        404: {"description": "Despesa não encontrada."},
    },
)
def update_expense(expense_id: int, payload: ExpenseUpdate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    expense = db.get(Expense, expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Despesa não encontrada.")
    for key, value in payload.model_dump().items():
        setattr(expense, key, value)
    db.commit()
    db.refresh(expense)
    return expense


@app.delete(
    "/expenses/{expense_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Financeiro"],
    summary="Remover despesa",
    description="Remove definitivamente uma despesa do sistema.",
    responses={
        204: {"description": "Despesa removida com sucesso."},
        401: {"description": "Usuário não autenticado."},
        404: {"description": "Despesa não encontrada."},
    },
)
def delete_expense(expense_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    expense = db.get(Expense, expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Despesa não encontrada.")
    db.delete(expense)
    db.commit()


@app.post(
    "/finance/unlock",
    tags=["Financeiro"],
    summary="Validar chave de acesso do financeiro",
    description="Verifica a chave de acesso adicional exigida para abrir a área financeira, sensível por conter faturamento e despesas.",
    responses={
        200: {"description": "Chave de acesso correta."},
        401: {"description": "Chave de acesso incorreta ou usuário não autenticado."},
    },
)
def unlock_finance(payload: FinancePasscodeRequest, _: User = Depends(get_current_user)):
    if payload.password != settings.finance_passcode:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Chave de acesso incorreta.")
    return {"unlocked": True}


@app.get(
    "/dashboard",
    response_model=DashboardOut,
    tags=["Dashboard"],
    summary="Obter indicadores do painel",
    description=(
        "Retorna métricas operacionais para o painel administrativo: agendamentos do dia "
        "(total, concluídos, cancelados e não comparecidos), total de agendamentos da semana "
        "e o serviço mais popular."
    ),
    responses={
        200: {"description": "Indicadores retornados com sucesso."},
        401: {"description": "Usuário não autenticado."},
    },
)
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
