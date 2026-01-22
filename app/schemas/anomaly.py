from datetime import date
from pydantic import BaseModel
from typing import List, Optional


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
