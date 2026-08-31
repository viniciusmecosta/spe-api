import logging
from datetime import date, datetime, timedelta
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import Depends
from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.config import settings
from app.features.adjustments.adjustment_repository import (
    adjustment_repository,
    async_adjustment_repository,
)
from app.features.reports.report_schemas import (
    Aniversariante,
    AnomalyItem,
    DashboardMetricsResponse,
    EmployeeHours,
    ManagerDashboardResponse,
    MyDashboardResponse,
    TeamHoursResponse,
    TodayPunch,
)
from app.features.reports.report_service import report_service
from app.features.time_records.time_record_repository import (
    async_time_record_repository,
    time_record_repository,
)
from app.features.timesheets.anomaly_service import anomaly_service
from app.features.users.user_models import User
from app.shared import deps
from app.shared.enums import RecordType, UserRole
from app.shared.trusted_time_service import trusted_time_service
from app.utils.formatters import format_short_name

logger = logging.getLogger(__name__)


class DashboardService:
    def __init__(self, db: Annotated[AsyncSession, Depends(deps.get_async_db)] = None):
        self.db = db

    async def get_dashboard_metrics(self, db: Any | None = None) -> DashboardMetricsResponse:
        session = db if db is not None else self.db
        assert session is not None
        tz = ZoneInfo(settings.TIMEZONE)
        today = datetime.now(tz).date()

        today_start = datetime.combine(today, datetime.min.time(), tzinfo=tz)
        today_end = datetime.combine(today, datetime.max.time(), tzinfo=tz)

        if hasattr(session, "sync_session"):
            stmt = select(func.count(User.id)).where(
                User.is_active.is_(True),
                User.role == UserRole.EMPLOYEE,
                User.is_exempt_from_rules.is_(False),
            )
            active_users = (await session.scalar(stmt)) or 0
            pending = await async_adjustment_repository.count_pending(session)
            present = await async_time_record_repository.count_unique_users_in_range(session, today_start, today_end)
        else:
            active_users = session.query(User).filter(
                User.is_active.is_(True),
                User.role == UserRole.EMPLOYEE,
                User.is_exempt_from_rules.is_(False)
            ).count()
            pending = adjustment_repository.count_pending(session)
            present = time_record_repository.count_unique_users_in_range(session, today_start, today_end)

        return DashboardMetricsResponse(
            total_active_employees=active_users,
            pending_adjustments=pending,
            employees_present_today=present,
            date=today
        )

    async def get_my_dashboard(self, db: Any | None = None, current_user: User | None = None) -> MyDashboardResponse:
        session = db if db is not None else self.db
        assert session is not None
        assert current_user is not None
        now, _ = trusted_time_service.get_trusted_time()
        tz = now.tzinfo
        today_date = now.date()
        start_of_month = date(now.year, now.month, 1)

        start_dt_today = datetime.combine(today_date, datetime.min.time(), tzinfo=tz)
        end_dt_today = datetime.combine(today_date, datetime.max.time(), tzinfo=tz)

        if hasattr(session, "sync_session"):
            today_records = await async_time_record_repository.get_by_range(session, current_user.id, start_dt_today,
                                                                            end_dt_today)
        else:
            today_records = time_record_repository.get_by_range(session, current_user.id, start_dt_today, end_dt_today)
        today_records.sort(key=lambda x: x.record_datetime)

        today_punches = []
        for rec in today_records:
            today_punches.append(TodayPunch(
                id=rec.id,
                short_id=rec.short_id,
                time=rec.record_datetime.strftime("%H:%M"),
                record_type=rec.record_type.value
            ))

        next_punch_type = "ENTRY"
        if today_records:
            last_record = today_records[-1]
            if last_record.record_type == RecordType.ENTRY:
                next_punch_type = "EXIT"

        month_anomalies = []
        anomalies = await anomaly_service.get_anomalies(
            session, start_of_month, today_date, current_user.id, ignore_excessive_hours=False
        )
        for a in anomalies:
            month_anomalies.append(AnomalyItem(
                date=a.date.strftime("%d/%m/%Y"),
                description=a.description
            ))

        if hasattr(session, "sync_session"):
            stmt = select(User).where(
                User.is_active == True,
                extract('month', User.data_nascimento) == now.month
            )
            res = await session.scalars(stmt)
            aniversariantes_query = list(res.all())
        else:
            aniversariantes_query = session.query(User).filter(
                User.is_active == True,
                extract('month', User.data_nascimento) == now.month
            ).all()

        aniversariantes_do_mes = []
        for a in aniversariantes_query:
            if a.data_nascimento:
                aniversariantes_do_mes.append(Aniversariante(
                    nome=a.name,
                    dia=a.data_nascimento.day
                ))

        aniversariantes_do_mes.sort(key=lambda x: x.dia)

        return MyDashboardResponse(
            full_name=current_user.name,
            next_punch_type=next_punch_type,
            today_punches=today_punches,
            month_anomalies=month_anomalies,
            aniversariantes_do_mes=aniversariantes_do_mes,
            server_time_unix=int(now.timestamp()),
            server_time_formatted=now.strftime("%d/%m/%Y %H:%M:%S")
        )

    async def get_team_worked_hours(self, db: Any | None = None, month: int = 0, year: int = 0,
                                    current_user: User | None = None) -> TeamHoursResponse:
        session = db if db is not None else self.db
        assert session is not None
        assert current_user is not None
        if hasattr(session, "sync_session"):
            stmt = select(User).options(selectinload(User.historical_schedules)).where(
                User.role == UserRole.EMPLOYEE,
                User.is_exempt_from_rules.is_(False)
            )
            res = await session.scalars(stmt)
            users = list(res.all())
        else:
            query = session.query(User).options(joinedload(User.historical_schedules)).filter(
                User.role == UserRole.EMPLOYEE,
                User.is_exempt_from_rules.is_(False)
            )
            users = query.all()

        employees_data = []
        team_total_minutes = 0

        for user in users:
            report = await report_service.get_advanced_user_report(session, user.id, month, year, current_user)
            if report:
                user_minutes = report.summary.total_worked_minutes
                if user_minutes >= 60:
                    user_hours_rounded = user_minutes // 60
                    employees_data.append(EmployeeHours(
                        user_id=user.id,
                        short_name=format_short_name(user.name),
                        total_hours=float(user_hours_rounded),
                        formatted_time=f"{user_hours_rounded}h"
                    ))
                    team_total_minutes += user_minutes

        t_hours = team_total_minutes // 60

        return TeamHoursResponse(
            month=month,
            year=year,
            team_total_hours=float(t_hours),
            team_formatted_time=f"{t_hours}h",
            employees=employees_data
        )

    async def get_manager_dashboard(self, db: Any | None = None,
                                    current_user: User | None = None) -> ManagerDashboardResponse:
        session = db if db is not None else self.db
        assert session is not None
        assert current_user is not None
        tz = ZoneInfo(settings.TIMEZONE)
        now = datetime.now(tz)
        today_date = now.date()

        start_dt_today = datetime.combine(today_date, datetime.min.time(), tzinfo=tz)
        end_dt_today = datetime.combine(today_date, datetime.max.time(), tzinfo=tz)

        if hasattr(session, "sync_session"):
            today_records = await async_time_record_repository.get_by_range(session, current_user.id, start_dt_today,
                                                                            end_dt_today)
        else:
            today_records = time_record_repository.get_by_range(session, current_user.id, start_dt_today, end_dt_today)
        today_records.sort(key=lambda x: x.record_datetime)

        today_punches = []
        for rec in today_records:
            today_punches.append(TodayPunch(
                id=rec.id,
                short_id=rec.short_id,
                time=rec.record_datetime.strftime("%H:%M"),
                record_type=rec.record_type.value
            ))

        next_punch_type = "ENTRY"
        if today_records:
            last_record = today_records[-1]
            if last_record.record_type == RecordType.ENTRY:
                next_punch_type = "EXIT"

        all_anomalies = await anomaly_service.get_anomalies_by_month(
            session, now.month, now.year, user_id=None, ignore_excessive_hours=False
        )
        total_system_anomalies = len(all_anomalies)

        six_months_ago = today_date - timedelta(days=180)
        if hasattr(session, "sync_session"):
            total_pending_adjustments = await async_adjustment_repository.count_pending(session,
                                                                                        from_date=six_months_ago)
            today_total_punches = await async_time_record_repository.count_records_in_range(session, start_dt_today,
                                                                                            end_dt_today)
        else:
            total_pending_adjustments = adjustment_repository.count_pending(session, from_date=six_months_ago)
            today_total_punches = time_record_repository.count_records_in_range(session, start_dt_today, end_dt_today)

        team_hours = await self.get_team_worked_hours(session, now.month, now.year, current_user)

        return ManagerDashboardResponse(
            full_name=current_user.name,
            next_punch_type=next_punch_type,
            today_punches=today_punches,
            total_system_anomalies=total_system_anomalies,
            total_pending_adjustments=total_pending_adjustments,
            today_total_punches=today_total_punches,
            team_hours=team_hours
        )


dashboard_service = DashboardService()
