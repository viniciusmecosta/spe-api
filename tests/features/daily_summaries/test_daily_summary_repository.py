from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.features.daily_summaries.daily_summary_models import DailySummary
from app.features.daily_summaries.daily_summary_repository import DailySummaryRepository
from app.features.daily_summaries.daily_summary_schemas import DaySummaryValues


@pytest.mark.asyncio
async def test_get_by_date_supports_async_and_sync_sessions():
    repository = DailySummaryRepository()
    expected = DailySummary(user_id=3, apuration_date=date(2026, 10, 5))
    async_session = MagicMock(spec=AsyncSession)
    async_session.sync_session = MagicMock()
    async_session.scalar = AsyncMock(return_value=expected)
    sync_session = MagicMock(spec=Session)
    sync_session.scalar.return_value = expected

    assert await repository.get_by_date(async_session, 3, date(2026, 10, 5)) is expected
    assert await repository.get_by_date(sync_session, 3, date(2026, 10, 5)) is expected


@pytest.mark.asyncio
async def test_get_range_supports_async_and_sync_sessions():
    repository = DailySummaryRepository()
    expected = [DailySummary(user_id=3, apuration_date=date(2026, 10, 5))]
    async_result = MagicMock()
    async_result.all.return_value = expected
    async_session = MagicMock(spec=AsyncSession)
    async_session.sync_session = MagicMock()
    async_session.scalars = AsyncMock(return_value=async_result)
    sync_result = MagicMock()
    sync_result.all.return_value = expected
    sync_session = MagicMock(spec=Session)
    sync_session.scalars.return_value = sync_result

    assert await repository.get_range(async_session, 3, date(2026, 10, 1), date(2026, 10, 31)) == expected
    assert await repository.get_range(sync_session, 3, date(2026, 10, 1), date(2026, 10, 31)) == expected


@pytest.mark.asyncio
async def test_upsert_supports_async_and_sync_sessions():
    repository = DailySummaryRepository()
    values = DaySummaryValues(480, 450, 480, 30, 0, 0, 0)
    async_session = MagicMock(spec=AsyncSession)
    async_session.sync_session = MagicMock()
    async_session.execute = AsyncMock()
    sync_session = MagicMock(spec=Session)

    await repository.upsert(async_session, 3, date(2026, 10, 5), values)
    await repository.upsert(sync_session, 3, date(2026, 10, 5), values)

    async_session.execute.assert_awaited_once()
    sync_session.execute.assert_called_once()
