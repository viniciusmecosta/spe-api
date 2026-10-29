from typing import Annotated

from pydantic import BaseModel, Field

from app.shared.validation import BusinessDate


class DailySummaryReprocessRequest(BaseModel):
    start_date: BusinessDate
    end_date: BusinessDate
    user_ids: list[Annotated[int, Field(gt=0)]] | None = Field(default=None, min_length=1)
