from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.repository import BaseRepository
from app.features.holidays.holiday_models import Holiday
from app.features.holidays.holiday_schemas import HolidayCreate


class HolidayRepository(BaseRepository[Holiday, HolidayCreate, HolidayCreate]):
    def __init__(self):
        super().__init__(Holiday)

    def create(self, db: Session, obj_in: HolidayCreate) -> Holiday:
        return super().create(db, obj_in=obj_in)

    def get_all(self, db: Session) -> list[Holiday]:
        stmt = select(Holiday).order_by(Holiday.date)
        return list(db.scalars(stmt).all())

    def get_by_date(self, db: Session, check_date: date) -> Holiday | None:
        stmt = select(Holiday).where(Holiday.date == check_date)
        return db.scalars(stmt).first()

    def get_by_id(self, db: Session, id: int) -> Holiday | None:
        return super().get(db, id)

    def get_by_month(self, db: Session, month: int, year: int) -> list[Holiday]:
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1)
        else:
            end_date = date(year, month + 1, 1)

        stmt = select(Holiday).where(Holiday.date >= start_date, Holiday.date < end_date)
        return list(db.scalars(stmt).all())

    def delete(self, db: Session, id: int):
        super().remove(db, id=id)


holiday_repository = HolidayRepository()
