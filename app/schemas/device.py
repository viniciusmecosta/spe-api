from pydantic import BaseModel
from typing import Optional, Any


class DevicePunchResponse(BaseModel):
    message: Optional[str] = None
    led: str
    data: Optional[Any] = None
