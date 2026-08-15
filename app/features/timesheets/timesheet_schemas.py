from datetime import date

from pydantic import BaseModel


class TimesheetCompany(BaseModel):
    name: str
    cnpj: str
    address: str
    phone: str | None = None


class TimesheetEmployee(BaseModel):
    name: str
    cpf: str | None = None
    pis: str | None = None
    role: str


class TimesheetDay(BaseModel):
    date: date
    day_name: str
    punches: list[str]
    worked_time: str
    status: str
    is_holiday: bool
    is_weekend: bool


class TimesheetSummary(BaseModel):
    total_worked_hours: str
    total_expected_hours: str
    balance: str


class OfficialTimesheetResponse(BaseModel):
    company: TimesheetCompany | None = None
    employee: TimesheetEmployee
    month: int
    year: int
    generation_date: date
    days: list[TimesheetDay]
    summary: TimesheetSummary
    signature_term: str


class AnomalyBase(BaseModel):
    date: date
    type: str
    description: str


class AnomalyResponse(AnomalyBase):
    user_id: int
    user_name: str


class UserAnomalySummary(BaseModel):
    user_id: int
    user_name: str
    anomalies: list[AnomalyBase]
