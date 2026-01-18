from sqlalchemy import Column, Integer, String, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.database.base import Base


class UserBiometric(Base):
    __tablename__ = "user_biometrics"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    sensor_index = Column(Integer, nullable=False, unique=True)
    template_data = Column(Text, nullable=False)
    label = Column(String, nullable=True)

    user = relationship("User", back_populates="biometrics")
    time_records = relationship("TimeRecord", back_populates="biometric")
