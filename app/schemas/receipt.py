from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class AuditLogTimeline(BaseModel):
    action: str
    timestamp: datetime
    user_name: Optional[str] = None
    old_data: Optional[Dict[str, Any]] = None
    new_data: Optional[Dict[str, Any]] = None


class ReceiptResponse(BaseModel):
    short_id: str
    record_id: int
    company_name: str
    company_cnpj: str
    employee_name: str
    employee_cpf: str
    record_datetime: datetime
    device_name: str
    record_type: str
    timeline: List[AuditLogTimeline]
