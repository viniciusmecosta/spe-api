import uuid
import os
import shutil
from datetime import datetime
from fastapi import UploadFile, HTTPException, status
from sqlalchemy.orm import Session
from app.core.config import settings
from app.repositories.adjustment_repository import adjustment_repository
from app.repositories.user_repository import user_repository
from app.schemas.adjustment import AdjustmentRequestCreate, AdjustmentRequestUpdate
from app.domain.models.adjustment import AdjustmentRequest
from app.domain.models.enums import AdjustmentStatus
from app.services.audit_service import audit_service
from app.services.payroll_service import payroll_service  # Importação nova


class AdjustmentService:
    def create_adjustment_request(self, db: Session, user_id: int,
                                  obj_in: AdjustmentRequestCreate) -> AdjustmentRequest:
        # Valida Folha na data do ajuste
        payroll_service.validate_period_open(db, obj_in.target_date)

        adjustment = adjustment_repository.create(db, user_id, obj_in)
        return adjustment

    def upload_attachment(self, db: Session, request_id: int, file: UploadFile, user_id: int):
        request = adjustment_repository.get(db, request_id)
        if not request:
            raise HTTPException(status_code=404, detail="Adjustment request not found")

        if request.user_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized")

        # Valida Folha (opcional, mas bom bloquear upload em mês fechado)
        payroll_service.validate_period_open(db, request.target_date)

        file_ext = file.filename.split(".")[-1]
        file_name = f"{uuid.uuid4()}.{file_ext}"
        file_path = os.path.join(settings.UPLOAD_DIR, file_name)

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        attachment = adjustment_repository.create_attachment(db, request_id, file_path, file.content_type)

        audit_service.log(
            db, user_id=user_id, action="UPLOAD_ATTACHMENT", entity="ADJUSTMENT", entity_id=request_id,
            details=f"Uploaded file {file.filename}"
        )
        return attachment

    def approve_adjustment(self, db: Session, request_id: int, manager_id: int) -> AdjustmentRequest:
        request = adjustment_repository.get(db, request_id)
        if not request:
            raise HTTPException(status_code=404, detail="Request not found")

        # Valida Folha
        payroll_service.validate_period_open(db, request.target_date)

        updated = adjustment_repository.update_status(db, request, AdjustmentStatus.APPROVED, manager_id)

        audit_service.log(
            db, user_id=manager_id, action="APPROVE_ADJUSTMENT", entity="ADJUSTMENT", entity_id=request_id,
            details="Approved adjustment request"
        )
        return updated

    def reject_adjustment(self, db: Session, request_id: int, manager_id: int, comment: str) -> AdjustmentRequest:
        request = adjustment_repository.get(db, request_id)
        if not request:
            raise HTTPException(status_code=404, detail="Request not found")

        # Valida Folha
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