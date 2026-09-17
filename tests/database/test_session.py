import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from app.database.session import get_db, get_db_session


def test_get_db_session_exception():
    def _trigger():
        with get_db_session():
            raise RuntimeError("Database error test")

    with pytest.raises(RuntimeError, match="Database error test"):
        _trigger()


def test_get_db_session_success(mocker):
    mock_session = MagicMock()
    mocker.patch("app.database.session.SessionLocal", return_value=mock_session)
    with get_db_session() as s:
        assert s == mock_session
    mock_session.close.assert_called_once()


def test_get_db_generator(mocker):
    mock_session = MagicMock()
    mocker.patch("app.database.session.SessionLocal", return_value=mock_session)
    gen = get_db()
    s = next(gen)
    assert s == mock_session
    try:
        next(gen)
    except StopIteration:
        pass
    mock_session.close.assert_called_once()


def test_encode_timestamptz():
    from app.database.session import encode_timestamptz
    assert encode_timestamptz(None) is None
    dt = datetime(2026, 9, 17, 12, 0, 0)
    assert encode_timestamptz(dt) == dt.isoformat()
    assert encode_timestamptz("2026-09-17") == "2026-09-17"


def test_decode_timestamptz():
    from zoneinfo import ZoneInfo
    from app.database.session import decode_timestamptz
    tz = ZoneInfo("America/Fortaleza")
    assert decode_timestamptz(None, tz) is None
    res = decode_timestamptz("2026-09-17T12:00:00", tz)
    assert res is not None
    assert res.tzinfo == tz


def test_on_async_connect_without_run_async():
    from app.database.session import on_async_connect
    conn = MagicMock(spec=[])
    on_async_connect(conn, None)


@pytest.mark.asyncio
async def test_on_async_connect_with_run_async():
    from unittest.mock import AsyncMock
    from app.database.session import on_async_connect
    fake_conn = MagicMock()
    fake_conn.set_type_codec = AsyncMock()

    captured_coro = None

    class FakeDbApiConn:
        def run_async(self, coro_fn):
            nonlocal captured_coro
            captured_coro = coro_fn

    on_async_connect(FakeDbApiConn(), None)
    assert captured_coro is not None
    await captured_coro(fake_conn)
    fake_conn.set_type_codec.assert_awaited_once()
    call_kwargs = fake_conn.set_type_codec.call_args[1]
    assert call_kwargs["format"] == "text"
    assert call_kwargs["encoder"](None) is None
    assert call_kwargs["decoder"](None) is None


@pytest.mark.asyncio
async def test_get_async_db(mocker):
    from app.database.session import get_async_db
    mock_session = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.close = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = None
    mocker.patch("app.database.session.AsyncSessionLocal", return_value=mock_cm)

    gen = get_async_db()
    s = await gen.__anext__()
    assert s == mock_session
    try:
        await gen.__anext__()
    except StopAsyncIteration:
        pass
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_async_db_exception(mocker):
    from app.database.session import get_async_db
    mock_session = MagicMock()
    mock_session.commit = AsyncMock(side_effect=RuntimeError("Commit failed"))
    mock_session.rollback = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = None
    mocker.patch("app.database.session.AsyncSessionLocal", return_value=mock_cm)

    gen = get_async_db()
    s = await gen.__anext__()
    assert s == mock_session
    with pytest.raises(RuntimeError, match="Commit failed"):
        await gen.__anext__()
    mock_session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_async_session_context(mocker):
    from app.database.session import get_async_session_context
    mock_session = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = None
    mocker.patch("app.database.session.AsyncSessionLocal", return_value=mock_cm)

    async with get_async_session_context() as s:
        assert s == mock_session
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_async_session_context_exception(mocker):
    from app.database.session import get_async_session_context
    mock_session = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = None
    mocker.patch("app.database.session.AsyncSessionLocal", return_value=mock_cm)

    async def _trigger():
        async with get_async_session_context():
            raise ValueError("Context error")

    with pytest.raises(ValueError, match="Context error"):
        await _trigger()
    mock_session.rollback.assert_awaited_once()


def test_session_module_sync_uri_prefix(monkeypatch):
    import importlib
    import app.core.config
    import app.database.session
    monkeypatch.setattr(app.core.config.settings, "SQLALCHEMY_DATABASE_URI", "postgresql://user:pass@localhost:5432/spe_db")
    importlib.reload(app.database.session)
    monkeypatch.undo()
    importlib.reload(app.database.session)


def test_session_module_listen_exception(monkeypatch):
    import importlib
    import sqlalchemy.event
    orig_listen = sqlalchemy.event.listen

    def fake_listen(target, identifier, fn, *args, **kwargs):
        if getattr(fn, "__name__", "") == "on_async_connect":
            raise RuntimeError("Listen error")
        return orig_listen(target, identifier, fn, *args, **kwargs)

    monkeypatch.setattr(sqlalchemy.event, "listen", fake_listen)
    import app.database.session
    importlib.reload(app.database.session)
    monkeypatch.undo()
    importlib.reload(app.database.session)


