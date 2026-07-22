from datetime import date

from sqlalchemy import desc, and_, func
from sqlalchemy.orm import Session

from app.domain.models.adjustment import AdjustmentRequest, AdjustmentAttachment, get_local_time
from app.domain.models.enums import AdjustmentStatus, AdjustmentType
from app.schemas.adjustment import AdjustmentRequestCreate


class AdjustmentRepository:
    def create(self, db: Session, user_id: int, obj_in: AdjustmentRequestCreate) -> AdjustmentRequest:
        db_obj = AdjustmentRequest(
            user_id=user_id,
            adjustment_type=obj_in.adjustment_type,
            record_type=obj_in.record_type,
            target_date=obj_in.target_date,
            time=obj_in.time,
            amount_hours=obj_in.amount_hours,
            reason_text=obj_in.reason_text
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get(self, db: Session, id: int) -> AdjustmentRequest | None:
        return db.query(AdjustmentRequest).filter(AdjustmentRequest.id == id, AdjustmentRequest.deleted_at.is_(None)).first()

    def get_all_by_user(
        self, 
        db: Session, 
        user_id: int, 
        skip: int = 0, 
        limit: int = 100,
        month: int | None = None,
        year: int | None = None,
        status: str | None = None,
        order_by: str = "created_at",
        order_direction: str = "desc"
    ) -> list[AdjustmentRequest]:
        query = db.query(AdjustmentRequest).filter(AdjustmentRequest.user_id == user_id, AdjustmentRequest.deleted_at.is_(None))
        
        if month and year:
            query = query.filter(
                func.extract('month', AdjustmentRequest.target_date) == month,
                func.extract('year', AdjustmentRequest.target_date) == year
            )
        elif year:
            query = query.filter(func.extract('year', AdjustmentRequest.target_date) == year)
            
        if status:
            if status.upper() == "NOT_PENDING":
                query = query.filter(AdjustmentRequest.status != AdjustmentStatus.PENDING)
            else:
                query = query.filter(AdjustmentRequest.status == AdjustmentStatus(status.upper()))
            
        order_column = AdjustmentRequest.target_date if order_by == "target_date" else func.coalesce(AdjustmentRequest.reviewed_at, AdjustmentRequest.created_at)
        query = query.order_by(desc(order_column) if order_direction == "desc" else order_column)
            
        return query.offset(skip).limit(limit).all()

    def get_all(
        self, 
        db: Session, 
        skip: int = 0, 
        limit: int = 100,
        month: int | None = None,
        year: int | None = None,
        status: str | None = None,
        order_by: str = "created_at",
        order_direction: str = "desc"
    ) -> list[AdjustmentRequest]:
        query = db.query(AdjustmentRequest).filter(AdjustmentRequest.deleted_at.is_(None))
        
        if month and year:
            query = query.filter(
                func.extract('month', AdjustmentRequest.target_date) == month,
                func.extract('year', AdjustmentRequest.target_date) == year
            )
        elif year:
            query = query.filter(func.extract('year', AdjustmentRequest.target_date) == year)
            
        if status:
            if status.upper() == "NOT_PENDING":
                query = query.filter(AdjustmentRequest.status != AdjustmentStatus.PENDING)
            else:
                query = query.filter(AdjustmentRequest.status == AdjustmentStatus(status.upper()))
            
        order_column = AdjustmentRequest.target_date if order_by == "target_date" else func.coalesce(AdjustmentRequest.reviewed_at, AdjustmentRequest.created_at)
        query = query.order_by(desc(order_column) if order_direction == "desc" else order_column)
            
        return query.offset(skip).limit(limit).all()

    def count_pending(self, db: Session) -> int:
        return db.query(AdjustmentRequest).filter(AdjustmentRequest.status == AdjustmentStatus.PENDING, AdjustmentRequest.deleted_at.is_(None)).count()

    def get_approved_by_range(self, db: Session, user_id: int, start_date: date, end_date: date) -> list[
        AdjustmentRequest]:
        return db.query(AdjustmentRequest).filter(
            and_(
                AdjustmentRequest.user_id == user_id,
                AdjustmentRequest.status == AdjustmentStatus.APPROVED,
                AdjustmentRequest.target_date >= start_date,
                AdjustmentRequest.target_date <= end_date,
                AdjustmentRequest.deleted_at.is_(None)
            )
        ).all()

    def get_waivers_by_user_and_date(self, db: Session, user_id: int, target_date: date) -> list[AdjustmentRequest]:
        return db.query(AdjustmentRequest).filter(
            and_(
                AdjustmentRequest.user_id == user_id,
                AdjustmentRequest.target_date == target_date,
                AdjustmentRequest.adjustment_type == AdjustmentType.WAIVER,
                AdjustmentRequest.status.in_([AdjustmentStatus.PENDING, AdjustmentStatus.APPROVED]),
                AdjustmentRequest.deleted_at.is_(None)
            )
        ).all()

    def update_status(self, db: Session, db_obj: AdjustmentRequest, status: AdjustmentStatus, manager_id: int,
                      comment: str | None = None) -> AdjustmentRequest:
        db_obj.status = status
        db_obj.manager_id = manager_id
        db_obj.manager_comment = comment
        db_obj.reviewed_at = get_local_time()
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

    def soft_delete(self, db: Session, id: int, user_id: int):
        db_obj = self.get(db, id)
        if db_obj:
            db_obj.deleted_at = get_local_time()
            db_obj.deleted_by = user_id
            db.add(db_obj)
            db.commit()

    def delete(self, db: Session, id: int):
        db.query(AdjustmentRequest).filter(AdjustmentRequest.id == id).delete()
        db.commit()


adjustment_repository = AdjustmentRepository()
