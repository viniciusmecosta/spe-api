from datetime import date
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.repositories.payroll_repository import payroll_repository
from app.domain.models.user import User
from app.domain.models.enums import UserRole


class PayrollService:
    def close_period(self, db: Session, month: int, year: int, current_user: User):
        # Apenas Gestor ou Mantenedor podem fechar
        if current_user.role not in [UserRole.MANAGER, UserRole.MAINTAINER]:
            raise HTTPException(status_code=403, detail="Not authorized")

        existing = payroll_repository.get_by_month(db, month, year)
        if existing:
            raise HTTPException(status_code=400, detail="Period already closed")

        return payroll_repository.create(db, month, year, current_user.id)

    def reopen_period(self, db: Session, month: int, year: int, current_user: User):
        # APENAS Mantenedor pode reabrir
        if current_user.role != UserRole.MAINTAINER:
            raise HTTPException(status_code=403, detail="Only Maintainers can reopen payroll")

        existing = payroll_repository.get_by_month(db, month, year)
        if not existing:
            raise HTTPException(status_code=404, detail="Period is not closed")

        payroll_repository.delete(db, month, year)
        return {"message": "Period reopened successfully"}

    def validate_period_open(self, db: Session, target_date: date):
        """
        Lança exceção se o período da data alvo estiver fechado.
        Deve ser chamado antes de qualquer operação de escrita (CUD) em pontos ou ajustes.
        """
        closure = payroll_repository.get_by_month(db, target_date.month, target_date.year)
        if closure:
            raise HTTPException(
                status_code=400,
                detail=f"Payroll for {target_date.month}/{target_date.year} is CLOSED. No modifications allowed."
            )


payroll_service = PayrollService()