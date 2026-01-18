import os
import shutil
import uuid
from datetime import datetime
from fastapi import UploadFile, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.models.adjustment import AdjustmentRequest
from app.domain.models.enums import AdjustmentStatus, AdjustmentType, RecordType
from app.repositories.adjustment_repository import adjustment_repository
from app.repositories.time_record_repository import time_record_repository
from app.schemas.adjustment import AdjustmentRequestCreate, AdjustmentRequestUpdate, AdjustmentWaiverCreate
from app.services.audit_service import audit_service
from app.services.payroll_service import payroll_service


class AdjustmentService:
    def create_adjustment_request(self, db: Session, user_id: int,
                                  obj_in: AdjustmentRequestCreate) -> AdjustmentRequest:
        payroll_service.validate_period_open(db, obj_in.target_date)
        return adjustment_repository.create(db, user_id, obj_in)

    def create_manager_waiver(self, db: Session, waiver_in: AdjustmentWaiverCreate,
                              manager_id: int) -> AdjustmentRequest:
        payroll_service.validate_period_open(db, waiver_in.target_date)

        adj_in = AdjustmentRequestCreate(
            adjustment_type=AdjustmentType.WAIVER,
            target_date=waiver_in.target_date,
            reason_text=waiver_in.reason_text,
            amount_hours=waiver_in.amount_hours
        )

        adjustment = adjustment_repository.create(db, waiver_in.user_id, adj_in)
        adjustment = adjustment_repository.update_status(
            db, adjustment, AdjustmentStatus.APPROVED, manager_id, "Abonado manualmente pelo gestor"
        )

        audit_service.log(
            db, user_id=manager_id, action="CREATE_WAIVER", entity="ADJUSTMENT", entity_id=adjustment.id,
            details=f"Absence waived for user {waiver_in.user_id} on {waiver_in.target_date} (Amount: {waiver_in.amount_hours})"
        )
        return adjustment

    def delete_adjustment(self, db: Session, adjustment_id: int, manager_id: int):
        request = adjustment_repository.get(db, adjustment_id)
        if not request:
            raise HTTPException(status_code=404, detail="Adjustment not found")

        payroll_service.validate_period_open(db, request.target_date)

        adjustment_repository.delete(db, adjustment_id)

        audit_service.log(
            db, user_id=manager_id, action="DELETE_ADJUSTMENT", entity="ADJUSTMENT", entity_id=adjustment_id,
            details="Deleted adjustment/waiver"
        )

    def upload_attachment(self, db: Session, request_id: int, file: UploadFile, user_id: int):
        request = adjustment_repository.get(db, request_id)
        if not request:
            raise HTTPException(status_code=404, detail="Adjustment request not found")

        if request.user_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized")

        payroll_service.validate_period_open(db, request.target_date)

        filename = file.filename.lower()
        if "." not in filename:
            raise HTTPException(status_code=400, detail="Nome de arquivo inválido.")

        file_ext = filename.split(".")[-1]
        allowed_extensions = {"pdf", "jpg", "jpeg", "png"}

        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail="Tipo de arquivo não permitido. Use apenas PDF, JPG ou PNG."
            )
        header = file.file.read(10)
        file.file.seek(0)

        is_valid = False

        if file_ext == "pdf" and header.startswith(b"%PDF"):
            is_valid = True
        elif file_ext == "png" and header.startswith(b"\x89PNG\r\n\x1a\n"):
            is_valid = True
        elif file_ext in ["jpg", "jpeg"] and header.startswith(b"\xff\xd8\xff"):
            is_valid = True

        if not is_valid:
            raise HTTPException(
                status_code=400,
                detail="O conteúdo do arquivo não corresponde à extensão ou está corrompido."
            )
        safe_filename = f"{uuid.uuid4()}.{file_ext}"
        file_path = os.path.join(settings.UPLOAD_DIR, safe_filename)

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        attachment = adjustment_repository.create_attachment(db, request_id, file_path, file.content_type)

        audit_service.log(
            db, user_id=user_id, action="UPLOAD_ATTACHMENT", entity="ADJUSTMENT", entity_id=request_id,
            details=f"Uploaded file {safe_filename}"
        )
        return attachment

    def approve_adjustment(self, db: Session, request_id: int, manager_id: int) -> AdjustmentRequest:
        request = adjustment_repository.get(db, request_id)
        if not request:
            raise HTTPException(status_code=404, detail="Request not found")

        payroll_service.validate_period_open(db, request.target_date)

        if request.adjustment_type == AdjustmentType.CERTIFICATE:
            if request.amount_hours is None or request.amount_hours <= 0:
                raise HTTPException(
                    status_code=400,
                    detail="Para aprovar um atestado, é obrigatório informar a quantidade de horas a abonar."
                )

        if request.adjustment_type in [AdjustmentType.MISSING_ENTRY, AdjustmentType.MISSING_EXIT, AdjustmentType.BOTH]:
            self._create_punches_from_adjustment(db, request)

        updated = adjustment_repository.update_status(db, request, AdjustmentStatus.APPROVED, manager_id)

        audit_service.log(
            db, user_id=manager_id, action="APPROVE_ADJUSTMENT", entity="ADJUSTMENT", entity_id=request_id,
            details=f"Approved adjustment request ({request.adjustment_type})"
        )
        return updated

    def _create_punches_from_adjustment(self, db: Session, request: AdjustmentRequest):
        user_id = request.user_id
        target_date = request.target_date

        if request.adjustment_type in [AdjustmentType.MISSING_ENTRY, AdjustmentType.BOTH]:
            if request.entry_time:
                entry_dt = datetime.combine(target_date, request.entry_time)
                time_record_repository.create(
                    db, user_id=user_id, record_type=RecordType.ENTRY,
                    record_datetime=entry_dt, ip_address="ADJUSTMENT_APPROVED", is_time_verified=True
                )

        if request.adjustment_type in [AdjustmentType.MISSING_EXIT, AdjustmentType.BOTH]:
            if request.exit_time:
                exit_dt = datetime.combine(target_date, request.exit_time)
                time_record_repository.create(
                    db, user_id=user_id, record_type=RecordType.EXIT,
                    record_datetime=exit_dt, ip_address="ADJUSTMENT_APPROVED", is_time_verified=True
                )

    def reject_adjustment(self, db: Session, request_id: int, manager_id: int, comment: str) -> AdjustmentRequest:
        request = adjustment_repository.get(db, request_id)
        if not request:
            raise HTTPException(status_code=404, detail="Request not found")

        payroll_service.validate_period_open(db, request.target_date)

        updated = adjustment_repository.update_status(db, request, AdjustmentStatus.REJECTED, manager_id, comment)

        audit_service.log(
            db, user_id=manager_id, action="REJECT_ADJUSTMENT", entity="ADJUSTMENT", entity_id=request_id,
            details=f"Rejected: {comment}"
        )
        return updated

    def update_adjustment(self, db: Session, request_id: int, obj_in: AdjustmentRequestUpdate,
                          manager_id: int) -> AdjustmentRequest:
        request = adjustment_repository.get(db, request_id)
        if not request:
            raise HTTPException(status_code=404, detail="Request not found")

        payroll_service.validate_period_open(db, request.target_date)
        if obj_in.target_date:
            payroll_service.validate_period_open(db, obj_in.target_date)

        updated = adjustment_repository.update(db, request, obj_in)

        audit_service.log(
            db, user_id=manager_id, action="UPDATE_ADJUSTMENT", entity="ADJUSTMENT", entity_id=request_id,
            details="Updated adjustment details"
        )
        return updated


adjustment_service = AdjustmentService()
