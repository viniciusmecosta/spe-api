import pytz
from datetime import date, datetime
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any

from app.core.config import settings
from app.domain.models.enums import UserRole
from app.domain.models.user import User
from app.repositories.payroll_repository import payroll_repository


class PayrollService:
    def list_periods(self, db: Session) -> List[Dict[str, Any]]:
        closed_periods = payroll_repository.get_all(db)

        tz = pytz.timezone(settings.TIMEZONE)
        now = datetime.now(tz)
        current_month = now.month
        current_year = now.year

        is_current_closed = any(p.month == current_month and p.year == current_year for p in closed_periods)

        result = []

        if not is_current_closed:
            result.append({
                "month": current_month,
                "year": current_year,
                "is_closed": False,
                "id": None,
                "closed_at": None,
                "closed_by_user_id": None
            })

        for p in closed_periods:
            result.append(p)

        return result

    def close_period(self, db: Session, month: int, year: int, current_user: User):
        if current_user.role not in [UserRole.MANAGER, UserRole.MAINTAINER]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to close payroll."
            )

        tz = pytz.timezone(settings.TIMEZONE)
        today = datetime.now(tz).date()

        request_date = date(year, month, 1)
        current_month_start = date(today.year, today.month, 1)

        if request_date >= current_month_start:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot close payroll for the current or future months ({month}/{year}). Only past months can be closed."
            )

        existing = payroll_repository.get_by_month(db, month, year)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Payroll period {month}/{year} is already closed."
            )

        return payroll_repository.create(db, month, year, current_user.id)

    def reopen_period(self, db: Session, month: int, year: int, current_user: User):
        if current_user.role != UserRole.MAINTAINER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only Maintainers can reopen payroll periods."
            )

        existing = payroll_repository.get_by_month(db, month, year)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Payroll period {month}/{year} is not closed."
            )

        payroll_repository.delete(db, month, year)
        return {"status": "success", "message": f"Payroll period {month}/{year} reopened successfully."}

    def validate_period_open(self, db: Session, target_date: date):
        closure = payroll_repository.get_by_month(db, target_date.month, target_date.year)
        if closure:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Action blocked: Payroll for {target_date.month}/{target_date.year} is CLOSED."
            )


payroll_service = PayrollService()