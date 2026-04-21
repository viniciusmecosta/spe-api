from datetime import date, datetime, time
from typing import List, Optional

from sqlalchemy import asc, desc
from sqlalchemy.orm import Session

from app.domain.models.routine_log import RoutineLog


class RoutineLogRepository:
    def get_logs(
            self,
            db: Session,
            routine_type: Optional[str] = None,
            status: Optional[str] = None,
            start_date: Optional[date] = None,
            end_date: Optional[date] = None,
            order_by: str = "desc",
            skip: int = 0,
            limit: int = 100
    ) -> List[RoutineLog]:
        query = db.query(RoutineLog)

        if routine_type:
            query = query.filter(RoutineLog.routine_type == routine_type)

        if status:
            query = query.filter(RoutineLog.status == status)

        if start_date:
            start_dt = datetime.combine(start_date, time.min)
            query = query.filter(RoutineLog.execution_time >= start_dt)

        if end_date:
            end_dt = datetime.combine(end_date, time.max)
            query = query.filter(RoutineLog.execution_time <= end_dt)

        if order_by == "asc":
            query = query.order_by(asc(RoutineLog.execution_time))
        else:
            query = query.order_by(desc(RoutineLog.execution_time))

        return query.offset(skip).limit(limit).all()


routine_log_repository = RoutineLogRepository()
