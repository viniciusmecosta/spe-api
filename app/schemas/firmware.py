from datetime import datetime
from pydantic import BaseModel, ConfigDict


class FirmwareResponse(BaseModel):
    version: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)