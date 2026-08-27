import calendar
from datetime import date, datetime
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.time_records.time_record_repository import (
    time_record_repository,
)
from app.features.timesheets.timesheet_exceptions import InvalidMonthOrYearError
from app.features.timesheets.timesheet_schemas import AnomalyResponse
from app.features.users.user_repository import user_repository
from app.shared import deps
from app.shared.enums import (
    AdjustmentStatus,
    AdjustmentType,
    DayOfWeek,
    RecordType,
    UserRole,
)


class AnomalyService:
    def __init__(self, db: Annotated[Session, Depends(deps.get_db)] = None):
        self.db = db
    def _format_duration(self, total_seconds: float) -> str:
        total_minutes = int(round(total_seconds / 60))
        hours = total_minutes // 60
        minutes = total_minutes % 60
        return f"{hours}h{minutes:02d}"

    def _check_missing_entries_exits(self, user_id: int, user_name: str, current_date: date, records: list) -> list[
        AnomalyResponse]:
        anomalies = []
        if records and records[0].record_type == RecordType.EXIT:
            anomalies.append(AnomalyResponse(
                user_id=user_id, user_name=user_name, date=current_date,
                type="MISSING_ENTRY", description="Saída registrada sem uma entrada correspondente."
            ))
        if records and records[-1].record_type == RecordType.ENTRY and current_date < date.today():
            anomalies.append(AnomalyResponse(
                user_id=user_id, user_name=user_name, date=current_date,
                type="MISSING_EXIT", description="Entrada registrada sem uma saída correspondente."
            ))
        return anomalies

    def _check_consecutive_records(self, user_id: int, user_name: str, current_date: date, records: list) -> list[
        AnomalyResponse]:
        anomalies = []
        for i in range(1, len(records)):
            current_record = records[i]
            prev_record = records[i - 1]
            if current_record.record_type == RecordType.ENTRY and prev_record.record_type == RecordType.ENTRY:
                anomalies.append(AnomalyResponse(
                    user_id=user_id, user_name=user_name, date=current_date,
                    type="DOUBLE_ENTRY",
                    description="Registros duplicados: Duas entradas seguidas sem saída no intervalo."
                ))
            if current_record.record_type == RecordType.EXIT and prev_record.record_type == RecordType.EXIT:
                anomalies.append(AnomalyResponse(
                    user_id=user_id, user_name=user_name, date=current_date,
                    type="DOUBLE_EXIT",
                    description="Registros duplicados: Duas saídas seguidas sem entrada no intervalo."
                ))
        return anomalies

    def _check_long_intervals(self, user_id: int, user_name: str, current_date: date, records: list) -> list[
        AnomalyResponse]:
        anomalies = []
        last_entry_time = None
        for current_record in records:
            if current_record.record_type == RecordType.ENTRY:
                last_entry_time = current_record.record_datetime.replace(second=0, microsecond=0)
            elif current_record.record_type == RecordType.EXIT and last_entry_time:
                delta = current_record.record_datetime.replace(second=0, microsecond=0) - last_entry_time
                seconds = delta.total_seconds()
                if seconds > 8 * 3600:
                    fmt_time = self._format_duration(seconds)
                    anomalies.append(AnomalyResponse(
                        user_id=user_id, user_name=user_name, date=current_date,
                        type="LONG_INTERVAL", description=f"Intervalo longo detectado ({fmt_time})."
                    ))
                last_entry_time = None
        return anomalies

    def _check_consecutive_and_long_intervals(self, user_id: int, user_name: str, current_date: date, records: list) -> \
            list[AnomalyResponse]:
        anomalies = []
        anomalies.extend(self._check_consecutive_records(user_id, user_name, current_date, records))
        anomalies.extend(self._check_long_intervals(user_id, user_name, current_date, records))
        return anomalies

    def _build_unapproved_extra_description(self, status, minutes: int, time_to_show) -> str:
        if status == AdjustmentStatus.PENDING:
            if time_to_show:
                return f"{minutes} minutos extras pendentes de aprovação (horário de entrada definido: {time_to_show.strftime('%H:%M')})"
            return f"{minutes} minutos extras pendentes de aprovação"
        if time_to_show:
            return f"Hora extra negada: {minutes} minutos não aprovados (horário de entrada: {time_to_show.strftime('%H:%M')})"
        return f"Hora extra negada: {minutes} minutos não aprovados"

    def _check_unapproved_adjustments(self, user_id: int, user_name: str, current_date: date, day_adjustments: list,
                                      expected_entry_time) -> list[AnomalyResponse]:
        anomalies = []
        for adj in day_adjustments:
            if adj.adjustment_type == AdjustmentType.EXTRA_TIME and adj.status in [AdjustmentStatus.PENDING,
                                                                                   AdjustmentStatus.REJECTED]:
                minutes = int(adj.amount_hours * 60) if adj.amount_hours else 0
                time_to_show = expected_entry_time or adj.time
                desc = self._build_unapproved_extra_description(adj.status, minutes, time_to_show)

                anomalies.append(AnomalyResponse(
                    user_id=user_id, user_name=user_name, date=current_date,
                    type="UNAPPROVED_EXTRA_TIME", description=desc
                ))
        return anomalies

    def _check_day_anomalies(self, user_id: int, user_name: str, current_date: date, records: list,
                             ignore_excessive_hours: bool = False, day_adjustments: list = None,
                             expected_entry_time=None) -> list[AnomalyResponse]:
        if day_adjustments is None:
            day_adjustments = []
        anomalies = []
        records.sort(key=lambda x: x.record_datetime)

        total_worked_seconds = 0.0
        last_entry = None
        for r in records:
            if r.record_type == RecordType.ENTRY:
                last_entry = r.record_datetime
            elif r.record_type == RecordType.EXIT and last_entry:
                total_worked_seconds += (r.record_datetime - last_entry).total_seconds()
                last_entry = None

        anomalies.extend(self._check_missing_entries_exits(user_id, user_name, current_date, records))
        anomalies.extend(self._check_consecutive_and_long_intervals(user_id, user_name, current_date, records))
        anomalies.extend(
            self._check_unapproved_adjustments(user_id, user_name, current_date, day_adjustments, expected_entry_time))

        if not ignore_excessive_hours and total_worked_seconds > (10 * 3600):
            fmt_total = self._format_duration(total_worked_seconds)
            anomalies.append(AnomalyResponse(
                user_id=user_id,
                user_name=user_name,
                date=current_date,
                type="EXCESSIVE_HOURS",
                description=f"Jornada excessiva: O tempo trabalhado ({fmt_total}) ultrapassou o limite normal de 10 horas."
            ))

        return anomalies

    def _build_data_maps(self, records_flat, extra_time_adjustments, target_user_ids):
        records_map: dict[int, dict[date, list]] = {uid: {} for uid in target_user_ids}
        adj_map: dict[int, dict[date, list]] = {uid: {} for uid in target_user_ids}

        for record in records_flat:
            uid = record.user_id
            rdate = record.record_datetime.date()
            if rdate not in records_map[uid]:
                records_map[uid][rdate] = []
            records_map[uid][rdate].append(record)

        for adj in extra_time_adjustments:
            uid = adj.user_id
            rdate = adj.target_date
            if rdate not in adj_map[uid]:
                adj_map[uid][rdate] = []
            adj_map[uid][rdate].append(adj)

        return records_map, adj_map

    def _get_expected_entry_time(self, user, rdate):
        if user and user.historical_schedules:
            valid_schedules = [
                s for s in user.historical_schedules
                if s.valid_from <= rdate and (s.valid_until is None or s.valid_until >= rdate)
            ]
            target_day = DayOfWeek.from_date(rdate)
            schedule = next((s for s in valid_schedules if s.day_of_week == target_day.value), None)
            if schedule and schedule.entry_1:
                return schedule.entry_1
        return None

    def _process_user_anomalies(self, uid, user, all_dates, records_map, adj_map, ignore_excessive_hours):
        user_anomalies = []
        user_name = user.name if user else "Unknown"
        for rdate in all_dates:
            expected_entry = self._get_expected_entry_time(user, rdate)
            day_records = records_map[uid].get(rdate, [])
            day_adjs = adj_map[uid].get(rdate, [])
            day_anomalies = self._check_day_anomalies(uid, user_name, rdate, day_records, ignore_excessive_hours,
                                                      day_adjs, expected_entry)
            user_anomalies.extend(day_anomalies)
        return user_anomalies

    def _process_all_anomalies(self, target_user_ids, users, records_map, adj_map, ignore_excessive_hours):
        all_anomalies = []
        user_map = {u.id: u for u in users}

        for uid in target_user_ids:
            user = user_map.get(uid)
            all_dates = sorted(set(records_map[uid].keys()).union(adj_map[uid].keys()))
            all_anomalies.extend(
                self._process_user_anomalies(uid, user, all_dates, records_map, adj_map, ignore_excessive_hours))

        all_anomalies.sort(key=lambda x: x.date, reverse=True)
        return all_anomalies

    def get_anomalies(self, db: Session | None = None, start_date: date | None = None, end_date: date | None = None, user_id: int | None = None,
                      ignore_excessive_hours: bool = False) -> list[AnomalyResponse]:
        session = db if db is not None else self.db
        assert session is not None
        assert start_date is not None
        assert end_date is not None
        if user_id:
            user = user_repository.get(session, user_id)
            users = [user] if user and user.is_active and user.role == UserRole.EMPLOYEE else []
        else:
            users = user_repository.get_active_employees(session)

        target_user_ids = [u.id for u in users]
        if not target_user_ids:
            return []

        dt_start = datetime.combine(start_date, datetime.min.time())
        dt_end = datetime.combine(end_date, datetime.max.time())

        records_flat = time_record_repository.get_by_users_and_range(session, target_user_ids, dt_start, dt_end)

        extra_time_adjustments = session.query(AdjustmentRequest).filter(
            AdjustmentRequest.user_id.in_(target_user_ids),
            AdjustmentRequest.target_date >= start_date,
            AdjustmentRequest.target_date <= end_date,
            AdjustmentRequest.adjustment_type == AdjustmentType.EXTRA_TIME,
            AdjustmentRequest.status.in_([AdjustmentStatus.PENDING, AdjustmentStatus.REJECTED]),
            AdjustmentRequest.deleted_at.is_(None)
        ).all()

        records_map, adj_map = self._build_data_maps(records_flat, extra_time_adjustments, target_user_ids)
        return self._process_all_anomalies(target_user_ids, users, records_map, adj_map, ignore_excessive_hours)

    def get_anomalies_by_month(self, db: Session | None = None, month: int = 0, year: int = 0, user_id: int | None = None,
                               ignore_excessive_hours: bool = False) -> list[AnomalyResponse]:
        session = db if db is not None else self.db
        assert session is not None
        today = date.today()
        try:
            _, last_day = calendar.monthrange(year, month)
        except ValueError:
            raise InvalidMonthOrYearError()

        start_date = date(year, month, 1)
        end_date = date(year, month, last_day)

        end_date = min(end_date, today)

        if start_date > end_date:
            return []

        return self.get_anomalies(session, start_date, end_date, user_id, ignore_excessive_hours)


anomaly_service = AnomalyService()
