from datetime import datetime, timedelta
import pytz
from sqlalchemy.orm import Session
from app.domain.models.manual_authorization import ManualPunchAuthorization
from app.core.config import settings


class ManualAuthService:
    def grant_permission(self, db: Session, user_id: int, manager_id: int) -> ManualPunchAuthorization:
        self.revoke_permission(db, user_id)

        tz = pytz.timezone(settings.TIMEZONE)
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
        return db_auth

    def revoke_permission(self, db: Session, user_id: int):
        db.query(ManualPunchAuthorization).filter(
            ManualPunchAuthorization.user_id == user_id
        ).delete()
        db.commit()

    def check_authorization(self, db: Session, user_id: int) -> bool:
        tz = pytz.timezone(settings.TIMEZONE)
        now = datetime.now(tz)

        auth = db.query(ManualPunchAuthorization).filter(
            ManualPunchAuthorization.user_id == user_id,
            ManualPunchAuthorization.valid_from <= now,
            ManualPunchAuthorization.valid_until >= now
        ).first()

        return auth is not None


manual_auth_service = ManualAuthService()