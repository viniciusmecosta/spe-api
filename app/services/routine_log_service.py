from datetime import date

from sqlalchemy.orm import Session

from app.repositories.routine_log_repository import routine_log_repository


class RoutineLogService:
    def get_logs(self, db: Session, routine_type: str | None = None, status: str | None = None,
                 start_date: date | None = None, end_date: date | None = None,
                 order_by: str = "desc", skip: int = 0, limit: int = 100):
        return routine_log_repository.get_logs(
            db, routine_type=routine_type, status=status, start_date=start_date, end_date=end_date,
            order_by=order_by, skip=skip, limit=limit
        )


routine_log_service = RoutineLogService()
