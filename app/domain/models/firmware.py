from sqlalchemy import Column, Integer, String, DateTime

from app.database.base import Base
from app.domain.models.device import get_local_time


class Firmware(Base):
    __tablename__ = "firmwares"

    id = Column(Integer, primary_key=True, index=True)
    version = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=get_local_time)
