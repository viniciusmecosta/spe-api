from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from app.database.unit_of_work import transactional, unit_of_work


class PreparedResponse(BaseModel):
    name: str
    model_config = ConfigDict(from_attributes=True)


@pytest.mark.asyncio
async def test_unit_of_work_supports_sync_sessions_without_premature_commits():
    session = MagicMock(info={})
    async with unit_of_work(session), unit_of_work(session):
        session.commit.assert_not_called()
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_transaction_prepares_a_response_before_commit_changes_the_source():
    source = SimpleNamespace(name="Resposta Sintetica")
    session = MagicMock(info={})
    session.commit = AsyncMock(side_effect=lambda: setattr(source, "name", None))
    session.rollback = AsyncMock()

    class Service:
        def __init__(self):
            self.db = session

        async def mutate(self):
            return source

    method = transactional(Service.mutate, response_model=PreparedResponse)
    response = await method(Service())
    assert response.name == "Resposta Sintetica"
    assert source.name is None
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_invalid_response_rolls_back_before_commit():
    session = MagicMock(info={})
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    class Service:
        def __init__(self):
            self.db = session

        async def mutate(self):
            return SimpleNamespace(name=None)

    method = transactional(Service.mutate, response_model=PreparedResponse)
    service = Service()
    with pytest.raises(ValidationError):
        await method(service)
    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()
