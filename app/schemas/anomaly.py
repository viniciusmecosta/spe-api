from datetime import date
from typing import List

from pydantic import BaseModel


class AnomalyBase(BaseModel):
    date: date
    type: str
    description: str


class AnomalyResponse(AnomalyBase):
    user_id: int
    user_name: str


class UserAnomalySummary(BaseModel):
    user_id: int
    user_name: str
    anomalies: List[AnomalyBase]
