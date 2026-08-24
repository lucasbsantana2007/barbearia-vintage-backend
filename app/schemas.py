from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field

AppointmentStatus = Literal["scheduled", "completed", "cancelled", "no_show"]


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ClientCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    notes: str | None = None


class ClientUpdate(ClientCreate):
    pass


class ClientOut(ClientCreate):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ServiceOut(BaseModel):
    id: int
    name: str
    duration_minutes: int
    price: Decimal
    model_config = ConfigDict(from_attributes=True)


class AppointmentCreate(BaseModel):
    client_id: int
    service_id: int
    date: date
    start_time: time
    status: AppointmentStatus = "scheduled"


class AppointmentUpdate(AppointmentCreate):
    pass


class AppointmentStatusUpdate(BaseModel):
    status: AppointmentStatus


class AppointmentOut(BaseModel):
    id: int
    client_id: int
    service_id: int
    date: date
    start_time: time
    status: AppointmentStatus
    created_at: datetime
    updated_at: datetime
    client: ClientOut
    service: ServiceOut
    model_config = ConfigDict(from_attributes=True)


class ExpenseCreate(BaseModel):
    category: str = Field(min_length=2, max_length=120)
    amount: Decimal = Field(gt=0)
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="Mês de referência no formato YYYY-MM.")


class ExpenseUpdate(ExpenseCreate):
    pass


class ExpenseOut(ExpenseCreate):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class FinancePasscodeRequest(BaseModel):
    password: str


class DashboardOut(BaseModel):
    appointments_today: int
    completed_today: int
    cancelled_today: int
    no_show_today: int
    appointments_this_week: int
    most_popular_service: str | None
