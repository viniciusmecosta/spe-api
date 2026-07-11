from datetime import datetime
from typing import List

from sqlalchemy.orm import Session

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
            PayrollClosure.year == year,
            PayrollClosure.deleted_at.is_(None)
        ).first()

    def get_all(self, db: Session, year: int = None) -> List[PayrollClosure]:
        query = db.query(PayrollClosure).filter(PayrollClosure.deleted_at.is_(None))
        if year:
            query = query.filter(PayrollClosure.year == year)
        return query.order_by(
            PayrollClosure.year.desc(),
            PayrollClosure.month.desc()
        ).all()

    def get_history(self, db: Session, month: int, year: int) -> List[PayrollClosure]:
        return db.query(PayrollClosure).filter(
            PayrollClosure.month == month,
            PayrollClosure.year == year
        ).order_by(PayrollClosure.id.asc()).all()

    def delete(self, db: Session, month: int, year: int, user_id: int):
        record = db.query(PayrollClosure).filter(
            PayrollClosure.month == month,
            PayrollClosure.year == year,
            PayrollClosure.deleted_at.is_(None)
        ).first()
        if record:
            record.deleted_at = datetime.now()
            record.deleted_by = user_id
            db.commit()


payroll_repository = PayrollRepository()
