from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.features.holidays.holiday_exceptions import HolidayAlreadyExistsError
from app.features.holidays.holiday_models import Holiday
from app.features.holidays.holiday_repository import HolidayRepository, holiday_repository
from app.features.holidays.holiday_schemas import HolidayCreate
from app.features.payroll.payroll_service import payroll_service
from app.features.system.audit_service import audit_service
from app.shared import deps


class HolidayService:
    def __init__(
        self,
        db: Annotated[Session, Depends(deps.get_db)] = None,
        repo: Annotated[HolidayRepository, Depends()] = None,
    ):
        self.db = db
        self.repo = repo if repo is not None else holiday_repository

    def create_holiday(
            self,
            db: Session | None = None,
            holiday_in: HolidayCreate | None = None,
            current_user_id: int = 0,
    ) -> Holiday:
        session = db if db is not None else self.db
        assert session is not None
        assert holiday_in is not None
        payroll_service.validate_period_open(session, holiday_in.date)
        if self.repo.get_by_date(session, holiday_in.date):
            raise HolidayAlreadyExistsError(date_str=holiday_in.date.strftime("%d/%m/%Y"))

        holiday = self.repo.create(session, obj_in=holiday_in)
        audit_service.log_change(session, current_user_id, "CREATE", new_model=holiday)
        return holiday

    def get_all_holidays(self, db: Session | None = None) -> list[Holiday]:
        session = db if db is not None else self.db
        assert session is not None
        return self.repo.get_all(session)

    def delete_holiday(
            self,
            db: Session | None = None,
            holiday_id: int = 0,
            current_user_id: int = 0,
    ) -> dict[str, str]:
        session = db if db is not None else self.db
        assert session is not None
        holiday = self.repo.get_by_id(session, holiday_id)
        if holiday:
            payroll_service.validate_period_open(session, holiday.date)
            self.repo.delete(session, holiday_id)
            audit_service.log_change(session, current_user_id, "DELETE", old_model=holiday)
        return {"status": "success"}


holiday_service = HolidayService()
