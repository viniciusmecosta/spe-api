from datetime import datetime

from pydantic import BaseModel


class PayrollClosureCreate(BaseModel):
    month: int
    year: int


class PayrollClosureResponse(PayrollClosureCreate):
    id: int
    is_closed: bool
    closed_at: datetime
    closed_by_user_id: int

    class Config:
        from_attributes = True
