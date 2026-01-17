from datetime import datetime
import pytz
from sqlalchemy.orm import Session
from app.domain.models.manual_authorization import ManualPunchAuthorization
from app.schemas.manual_auth import ManualPunchAuthCreate
from app.core.config import settings


class ManualAuthService:
    def create_authorization(self, db: Session, auth_in: ManualPunchAuthCreate,
                             manager_id: int) -> ManualPunchAuthorization:
        """
        Cria uma nova janela de autorização para registro manual.
        """
        # Garante que as datas estejam coerentes
        if auth_in.valid_until <= auth_in.valid_from:
            raise ValueError("A data de término deve ser posterior ao início.")

        db_auth = ManualPunchAuthorization(
            user_id=auth_in.user_id,
            authorized_by=manager_id,
            valid_from=auth_in.valid_from,
            valid_until=auth_in.valid_until,
            reason=auth_in.reason
        )
        db.add(db_auth)
        db.commit()
        db.refresh(db_auth)
        return db_auth

    def check_authorization(self, db: Session, user_id: int) -> bool:
        """
        Verifica se o usuário possui uma autorização ativa AGORA.
        """
        tz = pytz.timezone(settings.TIMEZONE)
        now = datetime.now(tz)

        auth = db.query(ManualPunchAuthorization).filter(
            ManualPunchAuthorization.user_id == user_id,
            ManualPunchAuthorization.valid_from <= now,
            ManualPunchAuthorization.valid_until >= now
        ).first()

        return auth is not None


manual_auth_service = ManualAuthService()