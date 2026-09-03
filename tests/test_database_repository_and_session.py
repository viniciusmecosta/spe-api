from unittest.mock import AsyncMock, MagicMock, patch

from pydantic import BaseModel
from sqlalchemy import Column, Integer, String

import pytest
from app.database.base import Base
from app.database.repository import BaseRepository, AsyncBaseRepository
from app.database.session import get_db, get_async_session_context


class DummyModel(Base):
    __tablename__ = "dummy_model"
    id = Column(Integer, primary_key=True)
    name = Column(String)


class DummyCreate(BaseModel):
    name: str


class DummyUpdate(BaseModel):
    name: str


class PlainObj:
    def __init__(self, name: str):
        self.name = name


def test_base_repository_sync():
    repo = BaseRepository(DummyModel)
    db = MagicMock()

    repo.get(db, 1)
    db.get.assert_called_with(DummyModel, 1)

    repo.get_multi(db, skip=10, limit=20)
    db.scalars.assert_called_once()

    db_obj = DummyModel(id=1, name="test")

    res1 = repo.create(db, obj_in={"name": "A"})
    assert isinstance(res1, DummyModel)

    res2 = repo.create(db, obj_in=DummyCreate(name="B"))
    assert isinstance(res2, DummyModel)

    res3 = repo.create(db, obj_in=PlainObj("C"))
    assert isinstance(res3, DummyModel)

    repo.update(db, db_obj=db_obj, obj_in={"name": "New"})
    assert db_obj.name == "New"

    repo.update(db, db_obj=db_obj, obj_in=DummyUpdate(name="Newer"))
    assert db_obj.name == "Newer"

    repo.update(db, db_obj=db_obj, obj_in=PlainObj("Newest"))
    assert db_obj.name == "Newest"

    db.get.return_value = db_obj
    removed = repo.remove(db, id=1)
    assert removed == db_obj
    db.delete.assert_called_with(db_obj)

    db.scalar.return_value = 5
    assert repo.count(db) == 5


@pytest.mark.asyncio
async def test_base_repository_async_create():
    repo = BaseRepository(DummyModel)
    db = AsyncMock()
    db.add = MagicMock()
    res1 = await repo.async_create(db, obj_in={"name": "A"})
    assert isinstance(res1, DummyModel)

    res2 = await repo.async_create(db, obj_in=DummyCreate(name="B"))
    assert isinstance(res2, DummyModel)

    res3 = await repo.async_create(db, obj_in=PlainObj("C"))
    assert isinstance(res3, DummyModel)


@pytest.mark.asyncio
async def test_async_base_repository():
    repo = AsyncBaseRepository(DummyModel)
    db = AsyncMock()
    db.add = MagicMock()
    db_obj = DummyModel(id=1, name="test")

    await repo.get(db, 1)
    db.get.assert_called_with(DummyModel, 1)

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [db_obj]
    db.scalars.return_value = mock_scalars
    multi = await repo.get_multi(db, skip=5, limit=10)
    assert multi == [db_obj]

    res1 = await repo.create(db, obj_in={"name": "A"})
    assert isinstance(res1, DummyModel)

    res2 = await repo.create(db, obj_in=DummyCreate(name="B"))
    assert isinstance(res2, DummyModel)

    res3 = await repo.create(db, obj_in=PlainObj("C"))
    assert isinstance(res3, DummyModel)

    await repo.update(db, db_obj=db_obj, obj_in={"name": "Up1"})
    assert db_obj.name == "Up1"

    await repo.update(db, db_obj=db_obj, obj_in=DummyUpdate(name="Up2"))
    assert db_obj.name == "Up2"

    await repo.update(db, db_obj=db_obj, obj_in=PlainObj("Up3"))
    assert db_obj.name == "Up3"

    db.get.return_value = db_obj
    removed = await repo.remove(db, id=1)
    assert removed == db_obj
    db.delete.assert_called_with(db_obj)

    db.scalar.return_value = 10
    cnt = await repo.count(db)
    assert cnt == 10


def test_get_db_session_generator():
    mock_session = MagicMock()
    with patch("app.database.session.SessionLocal", return_value=mock_session):
        gen = get_db()
        s = next(gen)
        assert s == mock_session
        try:
            next(gen)
        except StopIteration:
            pass
        mock_session.close.assert_called_once()


@pytest.mark.asyncio
async def test_get_async_session_context_rollback_on_error():
    mock_session = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)
    with patch("app.database.session.AsyncSessionLocal", return_value=mock_ctx):
        with pytest.raises(ValueError):
            async with get_async_session_context() as s:
                raise ValueError("Oops")
        mock_session.rollback.assert_called_once()


from app.database.session import get_db_session, get_async_db, set_sqlite_pragma


def test_get_db_session_ctx():
    mock_session = MagicMock()
    with patch("app.database.session.SessionLocal", return_value=mock_session):
        with get_db_session() as s:
            assert s == mock_session
        mock_session.close.assert_called_once()


@pytest.mark.asyncio
async def test_get_async_db_normal_and_error():
    mock_session = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)
    with patch("app.database.session.AsyncSessionLocal", return_value=mock_ctx):
        gen = get_async_db()
        s = await anext(gen)
        assert s == mock_session
        try:
            await anext(gen)
        except StopAsyncIteration:
            pass
        mock_session.commit.assert_called_once()

    with patch("app.database.session.AsyncSessionLocal", return_value=mock_ctx):
        gen_err = get_async_db()
        await anext(gen_err)
        with pytest.raises(RuntimeError):
            await gen_err.athrow(RuntimeError("Db Fail"))
        mock_session.rollback.assert_called_once()


def test_set_sqlite_pragma():
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    with patch("app.database.session.db_uri_sync", "sqlite:///test.db"):
        set_sqlite_pragma(conn, None)
        cursor.execute.assert_called()
        cursor.close.assert_called_once()


def test_session_uri_prefixes():
    import importlib
    from app.core.config import settings
    import app.database.session as sess_mod

    orig_uri = settings.SQLALCHEMY_DATABASE_URI
    try:
        with patch("sqlalchemy.create_engine"), patch("sqlalchemy.ext.asyncio.create_async_engine"), patch(
                "sqlalchemy.event.listen"):
            with patch.object(settings, "SQLALCHEMY_DATABASE_URI", "sqlite+aiosqlite:///test.db"):
                importlib.reload(sess_mod)
            with patch.object(settings, "SQLALCHEMY_DATABASE_URI", "postgresql+asyncpg://user:pass@localhost/db"):
                importlib.reload(sess_mod)
            with patch.object(settings, "SQLALCHEMY_DATABASE_URI", "postgresql://user:pass@localhost/db"):
                importlib.reload(sess_mod)
    finally:
        with patch.object(settings, "SQLALCHEMY_DATABASE_URI", orig_uri):
            importlib.reload(sess_mod)


@pytest.mark.asyncio
async def test_get_async_session_context_normal():
    mock_session = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)
    with patch("app.database.session.AsyncSessionLocal", return_value=mock_ctx):
        async with get_async_session_context() as s:
            assert s == mock_session
        mock_session.commit.assert_called_once()
