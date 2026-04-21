from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.models.manual_authorization import ManualPunchAuthorization
from app.services.audit_service import audit_service


class ManualAuthService:
    def grant_permission(self, db: Session, user_id: int, manager_id: int) -> ManualPunchAuthorization:
        self.revoke_permission(db, user_id, manager_id)

        tz = ZoneInfo(settings.TIMEZONE)
        now = datetime.now(tz)
        valid_until = now + timedelta(days=3650)

        db_auth = ManualPunchAuthorization(
            user_id=user_id,
            authorized_by=manager_id,
            valid_from=now,
            valid_until=valid_until,
            reason="Autorizacao permanente concedida pelo gestor"
        )
        db.add(db_auth)
        db.commit()
        db.refresh(db_auth)

        audit_service.log(
            db, actor_id=manager_id, target_user_id=user_id, action="GRANT", entity="MANUAL_AUTH",
            entity_id=db_auth.id, new_data={"valid_until": str(valid_until)}
        )
        return db_auth

    def revoke_permission(self, db: Session, user_id: int, manager_id: int = None):
        existing = db.query(ManualPunchAuthorization).filter(
            ManualPunchAuthorization.user_id == user_id
        ).first()

        if existing:
            db.delete(existing)
            db.commit()

            if manager_id:
                audit_service.log(
                    db, actor_id=manager_id, target_user_id=user_id, action="REVOKE", entity="MANUAL_AUTH"
                )

    def check_authorization(self, db: Session, user_id: int) -> bool:
        tz = ZoneInfo(settings.TIMEZONE)
        now = datetime.now(tz)

        auth = db.query(ManualPunchAuthorization).filter(
            ManualPunchAuthorization.user_id == user_id,
            ManualPunchAuthorization.valid_from <= now,
            ManualPunchAuthorization.valid_until >= now
        ).first()

        return auth is not None


manual_auth_service = ManualAuthService()