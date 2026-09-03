from datetime import date
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.system.system_repository import (
    AsyncRoutineLogRepository,
    async_routine_log_repository,
    routine_log_repository,
)
from app.shared import deps


class RoutineLogService:
    def __init__(
        self,
            db: Annotated[AsyncSession, Depends(deps.get_async_db)] = None,
            repo: Annotated[AsyncRoutineLogRepository, Depends()] = None,
    ):
        self.db = db
        self._repo = repo

    @property
    def repo(self) -> AsyncRoutineLogRepository:
        return self._repo if self._repo is not None else async_routine_log_repository

    async def get_logs(
            self,
            db: AsyncSession | None = None,
            routine_type: str | None = None,
            status: str | None = None,
            start_date: date | None = None,
            end_date: date | None = None,
            order_by: str = "desc",
            skip: int = 0,
            limit: int = 100,
    ):
        session = db if db is not None else self.db
        assert session is not None
        if hasattr(session, "sync_session"):
            return await self.repo.get_logs(
                session, routine_type=routine_type, status=status, start_date=start_date, end_date=end_date,
                order_by=order_by, skip=skip, limit=limit
            )
        return routine_log_repository.get_logs(
            session, routine_type=routine_type, status=status, start_date=start_date, end_date=end_date,
            order_by=order_by, skip=skip, limit=limit
        )
