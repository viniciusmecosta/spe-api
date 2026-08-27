from datetime import date
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.features.system.system_repository import routine_log_repository
from app.shared import deps


class RoutineLogService:
    def __init__(self, db: Annotated[Session, Depends(deps.get_db)] = None):
        self.db = db

    def get_logs(self, db: Session | None = None, routine_type: str | None = None, status: str | None = None,
                 start_date: date | None = None, end_date: date | None = None,
                 order_by: str = "desc", skip: int = 0, limit: int = 100):
        session = db if db is not None else self.db
        assert session is not None
        return routine_log_repository.get_logs(
            session, routine_type=routine_type, status=status, start_date=start_date, end_date=end_date,
            order_by=order_by, skip=skip, limit=limit
        )


routine_log_service = RoutineLogService()
