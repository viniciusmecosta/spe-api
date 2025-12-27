from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.domain.models.adjustment import AdjustmentRequest
from app.schemas.adjustment import AdjustmentRequestCreate

class AdjustmentRepository:
    def create(self, db: Session, user_id: int, obj_in: AdjustmentRequestCreate) -> AdjustmentRequest:
        db_obj = AdjustmentRequest(
            user_id=user_id,
            adjustment_type=obj_in.adjustment_type,
            target_date=obj_in.target_date,
            entry_time=obj_in.entry_time,
            exit_time=obj_in.exit_time,
            reason_text=obj_in.reason_text,
            # Status padrão é PENDING (definido no model)
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get_all_by_user(self, db: Session, user_id: int, skip: int = 0, limit: int = 100) -> list[AdjustmentRequest]:
        return db.query(AdjustmentRequest)\
            .filter(AdjustmentRequest.user_id == user_id)\
            .order_by(desc(AdjustmentRequest.created_at))\
            .offset(skip)\
            .limit(limit)\
            .all()

adjustment_repository = AdjustmentRepository()