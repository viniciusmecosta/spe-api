from datetime import date, datetime
from pydantic import BaseModel
from typing import List, Optional


class PunchDetail(BaseModel):
    id: int
    time: str
    record_type: str
    ip_address: Optional[str] = None
    device_name: Optional[str] = None
    platform: Optional[str] = None
    is_manual: bool
    is_time_verified: Optional[bool] = None
    biometric_id: Optional[int] = None
    original_timestamp: Optional[datetime] = None
    edited_by: Optional[int] = None
    edit_justification: Optional[str] = None
    edit_reason: Optional[str] = None


class DailyReportItem(BaseModel):
    date: date
    day_name: str
    is_holiday: bool
    is_weekend: bool
    status: str
    entries: List[str]
    exits: List[str]
    punches: List[str]
    detailed_punches: Optional[List[PunchDetail]] = None

    adjustment_id: Optional[int] = None

    worked_hours: float
    expected_hours: float
    balance_hours: float
    extra_hours: float
    missing_hours: float

    worked_minutes: int
    worked_time: str
    expected_time: str


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
