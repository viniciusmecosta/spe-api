from datetime import date, datetime
from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy.orm import Session
from typing import Any
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.domain.models.enums import UserRole
from app.domain.models.user import User
from app.repositories.payroll_repository import payroll_repository
from app.services.audit_service import audit_service
from app.services.email_service import email_service, dispatch_payroll_email


def dispatch_closure_background(month: int, year: int, closure_id: int, current_user_id: int, user_name: str):
    import os
    import logging
    from app.database.session import get_db_session
    from app.domain.models.payroll import PayrollClosure
    from app.domain.models.user import User
    from app.services.excel_service import excel_service
    from app.core.config import settings

    logger = logging.getLogger(__name__)

    try:
        with get_db_session() as db:
            current_user = db.query(User).get(current_user_id)
            if not current_user:
                return

            attachment = excel_service.generate_excel_report(db, month, year, None, current_user)

            reports_dir = os.path.join(settings.UPLOAD_DIR, "reports")
            os.makedirs(reports_dir, exist_ok=True)

            filename = f"folha_ponto_{month:02d}_{year}.xlsx"
            file_path = os.path.join(reports_dir, filename)

            with open(file_path, "wb") as f:
                f.write(attachment.getvalue())

            closure = db.query(PayrollClosure).get(closure_id)
            if closure:
                closure.report_path = f"reports/{filename}"
                db.commit()

            email_service.send_payroll_email(db, "Fechamento", user_name, month, year, attachment)

    except Exception as e:
        logger.exception(f"Error in dispatch_closure_background: {e}")


class PayrollService:
    def _build_history(self, month_closures: list) -> list[dict[str, Any]]:
        history = []
        for h in month_closures:
            history.append({
                "action": "Fechamento",
                "timestamp": h.closed_at,
                "user_id": h.closed_by_user_id,
                "user_name": h.closed_by.name if h.closed_by else None,
                "observation": None,
            })
            if h.deleted_at:
                history.append({
                    "action": "Reabertura",
                    "timestamp": h.deleted_at,
                    "user_id": h.deleted_by,
                    "user_name": h.deleter.name if h.deleter else None,
                    "observation": h.reopen_observation,
                })
        history.sort(key=lambda x: x["timestamp"], reverse=True)
        return history

    def _build_period_response(self, mo: int, year: int, closures_by_month: dict) -> dict[str, Any]:
        history = []
        active_closure = None

        if mo in closures_by_month:
            month_closures = closures_by_month[mo]
            active_closure = next((c for c in month_closures if c.deleted_at is None), None)
            history = self._build_history(month_closures)

        if active_closure:
            return {
                "month": mo,
                "year": year,
                "is_closed": True,
                "id": active_closure.id,
                "closed_at": active_closure.closed_at,
                "closed_by_user_id": active_closure.closed_by_user_id,
                "closed_by_name": active_closure.closed_by.name if active_closure.closed_by else None,
                "history": history,
                "report_path": active_closure.report_path
            }
        else:
            return {
                "month": mo,
                "year": year,
                "is_closed": False,
                "id": None,
                "closed_at": None,
                "closed_by_user_id": None,
                "closed_by_name": None,
                "history": history,
                "report_path": None
            }

    def list_periods(self, db: Session, year: int) -> list[dict[str, Any]]:
        tz = ZoneInfo(settings.TIMEZONE)
        now = datetime.now(tz)
        current_year = now.year
        current_month = now.month

        if year < current_year:
            max_month = 12
        elif year == current_year:
            max_month = current_month
        else:
            max_month = 0

        from app.domain.models.payroll import PayrollClosure
        all_closures = db.query(PayrollClosure).filter(PayrollClosure.year == year).order_by(
            PayrollClosure.id.asc()).all()

        closures_by_month = {}
        for c in all_closures:
            if c.month not in closures_by_month:
                closures_by_month[c.month] = []
            closures_by_month[c.month].append(c)

        result = []
        for mo in range(max_month, 0, -1):
            result.append(self._build_period_response(mo, year, closures_by_month))
        return result

    def close_period(self, db: Session, month: int, year: int, current_user: User, background_tasks: BackgroundTasks):
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

        background_tasks.add_task(
            dispatch_closure_background,
            month, year, closure.id, current_user.id, current_user.name
        )
        return closure

    def reopen_period(self, db: Session, month: int, year: int, observation: str, current_user: User, background_tasks: BackgroundTasks):
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
        payroll_repository.delete(db, month, year, current_user.id, observation)

        audit_service.log(
            db, user_id=current_user.id, action="REOPEN", entity="PAYROLL", entity_id=closure_id,
            old_data={"month": month, "year": year}
        )

        background_tasks.add_task(
            dispatch_payroll_email,
            "Reabertura", current_user.name, month, year, current_user.id
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
