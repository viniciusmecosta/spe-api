from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.shared.validation import Month, Year


class PayrollClosureCreate(BaseModel):
    month: Month
    year: Year


class PayrollReopenCreate(PayrollClosureCreate):
    observation: str


class PayrollHistoryItem(BaseModel):
    action: str
    timestamp: datetime
    user_id: int
    user_name: str | None = None
    observation: str | None = None
    report_path: str | None = None

    model_config = ConfigDict(from_attributes=True)


class PayrollClosureResponse(PayrollClosureCreate):
    id: int | None = None
    closed_at: datetime | None = None
    closed_by_user_id: int | None = None
    closed_by_name: str | None = None
    is_closed: bool
    history: list[dict[str, Any]] = []
    report_path: str | None = None

    model_config = ConfigDict(from_attributes=True)
