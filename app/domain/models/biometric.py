import pytz
from datetime import datetime
from sqlalchemy import Column, Integer, ForeignKey, String, DateTime
from sqlalchemy.orm import relationship

from app.core.config import settings
from app.database.base import Base


def get_local_time():
    return datetime.now(pytz.timezone(settings.TIMEZONE))

class UserBiometric(Base):
    __tablename__ = "user_biometrics"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    sensor_index = Column(Integer, nullable=True)
    template_data = Column(String, nullable=True)
    description = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=get_local_time)

    user = relationship("User", back_populates="biometrics")
    time_records = relationship("TimeRecord", back_populates="biometric")