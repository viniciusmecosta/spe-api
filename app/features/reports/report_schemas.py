from datetime import date

from pydantic import BaseModel


class PunchDetail(BaseModel):
    id: int
    time: str
    record_type: str
    ip_address: str | None = None
    device_name: str | None = None
    platform: str | None = None
    biometric_id: int | None = None
    edited_by: str | None = None
    edit_justification: str | None = None


class DailyReportItem(BaseModel):
    date: date
    day_name: str
    is_holiday: bool
    holiday_name: str | None = None
    is_weekend: bool
    status: str
    entries: list[str]
    exits: list[str]
    punches: list[str]
    detailed_punches: list[PunchDetail] | None = None
    adjustment_id: int | None = None
    worked_hours: float
    expected_hours: float
    balance_hours: float
    extra_hours: float
    missing_hours: float
    worked_minutes: int
    worked_time: str
    expected_time: str
    unapproved_extra_time: str = "00:00"


class UserPayrollSummary(BaseModel):
    user_id: int
    user_name: str
    total_worked_time: str
    total_expected_time: str
    total_worked_hours: float = 0.0
    total_expected_hours: float = 0.0
    total_extra_hours: float = 0.0
    total_missing_hours: float = 0.0
    final_balance: float = 0.0
    total_worked_minutes: int = 0
    total_expected_minutes: int = 0
    days_worked: int
    absences: int


class AdvancedUserReportResponse(BaseModel):
    summary: UserPayrollSummary
    daily_details: list[DailyReportItem]


class MonthlyReportResponse(BaseModel):
    month: int
    year: int
    payroll_data: list[UserPayrollSummary]


class DashboardMetricsResponse(BaseModel):
    total_active_employees: int
    pending_adjustments: int
    employees_present_today: int
    date: date


class HistoryPunch(BaseModel):
    id: int
    time: str
    record_type: str
    ip_address: str | None = None
    device_name: str | None = None
    platform: str | None = None
    biometric_id: int | None = None
    edited_by: str | None = None
    edit_justification: str | None = None


class HistoryDay(BaseModel):
    date: date
    day_name: str
    is_holiday: bool
    is_weekend: bool
    is_absent: bool
    status: str
    holiday_name: str | None = None
    worked_time: str
    punches: list[HistoryPunch]
    has_anomaly: bool
    anomalies: list[str]
    abono_hours: float | None = None
    abono_id: int | None = None


class HistoryResponse(BaseModel):
    month: int
    year: int
    total_worked_time: str
    days: list[HistoryDay]


class TodayPunch(BaseModel):
    id: int
    time: str
    record_type: str


class AnomalyItem(BaseModel):
    date: str
    description: str


class Aniversariante(BaseModel):
    nome: str
    dia: int


class MyDashboardResponse(BaseModel):
    full_name: str
    next_punch_type: str
    today_punches: list[TodayPunch]
    month_anomalies: list[AnomalyItem]
    aniversariantes_do_mes: list[Aniversariante] = []
    server_time_unix: int
    server_time_formatted: str


class EmployeeHours(BaseModel):
    user_id: int
    short_name: str
    total_hours: float
    formatted_time: str


class TeamHoursResponse(BaseModel):
    month: int
    year: int
    team_total_hours: float
    team_formatted_time: str
    employees: list[EmployeeHours]


class ManagerDashboardResponse(BaseModel):
    full_name: str
    next_punch_type: str
    today_punches: list[TodayPunch]
    total_system_anomalies: int
    total_pending_adjustments: int
    today_total_punches: int
    team_hours: TeamHoursResponse
