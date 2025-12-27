from datetime import datetime
import pytz
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.repositories.adjustment_repository import adjustment_repository
from app.schemas.adjustment import AdjustmentRequestCreate
from app.domain.models.adjustment import AdjustmentRequest
from app.domain.models.enums import AdjustmentStatus
from app.core.config import settings
from app.services.audit_service import audit_service


class AdjustmentService:
    def create_request(self, db: Session, user_id: int, request_in: AdjustmentRequestCreate) -> AdjustmentRequest:
        return adjustment_repository.create(db, user_id, request_in)

    def review_request(self, db: Session, request_id: int, manager_id: int, new_status: AdjustmentStatus,
                       comment: str | None = None) -> AdjustmentRequest:
        request = adjustment_repository.get(db, request_id)
        if not request:
            raise HTTPException(status_code=404, detail="Adjustment request not found")

        if request.status != AdjustmentStatus.PENDING:
            raise HTTPException(status_code=400, detail="Request is already reviewed")

        tz = pytz.timezone(settings.TIMEZONE)
        request.reviewed_at = datetime.now(tz)

        updated_request = adjustment_repository.update_status(db, request, new_status, manager_id, comment)

        audit_service.log(
            db,
            user_id=manager_id,
            action="REVIEW_ADJUSTMENT",
            entity="ADJUSTMENT_REQUEST",
            entity_id=updated_request.id,
            details=f"Status set to {new_status}. Comment: {comment}"
        )

        return updated_request


adjustment_service = AdjustmentService()