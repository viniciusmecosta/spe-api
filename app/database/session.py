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

connect_args = {}
if settings.SQLALCHEMY_DATABASE_URI.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

db_uri_sync = settings.SQLALCHEMY_DATABASE_URI
if db_uri_sync.startswith("sqlite+aiosqlite://"):
    db_uri_sync = db_uri_sync.replace("sqlite+aiosqlite://", "sqlite://", 1)
elif db_uri_sync.startswith("postgresql+asyncpg://"):
    db_uri_sync = db_uri_sync.replace("postgresql+asyncpg://", "postgresql://", 1)

engine = create_engine(db_uri_sync, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

db_uri_async = settings.SQLALCHEMY_DATABASE_URI
if db_uri_async.startswith("sqlite://") and not db_uri_async.startswith("sqlite+aiosqlite://"):
    db_uri_async = db_uri_async.replace("sqlite://", "sqlite+aiosqlite://", 1)
elif db_uri_async.startswith("postgresql://") and not db_uri_async.startswith("postgresql+asyncpg://"):
    db_uri_async = db_uri_async.replace("postgresql://", "postgresql+asyncpg://", 1)

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
