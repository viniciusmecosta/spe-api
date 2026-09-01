from datetime import date, datetime
from datetime import time as dt_time

from pydantic import BaseModel, ConfigDict

from app.shared.enums import AdjustmentStatus, AdjustmentType, RecordType


class ReportAdjustmentItem(BaseModel):
    id: int
    user_id: int
    adjustment_type: AdjustmentType
    record_type: RecordType | None = None
    target_date: date
    time: dt_time | None = None
    amount_hours: float | None = None
    approved_amount_hours: float | None = None
    reason_text: str | None = None
    status: AdjustmentStatus
    manager_id: int | None = None
    manager_comment: str | None = None
    created_at: datetime | None = None
    reviewed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class PunchDetail(BaseModel):
    id: int
    short_id: str
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
    accounted_time: str = "00:00"
    expected_time: str
    unapproved_extra_time: str = "00:00"
    has_excess: bool = False
    excess_status: str | None = None
    daily_excess_id: int | None = None
    adjustments: list[ReportAdjustmentItem] = []


class UserPayrollSummary(BaseModel):
    user_id: int
    user_name: str
    total_worked_time: str
    total_expected_time: str
    total_accounted_time: str = "00:00"
    total_worked_hours: float = 0.0
    total_expected_hours: float = 0.0
    total_extra_hours: float = 0.0
    total_missing_hours: float = 0.0
    final_balance: float = 0.0
    total_worked_minutes: int = 0
    total_expected_minutes: int = 0
    total_accounted_minutes: int = 0
    days_worked: int
    absences: int


class AdvancedUserReportResponse(BaseModel):
    summary: UserPayrollSummary
    daily_details: list[DailyReportItem]


class DashboardMetricsResponse(BaseModel):
    total_active_employees: int
    pending_adjustments: int
    employees_present_today: int
    date: date


class HistoryPunch(BaseModel):
    id: int
    short_id: str
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
    accounted_time: str = "00:00"
    punches: list[HistoryPunch]
    has_anomaly: bool
    anomalies: list[str]
    abono_hours: float | None = None
    abono_id: int | None = None
    has_excess: bool = False
    excess_status: str | None = None
    daily_excess_id: int | None = None
    adjustments: list[ReportAdjustmentItem] = []


class HistoryResponse(BaseModel):
    month: int
    year: int
    total_worked_time: str
    total_accounted_time: str = "00:00"
    days: list[HistoryDay]


class TodayPunch(BaseModel):
    id: int
    short_id: str
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
