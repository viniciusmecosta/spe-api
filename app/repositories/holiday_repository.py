from typing import List
from datetime import date
from sqlalchemy.orm import Session
from app.domain.models.holiday import Holiday
from app.schemas.holiday import HolidayCreate


class HolidayRepository:
    def create(self, db: Session, obj_in: HolidayCreate) -> Holiday:
        db_obj = Holiday(date=obj_in.date, name=obj_in.name)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get_all(self, db: Session) -> List[Holiday]:
        return db.query(Holiday).order_by(Holiday.date).all()

    def get_by_date(self, db: Session, check_date: date) -> Holiday | None:
        return db.query(Holiday).filter(Holiday.date == check_date).first()

    def get_by_month(self, db: Session, month: int, year: int) -> List[Holiday]:
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1)
        else:
            end_date = date(year, month + 1, 1)

        return db.query(Holiday).filter(Holiday.date >= start_date, Holiday.date < end_date).all()

    def delete(self, db: Session, id: int):
        obj = db.query(Holiday).filter(Holiday.id == id).first()
        if obj:
            db.delete(obj)
            db.commit()


holiday_repository = HolidayRepository()