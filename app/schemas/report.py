from typing import List, Optional
from datetime import date
from pydantic import BaseModel

class DailyReportItem(BaseModel):
    date: date
    day_name: str
    is_holiday: bool
    is_weekend: bool
    status: str  # Normal, Falta, Folga, Extra
    entries: List[str]
    exits: List[str]
    worked_hours: float
    expected_hours: float
    balance_hours: float
    extra_hours: float  # Horas positivas do dia
    missing_hours: float # Horas negativas do dia (Falta/Atraso)

class UserPayrollSummary(BaseModel):
    user_id: int
    user_name: str
    total_worked_hours: float
    total_expected_hours: float
    total_extra_hours: float    # Banco Positivo/Hora Extra
    total_missing_hours: float  # Banco Negativo/Faltas
    final_balance: float        # Saldo líquido
    days_worked: int
    absences: int

class AdvancedUserReportResponse(BaseModel):
    summary: UserPayrollSummary
    daily_details: List[DailyReportItem]

class MonthlyReportResponse(BaseModel):
    month: int
    year: int
    payroll_data: List[UserPayrollSummary]

class DashboardMetricsResponse(BaseModel):
    total_active_employees: int
    pending_adjustments: int
    employees_present_today: int
    date: date