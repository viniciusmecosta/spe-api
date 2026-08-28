from datetime import date

from pydantic import BaseModel


class AnomalyBase(BaseModel):
    date: date
    type: str
    description: str


class AnomalyResponse(AnomalyBase):
    user_id: int
    user_name: str
