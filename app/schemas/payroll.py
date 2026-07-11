from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict


class PayrollClosureCreate(BaseModel):
    month: int
    year: int


class PayrollHistoryItem(BaseModel):
    action: str
    timestamp: datetime
    user_id: int
    user_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PayrollClosureResponse(PayrollClosureCreate):
    id: Optional[int] = None
    is_closed: bool
    closed_at: Optional[datetime] = None
    closed_by_user_id: Optional[int] = None
    closed_by_name: Optional[str] = None
    history: List[PayrollHistoryItem] = []

    model_config = ConfigDict(from_attributes=True)
