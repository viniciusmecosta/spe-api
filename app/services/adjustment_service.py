import os
import shutil
import uuid
from datetime import date, datetime

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.models.adjustment import AdjustmentRequest
from app.domain.models.enums import AdjustmentStatus, AdjustmentType
from app.domain.models.time_record import TimeRecord
from app.repositories.adjustment_repository import adjustment_repository
from app.repositories.time_record_repository import (
    get_local_time,
    time_record_repository,
)
from app.schemas.adjustment import AdjustmentRequestCreate, AdjustmentWaiverCreate
from app.services.audit_service import audit_service
from app.services.payroll_service import payroll_service

NOT_FOUND_MSG = "Solicitação não encontrada."

class AdjustmentService:

    def _enrich_adjustments_with_records(self, db: Session, adjustments: list[AdjustmentRequest]) -> list[
        AdjustmentRequest]:
        if not adjustments:
            return []

        user_ids = {a.user_id for a in adjustments}
        min_date = min(a.target_date for a in adjustments)
        max_date = max(a.target_date for a in adjustments)

        min_dt = datetime.combine(min_date, datetime.min.time())
        max_dt = datetime.combine(max_date, datetime.max.time())

        records = db.query(TimeRecord).filter(
            TimeRecord.user_id.in_(user_ids),
            TimeRecord.record_datetime >= min_dt,
            TimeRecord.record_datetime <= max_dt,
            TimeRecord.is_ignored == False
        ).order_by(TimeRecord.record_datetime.asc()).all()

        for adj in adjustments:
            adj.time_records = [
                r for r in records
                if r.user_id == adj.user_id and r.record_datetime.date() == adj.target_date
            ]

        return adjustments

    def _validate_waiver_limit(self, db: Session, user_id: int, target_date: date, amount_hours: float | None):
        if not amount_hours:
            return

        existing_waivers = adjustment_repository.get_waivers_by_user_and_date(db, user_id, target_date)
        existing_hours = sum(w.amount_hours for w in existing_waivers if w.amount_hours)

        if existing_hours + amount_hours > 10.0:
            remaining = max(0.0, 10.0 - existing_hours)
            raise HTTPException(
                status_code=400,
                detail=f"Limite máximo de 10 horas de abono por dia excedido. Horas disponíveis para esta data: {remaining}h."
            )

    def get_all_enriched(
        self, db: Session, skip: int = 0, limit: int = 100,
        month: int | None = None, year: int | None = None,
        status: str | None = None,
        order_by: str = "created_at", order_direction: str = "desc"
    ) -> list[AdjustmentRequest]:
        adjustments = adjustment_repository.get_all(db, skip, limit, month, year, status, order_by, order_direction)
        return self._enrich_adjustments_with_records(db, adjustments)

    def get_my_enriched(
        self, db: Session, user_id: int, skip: int = 0, limit: int = 100,
        month: int | None = None, year: int | None = None,
        status: str | None = None,
        order_by: str = "created_at", order_direction: str = "desc"
    ) -> list[AdjustmentRequest]:
        adjustments = adjustment_repository.get_all_by_user(db, user_id, skip, limit, month, year, status, order_by, order_direction)
        return self._enrich_adjustments_with_records(db, adjustments)

    def create_adjustment_request(self, db: Session, user_id: int,
                                  obj_in: AdjustmentRequestCreate) -> AdjustmentRequest:
        payroll_service.validate_period_open(db, obj_in.target_date)

        if obj_in.adjustment_type == AdjustmentType.WAIVER:
            self._validate_waiver_limit(db, user_id, obj_in.target_date, obj_in.amount_hours)

        adjustment = adjustment_repository.create(db, user_id, obj_in)
        return self._enrich_adjustments_with_records(db, [adjustment])[0]

    def create_manager_waiver(self, db: Session, waiver_in: AdjustmentWaiverCreate,
                              manager_id: int) -> AdjustmentRequest:
        payroll_service.validate_period_open(db, waiver_in.target_date)
        self._validate_waiver_limit(db, waiver_in.user_id, waiver_in.target_date, waiver_in.amount_hours)

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
            db, user_id=manager_id, action="CREATE_WAIVER",
            entity="ADJUSTMENT", entity_id=adjustment.id,
            new_data={
                "target_date": str(waiver_in.target_date),
                "amount_hours": waiver_in.amount_hours,
                "reason": waiver_in.reason_text
            }
        )
        return self._enrich_adjustments_with_records(db, [adjustment])[0]

    def admin_delete_adjustment(self, db: Session, adjustment_id: int, admin_id: int, reason: str) -> None:
        request = adjustment_repository.get(db, adjustment_id)
        if not request:
            raise HTTPException(status_code=404, detail="Abono não encontrado.")
        payroll_service.validate_period_open(db, request.target_date)

        if request.adjustment_type not in [AdjustmentType.EXTRA_TIME, AdjustmentType.WAIVER]:
            raise HTTPException(
                status_code=400,
                detail="Apenas ajustes do tipo EXTRA_TIME e WAIVER podem ser excluídos."
            )

        old_data = {
            "type": request.adjustment_type.value,
            "target_date": str(request.target_date),
            "status": request.status.value
        }
        
        if request.status == AdjustmentStatus.APPROVED:
            self._revert_adjustment_action(db, request, admin_id)

        adjustment_repository.soft_delete(db, adjustment_id, admin_id)

        audit_service.log(
            db, user_id=admin_id, action="DELETE_ADJUSTMENT",
            entity="ADJUSTMENT", entity_id=adjustment_id, old_data=old_data,
            new_data={"reason": reason}
        )

    def delete_adjustment(self, db: Session, adjustment_id: int, manager_id: int, reason: str) -> None:
        request = adjustment_repository.get(db, adjustment_id)
        if not request:
            raise HTTPException(status_code=404, detail="Abono não encontrado.")
        payroll_service.validate_period_open(db, request.target_date)

        if request.adjustment_type not in [AdjustmentType.EXTRA_TIME, AdjustmentType.WAIVER]:
            raise HTTPException(
                status_code=400,
                detail="Apenas ajustes do tipo EXTRA_TIME e WAIVER podem ser excluídos."
            )

        old_data = {
            "type": request.adjustment_type.value,
            "target_date": str(request.target_date),
            "status": request.status.value
        }
        
        if request.status == AdjustmentStatus.APPROVED:
            self._revert_adjustment_action(db, request, manager_id)

        adjustment_repository.soft_delete(db, adjustment_id, manager_id)

        audit_service.log(
            db, user_id=manager_id, action="DELETE_ADJUSTMENT",
            entity="ADJUSTMENT", entity_id=adjustment_id, old_data=old_data,
            new_data={"reason": reason}
        )

    def upload_attachment(self, db: Session, request_id: int, file: UploadFile, user_id: int):
        request = adjustment_repository.get(db, request_id)
        if not request:
            raise HTTPException(status_code=404, detail="Solicitação de abono não encontrada.")

        if request.user_id != user_id:
            raise HTTPException(status_code=403, detail="Acesso negado.")

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

        if (
                (file_ext == "pdf" and header.startswith(b"%PDF")) or
                (file_ext == "png" and header.startswith(b"\x89PNG\r\n\x1a\n")) or
                (file_ext in ["jpg", "jpeg"] and header.startswith(b"\xff\xd8\xff"))
        ):
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

        attachment = adjustment_repository.create_attachment(db, request_id, safe_filename, file.content_type)

        audit_service.log(
            db, user_id=user_id, action="UPLOAD_ATTACHMENT",
            entity="ADJUSTMENT", entity_id=request_id,
            new_data={"file_name": safe_filename, "file_type": file.content_type}
        )
        return attachment

    def approve_adjustment(self, db: Session, request_id: int, manager_id: int,
                           comment: str | None = None) -> AdjustmentRequest:
        request = adjustment_repository.get(db, request_id)
        if not request:
            raise HTTPException(status_code=404, detail=NOT_FOUND_MSG)
        payroll_service.validate_period_open(db, request.target_date)

        if request.adjustment_type == AdjustmentType.WAIVER:
            if not request.attachments:
                raise HTTPException(status_code=400, detail="Para aprovar um abono, é obrigatório haver anexo.")
        elif request.adjustment_type != AdjustmentType.EXTRA_TIME:
            self._execute_adjustment_action(db, request, manager_id)

        old_status = request.status.value
        updated = adjustment_repository.update_status(db, request, AdjustmentStatus.APPROVED, manager_id, comment)

        old_data = {"status": old_status}
        new_data_raw = {"status": updated.status.value, "comment": comment}
        actual_old, actual_new = audit_service.compute_diffs(old_data, new_data_raw)

        audit_service.log(
            db, user_id=manager_id, action="APPROVE_ADJUSTMENT",
            entity="ADJUSTMENT", entity_id=request_id,
            old_data=actual_old, new_data=actual_new
        )
        return self._enrich_adjustments_with_records(db, [updated])[0]

    def _execute_adjustment_action(self, db: Session, request: AdjustmentRequest, manager_id: int):
        target_dt = datetime.combine(request.target_date, request.time)
        if request.adjustment_type == AdjustmentType.DELETE_PUNCH:
            start_dt = target_dt.replace(second=0, microsecond=0)
            end_dt = target_dt.replace(second=59, microsecond=999999)

            record = db.query(TimeRecord).filter(
                TimeRecord.user_id == request.user_id,
                TimeRecord.record_type == request.record_type,
                TimeRecord.record_datetime >= start_dt,
                TimeRecord.record_datetime <= end_dt,
                TimeRecord.is_ignored == False
            ).first()
            if record:
                record.is_ignored = True
                record.deleted_at = get_local_time()
                record.deleted_by = manager_id
                
                db.query(AdjustmentRequest).filter(
                    AdjustmentRequest.user_id == request.user_id,
                    AdjustmentRequest.target_date == request.target_date,
                    AdjustmentRequest.adjustment_type == AdjustmentType.EXTRA_TIME,
                    AdjustmentRequest.status.in_([AdjustmentStatus.PENDING, AdjustmentStatus.REJECTED])
                ).delete(synchronize_session=False)
                
                db.commit()
        else:
            time_record_repository.create(
                db, user_id=request.user_id, record_type=request.record_type,
                record_datetime=target_dt, ip_address="ADJUSTMENT_APPROVED"
            )

    def reject_adjustment(self, db: Session, request_id: int, manager_id: int, comment: str) -> AdjustmentRequest:
        request = adjustment_repository.get(db, request_id)
        if not request:
            raise HTTPException(status_code=404, detail=NOT_FOUND_MSG)
        payroll_service.validate_period_open(db, request.target_date)

        old_status = request.status.value
        updated = adjustment_repository.update_status(db, request, AdjustmentStatus.REJECTED, manager_id, comment)

        old_data = {"status": old_status}
        new_data_raw = {"status": updated.status.value, "comment": comment}
        actual_old, actual_new = audit_service.compute_diffs(old_data, new_data_raw)

        audit_service.log(
            db, user_id=manager_id, action="REJECT_ADJUSTMENT",
            entity="ADJUSTMENT", entity_id=request_id,
            old_data=actual_old, new_data=actual_new
        )
        return self._enrich_adjustments_with_records(db, [updated])[0]

    def _revert_adjustment_action(self, db: Session, request: AdjustmentRequest, manager_id: int):
        if request.adjustment_type in [AdjustmentType.EXTRA_TIME, AdjustmentType.WAIVER]:
            return
            
        target_dt = datetime.combine(request.target_date, request.time)
        if request.adjustment_type == AdjustmentType.DELETE_PUNCH:
            start_dt = target_dt.replace(second=0, microsecond=0)
            end_dt = target_dt.replace(second=59, microsecond=999999)

            record = db.query(TimeRecord).filter(
                TimeRecord.user_id == request.user_id,
                TimeRecord.record_type == request.record_type,
                TimeRecord.record_datetime >= start_dt,
                TimeRecord.record_datetime <= end_dt,
                TimeRecord.is_ignored == True
            ).order_by(TimeRecord.deleted_at.desc()).first()
            if record:
                record.is_ignored = False
                record.deleted_at = None
                record.deleted_by = None
                db.commit()
        elif request.adjustment_type in [AdjustmentType.FORGOT_PUNCH, AdjustmentType.PUNCH_NOT_COUNTED]:
            start_dt = target_dt.replace(second=0, microsecond=0)
            end_dt = target_dt.replace(second=59, microsecond=999999)
            
            record = db.query(TimeRecord).filter(
                TimeRecord.user_id == request.user_id,
                TimeRecord.record_type == request.record_type,
                TimeRecord.record_datetime >= start_dt,
                TimeRecord.record_datetime <= end_dt,
                TimeRecord.is_ignored == False,
                TimeRecord.ip_address == "ADJUSTMENT_APPROVED"
            ).first()
            if record:
                record.is_ignored = True
                record.deleted_at = get_local_time()
                record.deleted_by = manager_id
                db.commit()

    def revert_adjustment_status(self, db: Session, request_id: int, manager_id: int, new_status: AdjustmentStatus, comment: str) -> AdjustmentRequest:
        request = adjustment_repository.get(db, request_id)
        if not request:
            raise HTTPException(status_code=404, detail=NOT_FOUND_MSG)
            
        payroll_service.validate_period_open(db, request.target_date)

        old_status = request.status
        
        if old_status == new_status:
            return self._enrich_adjustments_with_records(db, [request])[0]

        if old_status == AdjustmentStatus.APPROVED and new_status in [AdjustmentStatus.PENDING, AdjustmentStatus.REJECTED]:
            self._revert_adjustment_action(db, request, manager_id)
            
        elif old_status in [AdjustmentStatus.PENDING, AdjustmentStatus.REJECTED] and new_status == AdjustmentStatus.APPROVED:
            if request.adjustment_type not in [AdjustmentType.WAIVER, AdjustmentType.EXTRA_TIME]:
                self._execute_adjustment_action(db, request, manager_id)

        updated = adjustment_repository.update_status(db, request, new_status, manager_id, comment)

        actual_old, actual_new = audit_service.compute_diffs({"status": old_status.value}, {"status": updated.status.value, "comment": comment})

        audit_service.log(
            db, user_id=manager_id, action="REVERT_ADJUSTMENT",
            entity="ADJUSTMENT", entity_id=request_id,
            old_data=actual_old, new_data=actual_new
        )
        return self._enrich_adjustments_with_records(db, [updated])[0]

adjustment_service = AdjustmentService()
