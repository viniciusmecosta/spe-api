from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, text

from app.database.base import Base


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("ix_refresh_tokens_family_id", "family_id"),
        Index("ix_refresh_tokens_user_id", "user_id"),
        Index("ix_refresh_tokens_expires_at", "expires_at"),
        Index(
            "ix_refresh_tokens_active_family",
            "family_id",
            postgresql_where=text("used_at IS NULL AND revoked_at IS NULL"),
            sqlite_where=text("used_at IS NULL AND revoked_at IS NULL"),
        ),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash = Column(String(64), nullable=False, unique=True)
    family_id = Column(String(32), nullable=False)
    auth_version = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
