from datetime import date, time, datetime
from typing import Optional, List

from pydantic import BaseModel, computed_field

from app.domain.models.enums import AdjustmentType, AdjustmentStatus


class AdjustmentRequestBase(BaseModel):
    adjustment_type: AdjustmentType
    target_date: date
    reason_text: Optional[str] = None
    entry_time: Optional[time] = None
    exit_time: Optional[time] = None
    amount_hours: Optional[float] = None


class AdjustmentRequestCreate(AdjustmentRequestBase):
    pass


class AdjustmentWaiverCreate(BaseModel):
    user_id: int
    target_date: date
    reason_text: str = "Abono Administrativo"
    amount_hours: Optional[float] = None  # Permitir definir quantidade


class AdjustmentRequestUpdate(BaseModel):
    adjustment_type: Optional[AdjustmentType] = None
    target_date: Optional[date] = None
    entry_time: Optional[time] = None
    exit_time: Optional[time] = None
    reason_text: Optional[str] = None
    amount_hours: Optional[float] = None


class AdjustmentAttachmentResponse(BaseModel):
    id: int
    file_path: str
    file_type: str
    uploaded_at: datetime

    @computed_field
    def url(self) -> str:
        filename = self.file_path.split("/")[-1]
        if "\\" in filename:
            filename = filename.split("\\")[-1]
        return f"/static/{filename}"

    class Config:
        from_attributes = True


class AdjustmentRequestResponse(AdjustmentRequestBase):
    id: int
    user_id: int
    status: AdjustmentStatus
    manager_id: Optional[int] = None
    manager_comment: Optional[str] = None
    created_at: datetime
    reviewed_at: Optional[datetime] = None
    attachments: List[AdjustmentAttachmentResponse] = []

    class Config:
        from_attributes = True
