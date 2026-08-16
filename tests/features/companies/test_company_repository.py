from app.features.companies.company_repository import company_repository, CompanyRepository
from app.features.companies.company_schemas import CompanyCreate, CompanyUpdate


def test_company_repository(db_session):
    repo = CompanyRepository()
    curr = repo.get_current(db_session)

    created = repo.create(db_session, CompanyCreate(name="Repo Test Co", cnpj="44555666000181", address="Street 1", phone="1234"))
    assert created.id is not None

    by_id = repo.get(db_session, created.id)
    assert by_id is not None

    updated = repo.update(db_session, created, CompanyUpdate(name="Repo Test Co Updated"))
    assert updated.name == "Repo Test Co Updated"
