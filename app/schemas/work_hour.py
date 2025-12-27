from pydantic import BaseModel
from datetime import date
from typing import Optional

class WorkHourBalanceResponse(BaseModel):
    user_id: int
    start_date: date
    end_date: date
    total_worked_hours: float
    expected_hours: float
    balance_hours: float

    class Config:
        from_attributes = True