from datetime import date, datetime
from typing import List, Dict, Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.models.enums import UserRole
from app.domain.models.time_record import TimeRecord
from app.domain.models.user import User
from app.repositories.payroll_repository import payroll_repository
from app.services.audit_service import audit_service


class PayrollService:
    def list_periods(self, db: Session) -> List[Dict[str, Any]]:
        tz = ZoneInfo(settings.TIMEZONE)
        now = datetime.now(tz)
        current_month = now.month
        current_year = now.year

        all_records = db.query(TimeRecord.record_datetime).filter(TimeRecord.is_ignored == False).all()
        periods_with_data = {(dt[0].year, dt[0].month) for dt in all_records if dt[0]}

        periods_with_data.add((current_year, current_month))

        closed_periods = payroll_repository.get_all(db)
        closed_dict = {(p.year, p.month): p for p in closed_periods}

        for p in closed_periods:
            periods_with_data.add((p.year, p.month))

        result = []
        for year, month in sorted(periods_with_data, key=lambda x: (x[0], x[1]), reverse=True):
            if (year, month) in closed_dict:
                p = closed_dict[(year, month)]
                result.append({
                    "month": p.month,
                    "year": p.year,
                    "is_closed": True,
                    "id": p.id,
                    "closed_at": p.closed_at,
                    "closed_by_user_id": p.closed_by_user_id
                })
            else:
                result.append({
                    "month": month,
                    "year": year,
                    "is_closed": False,
                    "id": None,
                    "closed_at": None,
                    "closed_by_user_id": None
                })
        return result

    def close_period(self, db: Session, month: int, year: int, current_user: User):
        if current_user.role not in [UserRole.MANAGER, UserRole.MAINTAINER]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acesso negado: Usuário não tem permissão para fechar a folha de ponto."
            )

        tz = ZoneInfo(settings.TIMEZONE)
        today = datetime.now(tz).date()

        request_date = date(year, month, 1)
        current_month_start = date(today.year, today.month, 1)

        if request_date >= current_month_start:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Não é possível fechar a folha do mês atual ou de meses futuros ({month:02d}/{year}). Apenas meses anteriores podem ser fechados."
            )

        existing = payroll_repository.get_by_month(db, month, year)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"A folha de ponto referente a {month:02d}/{year} já está fechada."
            )

        closure = payroll_repository.create(db, month, year, current_user.id)

        audit_service.log(
            db, user_id=current_user.id, action="CLOSE", entity="PAYROLL", entity_id=closure.id,
            new_data={"month": month, "year": year}
        )
        return closure

    def reopen_period(self, db: Session, month: int, year: int, current_user: User):
        if current_user.role != UserRole.MAINTAINER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acesso negado: Apenas mantenedores podem reabrir folhas de ponto."
            )

        existing = payroll_repository.get_by_month(db, month, year)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"A folha de ponto referente a {month:02d}/{year} não está fechada."
            )

        closure_id = existing.id
        payroll_repository.delete(db, month, year, current_user.id)

        audit_service.log(
            db, user_id=current_user.id, action="REOPEN", entity="PAYROLL", entity_id=closure_id,
            old_data={"month": month, "year": year}
        )
        return {"status": "success", "message": f"Folha de ponto de {month:02d}/{year} reaberta com sucesso."}

    def validate_period_open(self, db: Session, target_date: date):
        closure = payroll_repository.get_by_month(db, target_date.month, target_date.year)
        if closure:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ação bloqueada: A folha de ponto referente a {target_date.month:02d}/{target_date.year} está FECHADA."
            )


payroll_service = PayrollService()
