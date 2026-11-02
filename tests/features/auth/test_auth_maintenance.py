from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.features.auth.auth_maintenance import purge_expired_refresh_tokens


@pytest.mark.asyncio
@pytest.mark.parametrize('deleted', [0, 1000])
async def test_purge_expired_refresh_tokens_uses_transaction_and_utc(mocker, async_db_mock, deleted):
    @asynccontextmanager
    async def context():
        yield async_db_mock

    mocker.patch('app.features.auth.auth_maintenance.get_async_session_context', context)
    purge = mocker.patch('app.features.auth.auth_maintenance.auth_repository.purge_expired', new_callable=AsyncMock, return_value=deleted)
    before = datetime.now(UTC)
    assert await purge_expired_refresh_tokens() == deleted
    session, cutoff = purge.await_args.args
    assert session is async_db_mock
    assert before <= cutoff <= datetime.now(UTC)


@pytest.mark.asyncio
async def test_purge_failure_reaches_transaction_boundary(mocker, async_db_mock):
    rolled_back = False

    @asynccontextmanager
    async def context():
        nonlocal rolled_back
        try:
            yield async_db_mock
        except RuntimeError:
            rolled_back = True
            raise

    mocker.patch('app.features.auth.auth_maintenance.get_async_session_context', context)
    mocker.patch('app.features.auth.auth_maintenance.auth_repository.purge_expired', new_callable=AsyncMock, side_effect=RuntimeError('database unavailable'))
    with pytest.raises(RuntimeError, match='database unavailable'):
        await purge_expired_refresh_tokens()
    assert rolled_back
