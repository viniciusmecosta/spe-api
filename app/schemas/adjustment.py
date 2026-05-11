from datetime import date, time, datetime
from pydantic import BaseModel, computed_field, model_validator
from typing import Optional, List

from app.domain.models.enums import AdjustmentType, AdjustmentStatus, RecordType


class AdjustmentRequestBase(BaseModel):
    adjustment_type: AdjustmentType
    target_date: date
    record_type: Optional[RecordType] = None
    time: Optional[time] = None
    amount_hours: Optional[float] = None
    reason_text: Optional[str] = None

class AdjustmentRequestCreate(AdjustmentRequestBase):
    @model_validator(mode='after')
    def validate_rules(self) -> 'AdjustmentRequestCreate':
        if self.adjustment_type == AdjustmentType.WAIVER:
            if not self.amount_hours or not self.reason_text:
                raise ValueError("Abono requer quantidade de horas e observação.")
        else:
            if not self.record_type or self.time is None:
                raise ValueError("Ajuste de ponto requer tipo (Entrada/Saída) e horário.")
            if self.adjustment_type in [AdjustmentType.OTHER, AdjustmentType.DELETE_PUNCH] and not self.reason_text:
                raise ValueError("Este tipo de ajuste requer observação obrigatória.")
        return self

class AdjustmentWaiverCreate(BaseModel):
    user_id: int
    target_date: date
    amount_hours: float
    reason_text: str

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
    user_name: str
    status: AdjustmentStatus
    manager_id: Optional[int] = None
    manager_comment: Optional[str] = None
    created_at: datetime
    reviewed_at: Optional[datetime] = None
    attachments: List[AdjustmentAttachmentResponse] = []

    class Config:
        from_attributes = True