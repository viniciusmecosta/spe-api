from sqlalchemy.orm import Session
from typing import List

from app.domain.models.payroll import PayrollClosure


class PayrollRepository:
    def create(self, db: Session, month: int, year: int, user_id: int) -> PayrollClosure:
        db_obj = PayrollClosure(month=month, year=year, is_closed=True, closed_by_user_id=user_id)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get_by_month(self, db: Session, month: int, year: int) -> PayrollClosure | None:
        return db.query(PayrollClosure).filter(
            PayrollClosure.month == month,
            PayrollClosure.year == year
        ).first()

    def get_all(self, db: Session) -> List[PayrollClosure]:
        return db.query(PayrollClosure).order_by(
            PayrollClosure.year.desc(),
            PayrollClosure.month.desc()
        ).all()

    def delete(self, db: Session, month: int, year: int):
        db.query(PayrollClosure).filter(
            PayrollClosure.month == month,
            PayrollClosure.year == year
        ).delete()
        db.commit()


payroll_repository = PayrollRepository()