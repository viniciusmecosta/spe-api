from datetime import date, datetime, timedelta
from typing import Any

from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.reports.report_schemas import (
    DailyExcessInfo,
    DailyReportItem,
    HistoryDay,
    HistoryPunch,
    PunchDetail,
    ReportAdjustmentItem,
)
from app.features.time_records.time_record_models import TimeRecord
from app.shared.enums import AdjustmentStatus, AdjustmentType, DayOfWeek

WEEKEND_STATUS = "Fim de semana"


class ReportResponseBuilder:

    def format_duration(self, total_seconds: float) -> str:
        total_minutes = int(round(total_seconds / 60))
        hours = total_minutes // 60
        minutes = total_minutes % 60
        return f"{hours:02d}:{minutes:02d}"

    def _build_history_punches(self, day_records, is_manager) -> list:
        punches = []
        for rec in day_records:
            punch_data = {
                "id": rec.id,
                "short_id": rec.short_id,
                "time": rec.record_datetime.strftime("%H:%M"),
                "record_type": rec.record_type.value,
                "original_record_id": rec.original_record_id,
                "is_ignored": bool(rec.is_ignored),
            }
            if is_manager:
                punch_data.update({
                    "ip_address": rec.ip_address,
                    "device_name": rec.device_name,
                    "platform": rec.platform,
                    "biometric_id": rec.biometric_id,
                    "edited_by": rec.editor_name,
                    "edit_justification": rec.edit_justification if rec.edit_justification else None
                })
            punches.append(HistoryPunch(**punch_data))
        return punches

    def _determine_history_status(self, has_records: bool, has_holiday: bool, is_weekend: bool, has_abono: bool,
                                  is_today: bool) -> str:
        if has_records:
            return "Normal"
        if has_holiday:
            return "Feriado"
        if is_weekend:
            return WEEKEND_STATUS
        if has_abono:
            return "Abono"
        if is_today:
            return ""
        return "Falta"

    def _determine_excess_info(self, accounted_res, daily_excess_adj, schedule: Any | None = None) -> tuple[bool, str | None, int | None]:
        is_enabled = bool(schedule and getattr(schedule, "is_daily_excess_enabled", False))
        if not is_enabled:
            return False, None, None

        total_secs = getattr(accounted_res, 'total_excess_seconds', 0.0) or 0.0
        has_excess = bool(total_secs > 0 or (daily_excess_adj is not None))
        daily_excess_id = daily_excess_adj.id if daily_excess_adj else None
        if daily_excess_adj:
            excess_status = daily_excess_adj.status.value
        elif total_secs > 0:
            excess_status = AdjustmentStatus.PENDING.value
        else:
            excess_status = None

        return has_excess, excess_status, daily_excess_id

    def _build_daily_excess_info(
            self,
            accounted_res: Any,
            daily_excess_adj: Any,
            has_excess: bool,
            excess_status: str | None,
            daily_excess_id: int | None,
    ) -> DailyExcessInfo | None:
        if not has_excess:
            return None

        total_sec = float(getattr(accounted_res, 'total_excess_seconds', 0.0) or 0.0)
        if total_sec <= 0.0 and daily_excess_adj:
            amount = getattr(daily_excess_adj, 'amount_hours', 0.0)
            if isinstance(amount, (int, float)):
                total_sec = float(amount * 3600.0)

        approved_sec = float(getattr(accounted_res, 'approved_seconds', 0.0) or 0.0)
        if approved_sec <= 0.0 and daily_excess_adj and getattr(daily_excess_adj, 'status', None) == AdjustmentStatus.APPROVED:
            appr_amount = getattr(daily_excess_adj, 'approved_amount_hours', None)
            if isinstance(appr_amount, (int, float)):
                approved_sec = min(total_sec, max(0.0, float(appr_amount * 3600.0)))
            elif total_sec > 0:
                approved_sec = total_sec

        unapproved_sec = max(0.0, total_sec - approved_sec)

        total_min = int(round(total_sec / 60))
        approved_min = int(round(approved_sec / 60))
        unapproved_min = int(round(unapproved_sec / 60))

        total_hrs = round(total_sec / 3600.0, 2)
        approved_hrs = round(approved_sec / 3600.0, 2)
        unapproved_hrs = round(unapproved_sec / 3600.0, 2)

        total_time_str = self.format_duration(total_sec)
        approved_time_str = self.format_duration(approved_sec)
        unapproved_time_str = self.format_duration(unapproved_sec)

        return DailyExcessInfo(
            has_excess=True,
            status=excess_status,
            daily_excess_id=daily_excess_id,
            total_minutes=total_min,
            total_time=total_time_str,
            total_hours=total_hrs,
            approved_minutes=approved_min,
            approved_time=approved_time_str,
            approved_hours=approved_hrs,
            unapproved_minutes=unapproved_min,
            unapproved_time=unapproved_time_str,
            unapproved_hours=unapproved_hrs,
            blocked_minutes=unapproved_min,
            blocked_time=unapproved_time_str,
            blocked_hours=unapproved_hrs,
        )

    def _to_report_adjustment_item(self, adj: Any, current: date) -> ReportAdjustmentItem:
        if isinstance(adj, ReportAdjustmentItem):
            return adj
        if isinstance(adj, dict):
            return ReportAdjustmentItem(**adj)
        c_at = getattr(adj, 'created_at', None)
        r_at = getattr(adj, 'reviewed_at', None)
        return ReportAdjustmentItem(
            id=getattr(adj, 'id', 0) or 0,
            user_id=getattr(adj, 'user_id', 0) or 0,
            adjustment_type=getattr(adj, 'adjustment_type', AdjustmentType.OTHER),
            record_type=getattr(adj, 'record_type', None),
            target_date=getattr(adj, 'target_date', current),
            time=getattr(adj, 'time', None),
            amount_hours=getattr(adj, 'amount_hours', None),
            approved_amount_hours=getattr(adj, 'approved_amount_hours', None),
            reason_text=getattr(adj, 'reason_text', None),
            status=getattr(adj, 'status', AdjustmentStatus.PENDING),
            manager_id=getattr(adj, 'manager_id', None),
            manager_comment=getattr(adj, 'manager_comment', None),
            created_at=c_at if isinstance(c_at, datetime) else None,
            reviewed_at=r_at if isinstance(r_at, datetime) else None,
        )

    def _build_day_adjustments_list(self, day_adjustments: list | None, current: date) -> list[ReportAdjustmentItem]:
        filtered = []
        for adj in (day_adjustments or []):
            item = self._to_report_adjustment_item(adj, current)
            filtered.append(item)
        return filtered

    def _build_history_day(
            self,
            current: date,
            today_date: date,
            records: list[TimeRecord],
            holidays: list,
            anomalies: list,
            period_result,
            is_manager: bool,
            schedule: Any | None = None,
            daily_excess_adj: AdjustmentRequest | None = None,
            day_adjustments: list[AdjustmentRequest] | None = None,
    ) -> HistoryDay:
        day_records = [r for r in records if r.record_datetime.date() == current]
        day_records.sort(key=lambda x: x.record_datetime)

        holiday = next((h for h in holidays if h.date == current), None)
        day_anomalies = [a for a in anomalies if a.date == current]

        daily_res = period_result.daily_results[current]
        worked_seconds = daily_res.gross_worked_seconds
        abono = period_result.daily_waivers[current]

        accounted_res = period_result.daily_accounted_results[current]
        accounted_time_str = self.format_duration(accounted_res.accounted_seconds)
        has_excess, excess_status, daily_excess_id = self._determine_excess_info(accounted_res, daily_excess_adj, schedule)
        excess_info = self._build_daily_excess_info(accounted_res, daily_excess_adj, has_excess, excess_status, daily_excess_id)

        day_adjustments_list = self._build_day_adjustments_list(day_adjustments, current)
        punches = self._build_history_punches(day_records, is_manager)

        target_day = DayOfWeek(current.weekday())
        day_name = target_day.abreviado
        is_weekend = target_day in (DayOfWeek.SABADO, DayOfWeek.DOMINGO)

        status = self._determine_history_status(
            has_records=bool(day_records),
            has_holiday=bool(holiday),
            is_weekend=is_weekend,
            has_abono=bool(abono),
            is_today=current == today_date
        )

        total_minutes = int(round(worked_seconds / 60))
        hours = total_minutes // 60
        minutes = total_minutes % 60
        worked_time_str = f"{hours:02d}:{minutes:02d}"

        anomalies_list = [a.description for a in day_anomalies]

        return HistoryDay(
            date=current,
            day_name=day_name,
            is_holiday=bool(holiday),
            is_weekend=is_weekend,
            is_absent=(status == "Falta"),
            status=status,
            holiday_name=holiday.name if holiday else None,
            worked_time=worked_time_str,
            accounted_time=accounted_time_str,
            punches=punches,
            has_anomaly=len(anomalies_list) > 0,
            anomalies=anomalies_list,
            abono_hours=abono.amount_hours if abono else None,
            abono_id=abono.id if abono and is_manager else None,
            has_excess=has_excess,
            excess_status=excess_status,
            daily_excess_id=daily_excess_id,
            excess=excess_info,
            daily_excess=excess_info,
            adjustments=day_adjustments_list,
        )

    def _build_detailed_punches(self, day_records: list[TimeRecord], is_maintainer: bool) -> list[PunchDetail]:
        if not is_maintainer:
            return []
        detailed_punches = []
        for rec in day_records:
            detailed_punches.append(PunchDetail(
                id=rec.id,
                short_id=rec.short_id,
                time=rec.record_datetime.strftime("%H:%M:%S"),
                record_type=rec.record_type.value,
                ip_address=rec.ip_address,
                device_name=rec.device_name,
                platform=rec.platform,
                biometric_id=rec.biometric_id,
                edited_by=rec.editor_name,
                edit_justification=rec.edit_justification if rec.edit_justification else None,
                original_record_id=rec.original_record_id,
                is_ignored=bool(rec.is_ignored),
            ))
        return detailed_punches

    def _determine_daily_status(self, is_future: bool, is_holiday: bool, is_weekend: bool, is_waiver: bool,
                                worked_seconds: float, expected_seconds: float, is_today: bool,
                                has_schedule: bool) -> str:
        if is_holiday:
            return "Feriado"
        if is_waiver:
            return "Abono"
            
        if is_future:
            if is_weekend:
                return WEEKEND_STATUS
            return ""
            
        if is_weekend:
            if worked_seconds > 0:
                return "Normal"
            return WEEKEND_STATUS
            
        if worked_seconds > 0:
            return "Normal"
            
        if expected_seconds > 0:
            if is_today:
                return ""
            return "Falta"
            
        if not has_schedule:
            return "-"
            
        return "Normal"

    def _compute_daily_hours_and_balance(self, daily_res, expected_seconds: float):
        worked_seconds = daily_res.gross_worked_seconds
        day_worked_hours = worked_seconds / 3600.0
        day_expected_hours = expected_seconds / 3600.0
        day_extra = daily_res.extra_seconds / 3600.0
        day_missing = daily_res.missing_seconds / 3600.0
        day_balance = day_extra - day_missing
        return worked_seconds, day_worked_hours, day_expected_hours, day_extra, day_missing, day_balance

    def _build_daily_report_item(
            self,
            current: date,
            today_date: date,
            all_records: list[TimeRecord],
            holidays: list,
            period_result,
            has_schedule: bool,
            is_maintainer: bool,
            schedule: Any | None = None,
            daily_excess_adj: AdjustmentRequest | None = None,
            day_adjustments: list[AdjustmentRequest] | None = None,
    ) -> DailyReportItem:
        is_future = current > today_date
        is_today = current == today_date

        day_records = sorted([r for r in all_records if r.record_datetime.date() == current], key=lambda x: x.record_datetime)
        holiday = next((h for h in holidays if h.date == current), None)
        holiday_name = holiday.name if holiday else None

        daily_res = period_result.daily_results[current]
        adjustment_day = period_result.daily_waivers[current]
        is_waiver = adjustment_day is not None
        adj_id = adjustment_day.id if adjustment_day else None
        target_day = DayOfWeek(current.weekday())
        is_weekend = target_day in (DayOfWeek.SABADO, DayOfWeek.DOMINGO)

        expected_seconds = period_result.daily_expected_seconds[current]
        worked_seconds, day_worked_hours, day_expected_hours, day_extra, day_missing, day_balance = self._compute_daily_hours_and_balance(daily_res, expected_seconds)

        accounted_res = period_result.daily_accounted_results[current]
        has_excess, excess_status, daily_excess_id = self._determine_excess_info(accounted_res, daily_excess_adj, schedule)
        excess_info = self._build_daily_excess_info(accounted_res, daily_excess_adj, has_excess, excess_status, daily_excess_id)

        punches = list(daily_res.punches)
        if is_waiver:
            formatted_waiver = self.format_duration(daily_res.waiver_seconds)
            if formatted_waiver and formatted_waiver != "00:00":
                punches.append(f"Abono: {formatted_waiver}")

        status = self._determine_daily_status(
            is_future, holiday is not None, is_weekend, is_waiver, worked_seconds, expected_seconds, is_today, has_schedule
        )

        return DailyReportItem(
            date=current,
            day_name=target_day.abreviado,
            is_holiday=holiday is not None,
            holiday_name=holiday_name,
            is_weekend=is_weekend,
            status=status,
            entries=daily_res.entries,
            exits=daily_res.exits,
            punches=punches,
            detailed_punches=self._build_detailed_punches(day_records, is_maintainer) if is_maintainer else None,
            adjustment_id=adj_id,
            worked_hours=round(day_worked_hours, 2),
            expected_hours=round(day_expected_hours, 2),
            balance_hours=round(day_balance, 2),
            extra_hours=round(day_extra, 2),
            missing_hours=round(day_missing, 2),
            worked_minutes=int(round(worked_seconds / 60)),
            worked_time=self.format_duration(worked_seconds),
            accounted_time=self.format_duration(accounted_res.accounted_seconds),
            expected_time=self.format_duration(expected_seconds),
            unapproved_extra_time=self.format_duration(daily_res.unapproved_extra_seconds),
            has_excess=has_excess,
            excess_status=excess_status,
            daily_excess_id=daily_excess_id,
            excess=excess_info,
            daily_excess=excess_info,
            adjustments=self._build_day_adjustments_list(day_adjustments, current),
        )

    def _get_schedule_for_date(self, user, current_date, target_day_val):
        if not user or not user.historical_schedules:
            return None
        for s in user.historical_schedules:
            if s.valid_from <= current_date:
                if s.valid_until is None or s.valid_until >= current_date:
                    if s.day_of_week == target_day_val:
                        return s
        return None

    def build_history_days(self, start_date, end_date, today_date, records, holidays, anomalies, period_result, is_manager, user, all_adjustments):
        history_days = []
        adjs_by_date = {}
        excess_by_date = {}
        for adj in all_adjustments:
            adjs_by_date.setdefault(adj.target_date, []).append(adj)
            if adj.adjustment_type == AdjustmentType.DAILY_EXCESS:
                excess_by_date[adj.target_date] = adj
                
        current = start_date
        while current <= end_date:
            target_day_val = DayOfWeek.from_date(current).value
            day_schedule = self._get_schedule_for_date(user, current, target_day_val)
            day_excess = excess_by_date.get(current)
            day_adjs = adjs_by_date.get(current, [])

            history_day = self._build_history_day(
                current=current,
                today_date=today_date,
                records=records,
                holidays=holidays,
                anomalies=anomalies,
                period_result=period_result,
                is_manager=is_manager,
                schedule=day_schedule,
                daily_excess_adj=day_excess,
                day_adjustments=day_adjs,
            )
            history_days.append(history_day)
            current += timedelta(days=1)
        return history_days

    def build_advanced_daily_details(self, start_date, end_date, today_date, all_records, holidays, period_result, has_schedule, is_maintainer, user, all_adjustments):
        daily_details = []
        days_worked_count = 0
        absences_count = 0
        
        adjs_by_date = {}
        excess_by_date = {}
        for adj in all_adjustments:
            adjs_by_date.setdefault(adj.target_date, []).append(adj)
            if adj.adjustment_type == AdjustmentType.DAILY_EXCESS:
                excess_by_date[adj.target_date] = adj
                
        current = start_date
        while current <= end_date:
            target_day_val = DayOfWeek.from_date(current).value
            day_schedule = self._get_schedule_for_date(user, current, target_day_val)
            day_excess = excess_by_date.get(current)
            day_adjs = adjs_by_date.get(current, [])

            item = self._build_daily_report_item(
                current=current,
                today_date=today_date,
                all_records=all_records,
                holidays=holidays,
                period_result=period_result,
                has_schedule=has_schedule,
                is_maintainer=is_maintainer,
                schedule=day_schedule,
                daily_excess_adj=day_excess,
                day_adjustments=day_adjs,
            )
            daily_details.append(item)

            if item.worked_hours > 0:
                days_worked_count += 1
            if item.worked_hours == 0 and item.expected_hours > 0 and not item.is_weekend and not item.is_holiday and not item.adjustment_id and current < today_date:
                absences_count += 1

            current += timedelta(days=1)
        return daily_details, days_worked_count, absences_count
