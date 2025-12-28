from datetime import date, datetime

import pytz
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.models.enums import UserRole
from app.domain.models.user import User
from app.repositories.payroll_repository import payroll_repository


class PayrollService:
    def close_period(self, db: Session, month: int, year: int, current_user: User):
        # Apenas Gestor ou Mantenedor podem fechar
        if current_user.role not in [UserRole.MANAGER, UserRole.MAINTAINER]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to close payroll."
            )

        # Validação de Data: Só permite fechar se o mês já passou
        tz = pytz.timezone(settings.TIMEZONE)
        today = datetime.now(tz).date()

        # Cria data do primeiro dia do mês requisitado e do mês atual para comparação
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
        # APENAS Mantenedor pode reabrir
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
        """
        Lança exceção se o período da data alvo estiver fechado.
        """
        closure = payroll_repository.get_by_month(db, target_date.month, target_date.year)
        if closure:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Action blocked: Payroll for {target_date.month}/{target_date.year} is CLOSED."
            )


payroll_service = PayrollService()
