from datetime import date
from typing import Annotated

from pydantic import BaseModel, Field


class DailySummaryReprocessRequest(BaseModel):
    start_date: date
    end_date: date
    user_ids: list[Annotated[int, Field(gt=0)]] | None = Field(default=None, min_length=1)
