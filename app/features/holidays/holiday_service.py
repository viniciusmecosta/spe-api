from sqlalchemy.orm import Session

from app.features.holidays.holiday_exceptions import HolidayAlreadyExistsError
from app.features.holidays.holiday_models import Holiday
from app.features.holidays.holiday_repository import holiday_repository
from app.features.holidays.holiday_schemas import HolidayCreate
from app.features.payroll.payroll_service import payroll_service
from app.features.system.audit_service import audit_service


class HolidayService:
    def create_holiday(
            self,
            db: Session,
            holiday_in: HolidayCreate,
            current_user_id: int,
    ) -> Holiday:
        payroll_service.validate_period_open(db, holiday_in.date)
        if holiday_repository.get_by_date(db, holiday_in.date):
            raise HolidayAlreadyExistsError()

        holiday = holiday_repository.create(db, holiday_in)
        audit_service.log_change(db, current_user_id, "CREATE", new_model=holiday)
        return holiday

    def get_all_holidays(self, db: Session) -> list[Holiday]:
        return holiday_repository.get_all(db)

    def delete_holiday(
            self,
            db: Session,
            holiday_id: int,
            current_user_id: int,
    ) -> dict[str, str]:
        holiday = holiday_repository.get_by_id(db, holiday_id)
        if holiday:
            payroll_service.validate_period_open(db, holiday.date)
            holiday_repository.delete(db, holiday_id)
            audit_service.log_change(db, current_user_id, "DELETE", old_model=holiday)
        return {"status": "success"}


holiday_service = HolidayService()
