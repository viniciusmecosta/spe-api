from typing import Optional, Any
from pydantic import BaseModel


class DevicePunchResponse(BaseModel):
    message: Optional[str] = None
    led: str
    data: Optional[Any] = None