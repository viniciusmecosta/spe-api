from unittest.mock import MagicMock

import pytest
from app.features.companies.company_models import Company
from app.features.companies.company_repository import AsyncCompanyRepository, CompanyRepository
from app.features.companies.company_schemas import CompanyCreate, CompanyUpdate


def test_company_repository(db_session):
    repo = CompanyRepository()
    curr = repo.get_current(db_session)

    created = repo.create(
        db_session,
        obj_in=CompanyCreate(name="Repo Test Co", cnpj="44555666000181", address="Street 1", phone="1234")
    )
    assert created.id is not None

    by_id = repo.get(db_session, created.id)
    assert by_id is not None

    updated = repo.update(db_session, db_obj=created, obj_in=CompanyUpdate(name="Repo Test Co Updated"))
    assert updated.name == "Repo Test Co Updated"


@pytest.mark.asyncio
async def test_async_company_repository(async_db_mock):
    repo = AsyncCompanyRepository()
    mock_company = Company(id=1, name="Async Co")
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = mock_company
    async_db_mock.scalars.return_value = mock_scalars

    curr = await repo.get_current(async_db_mock)
    assert curr == mock_company

    async_db_mock.get.return_value = mock_company
    by_id = await repo.get(async_db_mock, 1)
    assert by_id == mock_company

    created = await repo.create(
        async_db_mock,
        obj_in=CompanyCreate(name="Repo Test Co", cnpj="44555666000181", address="Street 1", phone="1234")
    )
    assert created.name == "Repo Test Co"

    updated = await repo.update(async_db_mock, db_obj=created, obj_in=CompanyUpdate(name="Repo Test Co Updated"))
    assert updated.name == "Repo Test Co Updated"
