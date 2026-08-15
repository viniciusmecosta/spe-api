from datetime import date

from pydantic import BaseModel, ConfigDict


class WorkHourBalanceResponse(BaseModel):
    user_id: int
    start_date: date
    end_date: date
    total_worked_hours: float
    expected_hours: float
    balance_hours: float

    model_config = ConfigDict(from_attributes=True)
