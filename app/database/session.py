from collections.abc import Generator
from contextlib import contextmanager
from typing import AsyncGenerator

from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

SQLITE_AIOSQLITE_PREFIX = "sqlite+aiosqlite://"
SQLITE_SYNC_PREFIX = "sqlite://"
POSTGRESQL_ASYNCPG_PREFIX = "postgresql+asyncpg://"
POSTGRESQL_SYNC_PREFIX = "postgresql://"

connect_args = {}
if settings.SQLALCHEMY_DATABASE_URI.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

db_uri_sync = settings.SQLALCHEMY_DATABASE_URI
if db_uri_sync.startswith(SQLITE_AIOSQLITE_PREFIX):
    db_uri_sync = db_uri_sync.replace(SQLITE_AIOSQLITE_PREFIX, SQLITE_SYNC_PREFIX, 1)
elif db_uri_sync.startswith(POSTGRESQL_ASYNCPG_PREFIX):
    db_uri_sync = db_uri_sync.replace(POSTGRESQL_ASYNCPG_PREFIX, POSTGRESQL_SYNC_PREFIX, 1)

engine = create_engine(db_uri_sync, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

db_uri_async = settings.SQLALCHEMY_DATABASE_URI
if db_uri_async.startswith(SQLITE_SYNC_PREFIX) and not db_uri_async.startswith(SQLITE_AIOSQLITE_PREFIX):
    db_uri_async = db_uri_async.replace(SQLITE_SYNC_PREFIX, SQLITE_AIOSQLITE_PREFIX, 1)
elif db_uri_async.startswith(POSTGRESQL_SYNC_PREFIX) and not db_uri_async.startswith(POSTGRESQL_ASYNCPG_PREFIX):
    db_uri_async = db_uri_async.replace(POSTGRESQL_SYNC_PREFIX, POSTGRESQL_ASYNCPG_PREFIX, 1)

async_engine = create_async_engine(db_uri_async, connect_args=connect_args)
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


def set_sqlite_pragma(dbapi_connection, connection_record):
    if db_uri_sync.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.execute("PRAGMA mmap_size=3000000000")
        cursor.close()


event.listen(engine, "connect", set_sqlite_pragma)
event.listen(async_engine.sync_engine, "connect", set_sqlite_pragma)


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
