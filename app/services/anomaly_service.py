from datetime import date, timedelta, datetime
from sqlalchemy.orm import Session
from typing import List, Dict

from app.domain.models.enums import RecordType, UserRole
from app.domain.models.user import User
from app.repositories.time_record_repository import time_record_repository
from app.repositories.user_repository import user_repository
from app.schemas.anomaly import AnomalyResponse, UserAnomalySummary, AnomalyBase


class AnomalyService:
    def _format_duration(self, total_seconds: float) -> str:
        total_minutes = int(round(total_seconds / 60))
        hours = total_minutes // 60
        minutes = total_minutes % 60
        return f"{hours}h{minutes:02d}"

    def _check_day_anomalies(self, user_id: int, user_name: str, current_date: date, records: List) -> List[
        AnomalyResponse]:
        anomalies = []
        records.sort(key=lambda x: x.record_datetime)

        total_worked_seconds = 0.0
        last_entry_time = None

        if records and records[0].record_type == RecordType.EXIT:
            anomalies.append(AnomalyResponse(
                user_id=user_id,
                user_name=user_name,
                date=current_date,
                type="MISSING_ENTRY",
                description="Saída sem entrada"
            ))

        for i in range(len(records)):
            current_record = records[i]

            if i > 0 and current_record.record_type == RecordType.ENTRY and records[
                i - 1].record_type == RecordType.ENTRY:
                anomalies.append(AnomalyResponse(
                    user_id=user_id,
                    user_name=user_name,
                    date=current_date,
                    type="DOUBLE_ENTRY",
                    description="Duas entradas consecutivas sem saída entre elas"
                ))

            if i > 0 and current_record.record_type == RecordType.EXIT and records[
                i - 1].record_type == RecordType.EXIT:
                anomalies.append(AnomalyResponse(
                    user_id=user_id,
                    user_name=user_name,
                    date=current_date,
                    type="DOUBLE_EXIT",
                    description="Duas saídas consecutivas sem entrada entre elas"
                ))

            if current_record.record_type == RecordType.ENTRY:
                last_entry_time = current_record.record_datetime
            elif current_record.record_type == RecordType.EXIT:
                if last_entry_time:
                    delta = current_record.record_datetime - last_entry_time
                    seconds = delta.total_seconds()

                    if seconds > 7 * 3600:
                        fmt_time = self._format_duration(seconds)
                        anomalies.append(AnomalyResponse(
                            user_id=user_id,
                            user_name=user_name,
                            date=current_date,
                            type="LONG_INTERVAL",
                            description=f"Intervalo de {fmt_time}"
                        ))

                    total_worked_seconds += seconds
                    last_entry_time = None

        if records and records[-1].record_type == RecordType.ENTRY:
            anomalies.append(AnomalyResponse(
                user_id=user_id,
                user_name=user_name,
                date=current_date,
                type="MISSING_EXIT",
                description="Entrada sem saída"
            ))

        if total_worked_seconds > (8.5 * 3600):
            fmt_total = self._format_duration(total_worked_seconds)
            anomalies.append(AnomalyResponse(
                user_id=user_id,
                user_name=user_name,
                date=current_date,
                type="EXCESSIVE_HOURS",
                description=f"Trabalhou {fmt_total}"
            ))

        return anomalies

    def get_anomalies(self, db: Session, start_date: date, end_date: date, user_id: int = None) -> List[
        AnomalyResponse]:
        query = db.query(User).filter(User.is_active == True, User.role == UserRole.EMPLOYEE)
        if user_id:
            query = query.filter(User.id == user_id)
        users = query.all()

        all_anomalies = []

        target_user_ids = [u.id for u in users]
        if not target_user_ids:
            return []

        dt_start = datetime.combine(start_date, datetime.min.time())
        dt_end = datetime.combine(end_date, datetime.max.time())

        records_flat = time_record_repository.get_by_users_and_range(db, target_user_ids, dt_start, dt_end)

        records_map: Dict[int, Dict[date, List]] = {uid: {} for uid in target_user_ids}

        for record in records_flat:
            uid = record.user_id
            rdate = record.record_datetime.date()
            if rdate not in records_map[uid]:
                records_map[uid][rdate] = []
            records_map[uid][rdate].append(record)
        user_map = {u.id: u.name for u in users}

        for uid in target_user_ids:
            user_name = user_map.get(uid, "Unknown")
            for rdate, day_records in records_map[uid].items():
                day_anomalies = self._check_day_anomalies(uid, user_name, rdate, day_records)
                all_anomalies.extend(day_anomalies)

        all_anomalies.sort(key=lambda x: x.date, reverse=True)
        return all_anomalies


anomaly_service = AnomalyService()
