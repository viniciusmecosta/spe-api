import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import get_db_session
from app.domain.models.adjustment import AdjustmentRequest
from app.domain.models.enums import RecordType, AdjustmentType, AdjustmentStatus
from app.domain.models.time_record import TimeRecord
from app.domain.models.user import UserWorkScheduleConfig

logger = logging.getLogger(__name__)


class ToleranceCronService:
    def process_unverified_entries(self):
        tz = ZoneInfo(settings.TIMEZONE)
        now = datetime.now(tz)
        
        try:
            with get_db_session() as db:
                unverified_entries = db.query(TimeRecord).filter(
                    TimeRecord.record_type == RecordType.ENTRY,
                    TimeRecord.is_verified.is_(False),
                    TimeRecord.deleted_at.is_(None)
                ).all()
                
                for record in unverified_entries:
                    record_date = record.record_datetime.date()
                    
                    config = db.query(UserWorkScheduleConfig).filter(
                        UserWorkScheduleConfig.user_id == record.user_id,
                        UserWorkScheduleConfig.day_of_week == record_date.weekday(),
                        UserWorkScheduleConfig.valid_from <= record_date,
                        (UserWorkScheduleConfig.valid_until.is_(None) | (UserWorkScheduleConfig.valid_until >= record_date))
                    ).order_by(UserWorkScheduleConfig.valid_from.desc()).first()
                    
                    if not config or not config.entry_1:
                        record.is_verified = True
                        continue
                        
                    official_datetime = datetime.combine(record_date, config.entry_1, tzinfo=tz)
                    diff_seconds = (official_datetime - record.record_datetime).total_seconds()
                    diff_minutes = diff_seconds / 60.0
                    
                    if diff_minutes <= 5:
                        record.is_verified = True
                    else:
                        if now >= official_datetime:
                            extra_minutes = diff_minutes - 5
                            amount_hours = extra_minutes / 60.0
                            
                            existing_adjustment = db.query(AdjustmentRequest).filter(
                                AdjustmentRequest.user_id == record.user_id,
                                AdjustmentRequest.target_date == record_date,
                                AdjustmentRequest.adjustment_type == AdjustmentType.EXTRA_TIME
                            ).first()
                            
                            if not existing_adjustment:
                                adjustment = AdjustmentRequest(
                                    user_id=record.user_id,
                                    adjustment_type=AdjustmentType.EXTRA_TIME,
                                    record_type=RecordType.ENTRY,
                                    target_date=record_date,
                                    amount_hours=amount_hours,
                                    reason_text=f"Tempo extra de entrada detectado ({int(extra_minutes)} min).",
                                    status=AdjustmentStatus.PENDING,
                                    created_at=now
                                )
                                db.add(adjustment)
                                
                            record.is_verified = True
                        else:
                            pass
                            
                db.commit()
        except SQLAlchemyError as e:
            logger.error(f"Erro ao processar tolerancia de entradas: {e}")

tolerance_cron_service = ToleranceCronService()
