from collections.abc import Generator
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime
from typing import Any, AsyncGenerator
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

POSTGRESQL_ASYNCPG_PREFIX = "postgresql+asyncpg://"
POSTGRESQL_SYNC_PREFIX = "postgresql://"

pool_kwargs = {
    "pool_pre_ping": True,
    "pool_size": settings.DB_POOL_SIZE,
    "max_overflow": settings.DB_MAX_OVERFLOW,
    "pool_timeout": settings.DB_POOL_TIMEOUT_SECONDS,
    "pool_recycle": 1800,
}


def connection_settings() -> dict[str, str]:
    return {
        "TimeZone": settings.TIMEZONE,
        "statement_timeout": str(settings.DB_STATEMENT_TIMEOUT_MS),
        "lock_timeout": str(settings.DB_LOCK_TIMEOUT_MS),
        "idle_in_transaction_session_timeout": str(settings.DB_IDLE_TRANSACTION_TIMEOUT_MS),
    }


def on_sync_connect(dbapi_connection, connection_record):
    # Commit session settings outside any application transaction.
    previous_autocommit = dbapi_connection.autocommit
    dbapi_connection.autocommit = True
    try:
        with dbapi_connection.cursor() as cursor:
            for name, value in connection_settings().items():
                cursor.execute("SELECT set_config(%s, %s, false)", (name, value))
    finally:
        dbapi_connection.autocommit = previous_autocommit

db_uri_sync = settings.SQLALCHEMY_DATABASE_URI
if db_uri_sync.startswith(POSTGRESQL_ASYNCPG_PREFIX):
    db_uri_sync = db_uri_sync.replace(POSTGRESQL_ASYNCPG_PREFIX, POSTGRESQL_SYNC_PREFIX, 1)

sync_connect_args = (
    {"connect_timeout": settings.DB_CONNECT_TIMEOUT_SECONDS}
    if db_uri_sync.startswith("postgresql") else {}
)
engine = create_engine(db_uri_sync, connect_args=sync_connect_args, **pool_kwargs)
if engine.dialect.name == "postgresql":
    event.listen(engine, "connect", on_sync_connect)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

db_uri_async = settings.SQLALCHEMY_DATABASE_URI
if db_uri_async.startswith(POSTGRESQL_SYNC_PREFIX) and not db_uri_async.startswith(POSTGRESQL_ASYNCPG_PREFIX):
    db_uri_async = db_uri_async.replace(POSTGRESQL_SYNC_PREFIX, POSTGRESQL_ASYNCPG_PREFIX, 1)

async_connect_args = (
    {"timeout": settings.DB_CONNECT_TIMEOUT_SECONDS, "server_settings": connection_settings()}
    if db_uri_async.startswith("postgresql") else {}
)
async_engine = create_async_engine(db_uri_async, connect_args=async_connect_args, **pool_kwargs)


class ApurationAsyncSession(AsyncSession):
    pass


AsyncSessionLocal = async_sessionmaker(
    bind=async_engine, class_=ApurationAsyncSession, expire_on_commit=False, autoflush=False
)


def encode_timestamptz(v: Any) -> str | None:
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


def decode_timestamptz(s: str | None, tz: ZoneInfo) -> datetime | None:
    if s is None:
        return None
    return datetime.fromisoformat(s).astimezone(tz)


def on_async_connect(dbapi_connection, connection_record):
    if not hasattr(dbapi_connection, "run_async"):
        return

    tz = ZoneInfo(settings.TIMEZONE)

    async def setup_connection(conn):
        await conn.set_type_codec(
            "timestamptz",
            encoder=encode_timestamptz,
            decoder=lambda s: decode_timestamptz(s, tz),
            schema="pg_catalog",
            format="text",
        )

    dbapi_connection.run_async(setup_connection)


try:
    event.listen(async_engine.sync_engine, "connect", on_async_connect)
except Exception:
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_async_session_context() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


from app.features.daily_summaries.daily_summary_events import (
    register_daily_summary_events,
)

register_daily_summary_events()
