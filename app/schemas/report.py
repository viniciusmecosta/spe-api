from datetime import date
from typing import List

from pydantic import BaseModel


class DailyReportItem(BaseModel):
    date: date
    entries: List[str]
    exits: List[str]
    worked_hours: float
    balance_hours: float


class UserReportResponse(BaseModel):
    user_id: int
    user_name: str
    month: int
    year: int
    total_worked_hours: float
    expected_hours: float
    total_balance_hours: float
    daily_details: List[DailyReportItem]


class MonthlySummaryItem(BaseModel):
    user_id: int
    user_name: str
    total_worked_hours: float
    expected_hours: float
    balance_hours: float


class MonthlyReportResponse(BaseModel):
    month: int
    year: int
    employees: List[MonthlySummaryItem]
