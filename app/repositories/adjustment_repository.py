from datetime import date

from sqlalchemy import desc, and_
from sqlalchemy.orm import Session

from app.domain.models.adjustment import AdjustmentRequest, AdjustmentAttachment
from app.domain.models.enums import AdjustmentStatus
from app.schemas.adjustment import AdjustmentRequestCreate, AdjustmentRequestUpdate


class AdjustmentRepository:
    def create(self, db: Session, user_id: int, obj_in: AdjustmentRequestCreate) -> AdjustmentRequest:
        db_obj = AdjustmentRequest(
            user_id=user_id,
            adjustment_type=obj_in.adjustment_type,
            target_date=obj_in.target_date,
            entry_time=obj_in.entry_time,
            exit_time=obj_in.exit_time,
            reason_text=obj_in.reason_text,
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get(self, db: Session, id: int) -> AdjustmentRequest | None:
        return db.query(AdjustmentRequest).filter(AdjustmentRequest.id == id).first()

    def get_all_by_user(self, db: Session, user_id: int, skip: int = 0, limit: int = 100) -> list[AdjustmentRequest]:
        return db.query(AdjustmentRequest) \
            .filter(AdjustmentRequest.user_id == user_id) \
            .order_by(desc(AdjustmentRequest.created_at)) \
            .offset(skip) \
            .limit(limit) \
            .all()

    def get_all(self, db: Session, skip: int = 0, limit: int = 100) -> list[AdjustmentRequest]:
        return db.query(AdjustmentRequest) \
            .order_by(desc(AdjustmentRequest.created_at)) \
            .offset(skip) \
            .limit(limit) \
            .all()

    def count_pending(self, db: Session) -> int:
        return db.query(AdjustmentRequest).filter(AdjustmentRequest.status == AdjustmentStatus.PENDING).count()

    def get_approved_by_range(self, db: Session, user_id: int, start_date: date, end_date: date) -> list[
        AdjustmentRequest]:
        return db.query(AdjustmentRequest).filter(
            and_(
                AdjustmentRequest.user_id == user_id,
                AdjustmentRequest.status == AdjustmentStatus.APPROVED,
                AdjustmentRequest.target_date >= start_date,
                AdjustmentRequest.target_date <= end_date
            )
        ).all()

    def update(self, db: Session, db_obj: AdjustmentRequest,
               obj_in: AdjustmentRequestUpdate | dict) -> AdjustmentRequest:
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(db_obj, field, value)

        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update_status(self, db: Session, db_obj: AdjustmentRequest, status: AdjustmentStatus, manager_id: int,
                      comment: str | None = None) -> AdjustmentRequest:
        db_obj.status = status
        db_obj.manager_id = manager_id
        db_obj.manager_comment = comment
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def create_attachment(self, db: Session, request_id: int, file_path: str, file_type: str) -> AdjustmentAttachment:
        db_attachment = AdjustmentAttachment(
            adjustment_request_id=request_id,
            file_path=file_path,
            file_type=file_type
        )
        db.add(db_attachment)
        db.commit()
        db.refresh(db_attachment)
        return db_attachment


adjustment_repository = AdjustmentRepository()
