import os
import importlib
import uuid
from pathlib import Path

import psycopg2
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from psycopg2 import sql
from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings


@pytest.fixture
def pg_url(monkeypatch):
    configured = os.getenv("SPE_TEST_DATABASE_URL")
    if not configured:
        pytest.skip(
            "SPE_TEST_DATABASE_URL must point to a disposable PostgreSQL test server"
        )
    url = make_url(configured)
    if url.database not in {"spe_test", "postgres"}:
        pytest.fail(
            "SPE_TEST_DATABASE_URL must use the dedicated spe_test or postgres admin database"
        )
    admin = psycopg2.connect(
        url.set(drivername="postgresql").render_as_string(hide_password=False)
    )
    admin.autocommit = True
    name = "spe_test_" + uuid.uuid4().hex
    with admin.cursor() as cursor:
        cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    target = url.set(drivername="postgresql+asyncpg", database=name).render_as_string(
        hide_password=False
    )
    monkeypatch.setattr(settings, "SQLALCHEMY_DATABASE_URI", target)
    monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", target)
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    try:
        command.upgrade(config, "head")
        yield target
    finally:
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s",
                (name,),
            )
            cursor.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
        admin.close()


@pytest_asyncio.fixture
async def pg_session_factory(pg_url, monkeypatch, tmp_path):
    import app.database.session as database

    summary_module = importlib.import_module(
        "app.features.daily_summaries.daily_summary_service"
    )

    engine = create_async_engine(pg_url)
    event.listen(engine.sync_engine, "connect", database.on_async_connect)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    monkeypatch.setattr(database, "AsyncSessionLocal", factory)
    monkeypatch.setattr(summary_module, "AsyncSessionLocal", factory)
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    try:
        yield factory
    finally:
        await engine.dispose()
