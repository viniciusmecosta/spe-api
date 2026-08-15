import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import extract
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.features.adjustments.adjustment_repository import adjustment_repository
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
    time_record_repository,
)
from app.features.timesheets.anomaly_service import anomaly_service
from app.features.users.user_models import User
from app.shared.enums import RecordType, UserRole
from app.shared.trusted_time_service import trusted_time_service
from app.utils.formatters import format_short_name

logger = logging.getLogger(__name__)


class DashboardService:
    def get_dashboard_metrics(self, db: Session) -> DashboardMetricsResponse:
        tz = ZoneInfo(settings.TIMEZONE)
        today = datetime.now(tz).date()

        active_users = db.query(User).filter(
            User.is_active.is_(True),
            User.role == UserRole.EMPLOYEE,
            User.is_exempt_from_rules.is_(False)
        ).count()

        pending = adjustment_repository.count_pending(db)

        today_start = datetime.combine(today, datetime.min.time(), tzinfo=tz)
        today_end = datetime.combine(today, datetime.max.time(), tzinfo=tz)

        present = time_record_repository.count_unique_users_in_range(db, today_start, today_end)

        return DashboardMetricsResponse(
            total_active_employees=active_users,
            pending_adjustments=pending,
            employees_present_today=present,
            date=today
        )

    def get_my_dashboard(self, db: Session, current_user: User) -> MyDashboardResponse:
        now, _ = trusted_time_service.get_trusted_time()
        tz = now.tzinfo
        today_date = now.date()
        start_of_month = date(now.year, now.month, 1)

        start_dt_today = datetime.combine(today_date, datetime.min.time(), tzinfo=tz)
        end_dt_today = datetime.combine(today_date, datetime.max.time(), tzinfo=tz)

        today_records = time_record_repository.get_by_range(db, current_user.id, start_dt_today, end_dt_today)
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
        anomalies = anomaly_service.get_anomalies(
            db, start_of_month, today_date, current_user.id, ignore_excessive_hours=False
        )
        for a in anomalies:
            month_anomalies.append(AnomalyItem(
                date=a.date.strftime("%d/%m/%Y"),
                description=a.description
            ))

        aniversariantes_query = db.query(User).filter(
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

    def get_team_worked_hours(self, db: Session, month: int, year: int, current_user: User) -> TeamHoursResponse:
        query = db.query(User).options(joinedload(User.historical_schedules)).filter(
            User.role == UserRole.EMPLOYEE,
            User.is_exempt_from_rules.is_(False)
        )
        users = query.all()

        employees_data = []
        team_total_minutes = 0

        for user in users:
            report = report_service.get_advanced_user_report(db, user.id, month, year, current_user)
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

    def get_manager_dashboard(self, db: Session, current_user: User) -> ManagerDashboardResponse:
        tz = ZoneInfo(settings.TIMEZONE)
        now = datetime.now(tz)
        today_date = now.date()

        start_dt_today = datetime.combine(today_date, datetime.min.time(), tzinfo=tz)
        end_dt_today = datetime.combine(today_date, datetime.max.time(), tzinfo=tz)

        today_records = time_record_repository.get_by_range(db, current_user.id, start_dt_today, end_dt_today)
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

        all_anomalies = anomaly_service.get_anomalies_by_month(
            db, now.month, now.year, user_id=None, ignore_excessive_hours=False
        )
        total_system_anomalies = len(all_anomalies)

        six_months_ago = today_date - timedelta(days=180)
        total_pending_adjustments = adjustment_repository.count_pending(db, from_date=six_months_ago)

        today_total_punches = time_record_repository.count_records_in_range(db, start_dt_today, end_dt_today)

        team_hours = self.get_team_worked_hours(db, now.month, now.year, current_user)

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
