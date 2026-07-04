from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.repositories.routine_log_repository import routine_log_repository


class RoutineLogService:
    def get_logs(self, db: Session, routine_type: Optional[str] = None, status: Optional[str] = None,
                 start_date: Optional[date] = None, end_date: Optional[date] = None,
                 order_by: str = "desc", skip: int = 0, limit: int = 100):
        return routine_log_repository.get_logs(
            db, routine_type=routine_type, status=status, start_date=start_date, end_date=end_date,
            order_by=order_by, skip=skip, limit=limit
        )


routine_log_service = RoutineLogService()
