from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    text,
)

from app.database.base import Base


class DailySummary(Base):
    __tablename__ = "daily_summaries"
    __table_args__ = (
        UniqueConstraint("user_id", "apuration_date", name="uq_daily_summaries_user_date"),
        Index(
            "ix_daily_summaries_pending", "updated_at", "id",
            postgresql_where=text("pending_recalculation = TRUE"),
        ),
        CheckConstraint(
            "worked_minutes >= 0 AND accounted_minutes >= 0 AND expected_minutes >= 0 "
            "AND excess_minutes >= 0 AND authorized_excess_minutes >= 0 "
            "AND missing_minutes >= 0 AND waiver_minutes >= 0",
            name="ck_daily_summaries_nonnegative",
        ),
        CheckConstraint(
            "authorized_excess_minutes <= excess_minutes",
            name="ck_daily_summaries_authorized",
        ),
        CheckConstraint(
            "accounted_minutes <= worked_minutes", name="ck_daily_summaries_accounted"
        ),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    apuration_date = Column(Date, nullable=False)
    worked_minutes = Column(Integer, nullable=False, server_default=text("0"))
    accounted_minutes = Column(Integer, nullable=False, server_default=text("0"))
    expected_minutes = Column(Integer, nullable=False, server_default=text("0"))
    excess_minutes = Column(Integer, nullable=False, server_default=text("0"))
    authorized_excess_minutes = Column(Integer, nullable=False, server_default=text("0"))
    missing_minutes = Column(Integer, nullable=False, server_default=text("0"))
    waiver_minutes = Column(Integer, nullable=False, server_default=text("0"))
    pending_recalculation = Column(Boolean, nullable=False, server_default=text("FALSE"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))
