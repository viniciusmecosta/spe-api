from datetime import datetime
from sqlalchemy import Column, Integer, ForeignKey, String, DateTime
from sqlalchemy.orm import relationship

from app.database.base import Base


class UserBiometric(Base):
    __tablename__ = "user_biometrics"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    sensor_index = Column(Integer, nullable=True)
    template_data = Column(String, nullable=True)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="biometrics")
    time_records = relationship("TimeRecord", back_populates="biometric")
