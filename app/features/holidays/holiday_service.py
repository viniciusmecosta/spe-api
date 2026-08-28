from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_async_db
from app.features.holidays.holiday_exceptions import HolidayAlreadyExistsError
from app.features.holidays.holiday_models import Holiday
from app.features.holidays.holiday_repository import AsyncHolidayRepository, async_holiday_repository
from app.features.holidays.holiday_schemas import HolidayCreate
from app.features.payroll.payroll_service import payroll_service
from app.features.system.audit_service import audit_service


class HolidayService:
    def __init__(
        self,
            db: Annotated[AsyncSession, Depends(get_async_db)] = None,
            repo: Annotated[AsyncHolidayRepository, Depends()] = None,
    ):
        self.db = db
        self._repo = repo

    @property
    def repo(self) -> AsyncHolidayRepository:
        return self._repo if self._repo is not None else async_holiday_repository

    @repo.setter
    def repo(self, value: AsyncHolidayRepository) -> None:
        self._repo = value

    async def create_holiday(
            self,
            db: AsyncSession | None = None,
            holiday_in: HolidayCreate | None = None,
            current_user_id: int = 0,
    ) -> Holiday:
        session = db if db is not None else self.db
        assert session is not None
        assert holiday_in is not None
        await payroll_service.async_validate_period_open(session, holiday_in.date)
        if await self.repo.get_by_date(session, holiday_in.date):
            raise HolidayAlreadyExistsError(date_str=holiday_in.date.strftime("%d/%m/%Y"))

        holiday = await self.repo.create(session, obj_in=holiday_in)
        await audit_service.async_log_change(session, current_user_id, "CREATE", new_model=holiday)
        return holiday

    async def get_all_holidays(self, db: AsyncSession | None = None) -> list[Holiday]:
        session = db if db is not None else self.db
        assert session is not None
        return await self.repo.get_all(session)

    async def delete_holiday(
            self,
            db: AsyncSession | None = None,
            holiday_id: int = 0,
            current_user_id: int = 0,
    ) -> dict[str, str]:
        session = db if db is not None else self.db
        assert session is not None
        holiday = await self.repo.get_by_id(session, holiday_id)
        if holiday:
            await payroll_service.async_validate_period_open(session, holiday.date)
            await self.repo.delete(session, holiday_id)
            await audit_service.async_log_change(session, current_user_id, "DELETE", old_model=holiday)
        return {"status": "success"}


holiday_service = HolidayService()
