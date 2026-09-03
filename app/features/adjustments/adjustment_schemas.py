from datetime import date, datetime, timedelta
from datetime import time as dt_time

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from app.features.time_records.time_record_schemas import TimeRecordSimple
from app.shared.enums import AdjustmentStatus, AdjustmentType, RecordType


class AdjustmentRequestBase(BaseModel):
    adjustment_type: AdjustmentType
    target_date: date
    record_type: RecordType | None = None
    time: dt_time | None = None
    amount_hours: float | None = None
    reason_text: str | None = None


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


class AdjustmentApproveRequest(BaseModel):
    comment: str | None = None
    approved_amount_hours: float | None = Field(default=None, ge=0)


class BulkReprocessDailyExcessRequest(BaseModel):
    start_date: date
    end_date: date
    user_ids: list[int]
    overwrite_reviewed: bool = False


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

    model_config = ConfigDict(from_attributes=True)


class AdjustmentRequestResponse(AdjustmentRequestBase):
    id: int
    user_id: int
    user_name: str
    status: AdjustmentStatus
    manager_id: int | None = None
    manager_comment: str | None = None
    approved_amount_hours: float | None = None
    created_at: datetime
    reviewed_at: datetime | None = None
    attachments: list[AdjustmentAttachmentResponse] = []
    time_records: list[TimeRecordSimple] = []

    def _build_extra_time_info(self) -> dict:
        extra_mins = int(round(self.amount_hours * 60)) if self.amount_hours else 0
        actual_time = self.time.strftime("%H:%M") if self.time else "--:--"
        expected = "--:--"
        if self.time and self.amount_hours:
            dummy = datetime.combine(datetime.today(), self.time)
            expected_dt = dummy + timedelta(minutes=extra_mins + 5)
            expected = expected_dt.strftime("%H:%M")
        return {
            "tempo_extra_minutos": extra_mins,
            "horario_batido": actual_time,
            "horario_esperado": expected
        }

    def _build_daily_excess_info(self) -> dict:
        extra_mins = int(round(self.amount_hours * 60)) if self.amount_hours else 0
        approved_mins = int(round(self.approved_amount_hours * 60)) if self.approved_amount_hours is not None else None
        return {
            "tempo_excedente_minutos": extra_mins,
            "tempo_aprovado_minutos": approved_mins,
            "motivo": self.reason_text,
        }

    def _build_punch_info(self) -> dict:
        req_time = self.time.strftime("%H:%M") if self.time else "--:--"
        return {
            "horario_solicitado": req_time,
            "tipo_batida": self.record_type.value if self.record_type else None,
            "batidas_do_dia": [r.record_datetime.strftime("%H:%M") for r in self.time_records]
        }

    @computed_field
    def metadata_info(self) -> dict:
        if self.adjustment_type == AdjustmentType.EXTRA_TIME:
            return self._build_extra_time_info()
        if self.adjustment_type == AdjustmentType.DAILY_EXCESS:
            return self._build_daily_excess_info()
        if self.adjustment_type in [AdjustmentType.FORGOT_PUNCH, AdjustmentType.PUNCH_NOT_COUNTED, AdjustmentType.DELETE_PUNCH]:
            return self._build_punch_info()
        if self.adjustment_type == AdjustmentType.WAIVER:
            return {"horas_abonadas": self.amount_hours}
        return {}

    model_config = ConfigDict(from_attributes=True)
