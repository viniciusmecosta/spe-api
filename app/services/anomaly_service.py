import calendar
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional

from sqlalchemy.orm import Session

from app.domain.models.enums import RecordType, UserRole
from app.repositories.time_record_repository import time_record_repository
from app.repositories.user_repository import user_repository
from app.schemas.anomaly import AnomalyResponse


class AnomalyService:
    def _format_duration(self, total_seconds: float) -> str:
        total_minutes = int(round(total_seconds / 60))
        hours = total_minutes // 60
        minutes = total_minutes % 60
        return f"{hours}h{minutes:02d}"

    def _check_day_anomalies(self, user_id: int, user_name: str, current_date: date, records: List,
                             ignore_excessive_hours: bool = False, day_adjustments: List = None) -> List[AnomalyResponse]:
        if day_adjustments is None:
            day_adjustments = []
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

                    if seconds > 8 * 3600:
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

        if not ignore_excessive_hours and total_worked_seconds > (10 * 3600):
            fmt_total = self._format_duration(total_worked_seconds)
            anomalies.append(AnomalyResponse(
                user_id=user_id,
                user_name=user_name,
                date=current_date,
                type="EXCESSIVE_HOURS",
                description=f"Trabalhou {fmt_total}"
            ))

        for adj in day_adjustments:
            from app.domain.models.enums import AdjustmentType, AdjustmentStatus
            if adj.adjustment_type == AdjustmentType.EXTRA_TIME and adj.status in [AdjustmentStatus.PENDING, AdjustmentStatus.REJECTED]:
                fmt_time = self._format_duration(adj.amount_hours * 3600 if adj.amount_hours else 0)
                anomalies.append(AnomalyResponse(
                    user_id=user_id,
                    user_name=user_name,
                    date=current_date,
                    type="UNAPPROVED_EXTRA_TIME",
                    description=f"Tempo extra não aprovado: considerado {fmt_time} de antecipação descartada"
                ))

        return anomalies

    def get_anomalies(self, db: Session, start_date: date, end_date: date, user_id: Optional[int] = None,
                      ignore_excessive_hours: bool = False) -> List[AnomalyResponse]:
        if user_id:
            user = user_repository.get(db, user_id)
            users = [user] if user and user.is_active and user.role == UserRole.EMPLOYEE else []
        else:
            users = user_repository.get_active_employees(db)

        all_anomalies = []

        target_user_ids = [u.id for u in users]
        if not target_user_ids:
            return []

        dt_start = datetime.combine(start_date, datetime.min.time())
        dt_end = datetime.combine(end_date, datetime.max.time())

        records_flat = time_record_repository.get_by_users_and_range(db, target_user_ids, dt_start, dt_end)
        
        from app.domain.models.adjustment import AdjustmentRequest
        from app.domain.models.enums import AdjustmentType, AdjustmentStatus
        extra_time_adjustments = db.query(AdjustmentRequest).filter(
            AdjustmentRequest.user_id.in_(target_user_ids),
            AdjustmentRequest.target_date >= start_date,
            AdjustmentRequest.target_date <= end_date,
            AdjustmentRequest.adjustment_type == AdjustmentType.EXTRA_TIME,
            AdjustmentRequest.status.in_([AdjustmentStatus.PENDING, AdjustmentStatus.REJECTED])
        ).all()

        records_map: Dict[int, Dict[date, List]] = {uid: {} for uid in target_user_ids}
        adj_map: Dict[int, Dict[date, List]] = {uid: {} for uid in target_user_ids}

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
            
        user_map = {u.id: u.name for u in users}

        for uid in target_user_ids:
            user_name = user_map.get(uid, "Unknown")
            all_dates = sorted(list(set(records_map[uid].keys()).union(set(adj_map[uid].keys()))))
            for rdate in all_dates:
                day_records = records_map[uid].get(rdate, [])
                day_adjs = adj_map[uid].get(rdate, [])
                day_anomalies = self._check_day_anomalies(uid, user_name, rdate, day_records, ignore_excessive_hours, day_adjs)
                all_anomalies.extend(day_anomalies)

        all_anomalies.sort(key=lambda x: x.date, reverse=True)
        return all_anomalies

    def get_anomalies_by_month(self, db: Session, month: int, year: int, user_id: Optional[int] = None,
                               ignore_excessive_hours: bool = False) -> List[AnomalyResponse]:
        today = date.today()
        try:
            _, last_day = calendar.monthrange(year, month)
        except ValueError:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Mês ou ano inválido.")

        start_date = date(year, month, 1)
        end_date = date(year, month, last_day)

        if end_date >= today:
            end_date = today - timedelta(days=1)

        if start_date > end_date:
            return []

        return self.get_anomalies(db, start_date, end_date, user_id, ignore_excessive_hours)


anomaly_service = AnomalyService()
