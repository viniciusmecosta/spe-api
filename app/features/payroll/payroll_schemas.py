from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.shared.validation import Month, Year


class PayrollClosureCreate(BaseModel):
    month: Month
    year: Year


class PayrollReopenCreate(PayrollClosureCreate):
    observation: str


class PayrollCloseTransition(BaseModel):
    action: Literal["CLOSE"]
    model_config = ConfigDict(extra="forbid")


class PayrollReopenTransition(BaseModel):
    action: Literal["REOPEN"]
    observation: str = Field(min_length=1, max_length=1000)
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


PayrollTransitionRequest = Annotated[
    PayrollCloseTransition | PayrollReopenTransition, Field(discriminator="action")
]


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


class PayrollTransitionResponse(BaseModel):
    year: Year
    month: Month
    action: Literal["CLOSE", "REOPEN"]
    is_closed: bool
    closure: PayrollClosureResponse | None = None
