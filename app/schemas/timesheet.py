from datetime import date
from typing import List, Optional
from pydantic import BaseModel


class TimesheetCompany(BaseModel):
    name: str
    cnpj: str
    address: str
    phone: Optional[str] = None


class TimesheetEmployee(BaseModel):
    name: str
    cpf: Optional[str] = None
    pis: Optional[str] = None
    role: str


class TimesheetDay(BaseModel):
    date: date
    day_name: str
    punches: List[str]
    worked_time: str
    status: str
    is_holiday: bool
    is_weekend: bool


class TimesheetSummary(BaseModel):
    total_worked_hours: str
    total_expected_hours: str
    balance: str


class OfficialTimesheetResponse(BaseModel):
    company: Optional[TimesheetCompany] = None
    employee: TimesheetEmployee
    month: int
    year: int
    generation_date: date
    days: List[TimesheetDay]
    summary: TimesheetSummary
    signature_term: str