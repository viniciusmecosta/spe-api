from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class PayrollClosureCreate(BaseModel):
    month: int
    year: int


class PayrollClosureResponse(PayrollClosureCreate):
    id: Optional[int] = None
    is_closed: bool
    closed_at: Optional[datetime] = None
    closed_by_user_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)
