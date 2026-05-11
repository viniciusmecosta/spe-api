import os
import shutil
import uuid
from datetime import datetime
from fastapi import UploadFile, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.models.adjustment import AdjustmentRequest
from app.domain.models.enums import AdjustmentStatus, AdjustmentType
from app.domain.models.time_record import TimeRecord
from app.repositories.adjustment_repository import adjustment_repository
from app.repositories.time_record_repository import time_record_repository
from app.schemas.adjustment import AdjustmentRequestCreate, AdjustmentWaiverCreate
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
            amount_hours=waiver_in.amount_hours,
            reason_text=waiver_in.reason_text
        )

        adjustment = adjustment_repository.create(db, waiver_in.user_id, adj_in)
        adjustment = adjustment_repository.update_status(
            db, adjustment, AdjustmentStatus.APPROVED, manager_id, "Abonado manualmente pelo gestor"
        )

        audit_service.log(
            db, actor_id=manager_id, target_user_id=waiver_in.user_id, action="CREATE_WAIVER",
            entity="ADJUSTMENT", entity_id=adjustment.id,
            new_data={
                "target_date": str(waiver_in.target_date),
                "amount_hours": waiver_in.amount_hours,
                "reason": waiver_in.reason_text
            }
        )
        return adjustment

    def delete_adjustment(self, db: Session, adjustment_id: int, manager_id: int):
        request = adjustment_repository.get(db, adjustment_id)
        if not request:
            raise HTTPException(status_code=404, detail="Adjustment not found")

        payroll_service.validate_period_open(db, request.target_date)

        target_user_id = request.user_id
        old_data = {
            "type": request.adjustment_type.value,
            "target_date": str(request.target_date)
        }

        adjustment_repository.delete(db, adjustment_id)

        audit_service.log(
            db, actor_id=manager_id, target_user_id=target_user_id, action="DELETE_ADJUSTMENT",
            entity="ADJUSTMENT", entity_id=adjustment_id, old_data=old_data
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
            db, actor_id=user_id, target_user_id=request.user_id, action="UPLOAD_ATTACHMENT",
            entity="ADJUSTMENT", entity_id=request_id,
            new_data={"file_name": safe_filename, "file_type": file.content_type}
        )
        return attachment

    def approve_adjustment(self, db: Session, request_id: int, manager_id: int) -> AdjustmentRequest:
        request = adjustment_repository.get(db, request_id)
        if not request:
            raise HTTPException(status_code=404, detail="Request not found")

        payroll_service.validate_period_open(db, request.target_date)

        if request.adjustment_type == AdjustmentType.WAIVER:
            if not request.attachments:
                raise HTTPException(status_code=400, detail="Para aprovar um abono, é obrigatório haver anexo.")
        else:
            self._execute_adjustment_action(db, request)

        old_status = request.status.value
        updated = adjustment_repository.update_status(db, request, AdjustmentStatus.APPROVED, manager_id)

        audit_service.log(
            db, actor_id=manager_id, target_user_id=request.user_id, action="APPROVE_ADJUSTMENT",
            entity="ADJUSTMENT", entity_id=request_id,
            old_data={"status": old_status}, new_data={"status": updated.status.value}
        )
        return updated

    def _execute_adjustment_action(self, db: Session, request: AdjustmentRequest):
        target_dt = datetime.combine(request.target_date, request.time)

        if request.adjustment_type == AdjustmentType.DELETE_PUNCH:
            record = db.query(TimeRecord).filter(
                TimeRecord.user_id == request.user_id,
                TimeRecord.record_type == request.record_type,
                TimeRecord.record_datetime == target_dt
            ).first()
            if record:
                db.delete(record)
                db.commit()
        else:
            time_record_repository.create(
                db, user_id=request.user_id, record_type=request.record_type,
                record_datetime=target_dt, ip_address="ADJUSTMENT_APPROVED", is_time_verified=True
            )

    def reject_adjustment(self, db: Session, request_id: int, manager_id: int, comment: str) -> AdjustmentRequest:
        request = adjustment_repository.get(db, request_id)
        if not request:
            raise HTTPException(status_code=404, detail="Request not found")

        payroll_service.validate_period_open(db, request.target_date)

        old_status = request.status.value
        updated = adjustment_repository.update_status(db, request, AdjustmentStatus.REJECTED, manager_id, comment)

        audit_service.log(
            db, actor_id=manager_id, target_user_id=request.user_id, action="REJECT_ADJUSTMENT",
            entity="ADJUSTMENT", entity_id=request_id,
            old_data={"status": old_status}, new_data={"status": updated.status.value, "comment": comment}
        )
        return updated

adjustment_service = AdjustmentService()