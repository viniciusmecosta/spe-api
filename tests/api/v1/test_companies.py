import io
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.domain.models.company import Company
from app.domain.models.enums import UserRole
from app.domain.models.user import User
from app.main import app


@pytest.fixture
def mock_maintainer_user() -> User:
    user = MagicMock(spec=User)
    user.id = 1
    user.role = UserRole.MAINTAINER
    user.is_active = True
    return user


@pytest.fixture
def client(mock_maintainer_user: User, db_session_mock: MagicMock) -> TestClient:
    app.dependency_overrides[deps.get_current_maintainer] = lambda: mock_maintainer_user
    app.dependency_overrides[deps.get_current_active_user] = lambda: mock_maintainer_user
    app.dependency_overrides[deps.get_db] = lambda: db_session_mock
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_get_company_found(client: TestClient, mocker: MagicMock) -> None:
    mock_company = Company(
        id=1,
        name="Empresa Teste",
        cnpj="11222333000181",
        address="Rua 1",
        phone="1199999999",
        logo_path="logo.png",
    )
    mocker.patch("app.api.v1.companies.company_service.get_company", return_value=mock_company)

    response = client.get("/api/v1/companies/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Empresa Teste"
    assert "/uploads/logo.png" in data["logo_path"]


def test_get_company_not_found(client: TestClient, mocker: MagicMock) -> None:
    mocker.patch("app.api.v1.companies.company_service.get_company", return_value=None)

    response = client.get("/api/v1/companies/")
    assert response.status_code == 200
    assert response.json() is None


def test_create_company(client: TestClient, mocker: MagicMock) -> None:
    mock_company = Company(
        id=1,
        name="Nova Empresa",
        cnpj="11222333000181",
        address="Rua 1",
        phone="1199999999",
    )
    mocker.patch("app.api.v1.companies.company_service.create_company", return_value=mock_company)

    response = client.post(
        "/api/v1/companies/",
        json={"name": "Nova Empresa", "cnpj": "11222333000181", "address": "Rua 1", "phone": "1199999999"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Nova Empresa"


def test_update_company(client: TestClient, mocker: MagicMock) -> None:
    mock_company = Company(
        id=1,
        name="Empresa Atualizada",
        cnpj="11222333000181",
        address="Rua 1",
        phone="1199999999",
    )
    mocker.patch("app.api.v1.companies.company_service.update_company", return_value=mock_company)

    response = client.put(
        "/api/v1/companies/",
        json={"name": "Empresa Atualizada"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Empresa Atualizada"


def test_upload_company_logo(client: TestClient, mocker: MagicMock) -> None:
    mock_company = Company(
        id=1,
        name="Empresa Teste",
        cnpj="11222333000181",
        address="Rua 1",
        phone="1199999999",
        logo_path="logo_123.png",
    )
    mocker.patch("app.api.v1.companies.company_service.upload_logo", return_value=mock_company)

    test_file = io.BytesIO(b"image data")
    response = client.post(
        "/api/v1/companies/logo",
        files={"file": ("logo.png", test_file, "image/png")},
    )
    assert response.status_code == 200
    assert "/uploads/logo_123.png" in response.json()["logo_path"]
