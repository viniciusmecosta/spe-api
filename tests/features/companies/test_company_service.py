import io

from PIL import Image
from unittest.mock import AsyncMock, MagicMock

from fastapi import UploadFile

import pytest
from app.features.companies.company_exceptions import (
    CompanyAlreadyExistsError,
    CompanyNotFoundError,
    InvalidLogoFormatError,
    LogoSaveError,
)
from app.features.companies.company_models import Company
from app.features.companies.company_schemas import CompanyCreate, CompanyUpdate
from app.features.companies.company_service import company_service


@pytest.mark.asyncio
async def test_get_company_none(mocker, async_db_mock):
    mocker.patch("app.features.companies.company_repository.async_company_repository.get_current",
                 new_callable=AsyncMock, return_value=None)
    result = await company_service.get_company(async_db_mock)
    assert result is None


@pytest.mark.asyncio
async def test_get_company_existing(mocker, async_db_mock):
    mock_company = Company(id=1, name="Test")
    mocker.patch("app.features.companies.company_repository.async_company_repository.get_current",
                 new_callable=AsyncMock, return_value=mock_company)
    result = await company_service.get_company(async_db_mock)
    assert result == mock_company


@pytest.mark.asyncio
async def test_create_company_already_exists(mocker, async_db_mock):
    mock_company = Company(id=1, name="Test")
    mocker.patch("app.features.companies.company_repository.async_company_repository.get_current",
                 new_callable=AsyncMock, return_value=mock_company)
    obj_in = CompanyCreate(name="Test 2", cnpj="11222333000181", address="Addr", phone="123")

    with pytest.raises(CompanyAlreadyExistsError) as exc_info:
        await company_service.create_company(async_db_mock, obj_in, 1)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Empresa já cadastrada. Utilize a atualização."


@pytest.mark.asyncio
async def test_create_company_success(mocker, async_db_mock):
    mocker.patch("app.features.companies.company_repository.async_company_repository.get_current",
                 new_callable=AsyncMock, return_value=None)
    obj_in = CompanyCreate(name="New", cnpj="44555666000181", address="Addr2", phone="321")
    created_company = Company(id=2, name="New", cnpj="44555666000181", address="Addr2", phone="321")
    mocker.patch("app.features.companies.company_repository.async_company_repository.create", new_callable=AsyncMock,
                 return_value=created_company)
    mock_audit = mocker.patch("app.features.system.audit_service.audit_service.async_log_change",
                              new_callable=AsyncMock)

    result = await company_service.create_company(async_db_mock, obj_in, 99)
    assert result == created_company
    mock_audit.assert_called_once_with(
        async_db_mock, 99, "CREATE", new_model=created_company
    )


@pytest.mark.asyncio
async def test_update_company_not_found(mocker, async_db_mock):
    mocker.patch("app.features.companies.company_repository.async_company_repository.get_current",
                 new_callable=AsyncMock, return_value=None)
    obj_in = CompanyUpdate(name="Up")

    with pytest.raises(CompanyNotFoundError) as exc_info:
        await company_service.update_company(async_db_mock, obj_in, 1)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Nenhuma empresa cadastrada para atualizar."


@pytest.mark.asyncio
async def test_update_company_success(mocker, async_db_mock):
    existing = Company(id=1, name="Old", cnpj="11222333000181", address="A1", phone="P1", logo_path="L1")
    mocker.patch("app.features.companies.company_repository.async_company_repository.get_current",
                 new_callable=AsyncMock, return_value=existing)

    updated = Company(id=1, name="New", cnpj="11222333000181", address="A1", phone="P1", logo_path="L1")
    mocker.patch("app.features.companies.company_repository.async_company_repository.update", new_callable=AsyncMock,
                 return_value=updated)
    mock_audit = mocker.patch("app.features.system.audit_service.audit_service.async_log_change",
                              new_callable=AsyncMock)

    obj_in = CompanyUpdate(name="New")
    result = await company_service.update_company(async_db_mock, obj_in, 100)

    from unittest import mock
    assert result == updated
    mock_audit.assert_called_once_with(
        async_db_mock, 100, "UPDATE", old_model=mock.ANY, new_model=updated
    )


@pytest.mark.asyncio
async def test_upload_logo_not_found(mocker, async_db_mock):
    mocker.patch("app.features.companies.company_repository.async_company_repository.get_current",
                 new_callable=AsyncMock, return_value=None)
    file_mock = MagicMock(spec=UploadFile)

    with pytest.raises(CompanyNotFoundError) as exc_info:
        await company_service.upload_logo(async_db_mock, file_mock, 1)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Nenhuma empresa cadastrada para associar o logotipo."


@pytest.mark.asyncio
async def test_upload_logo_invalid_ext(mocker, async_db_mock):
    existing = Company(id=1)
    mocker.patch("app.features.companies.company_repository.async_company_repository.get_current",
                 new_callable=AsyncMock, return_value=existing)
    file_mock = MagicMock(spec=UploadFile)
    file_mock.filename = "image.gif"

    with pytest.raises(InvalidLogoFormatError) as exc_info:
        await company_service.upload_logo(async_db_mock, file_mock, 1)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Formato de arquivo inválido. Apenas PNG, JPG ou JPEG são aceitos."


def logo_file(name="logo.png"):
    content = io.BytesIO()
    Image.new("RGB", (4, 4), "blue").save(content, format="JPEG" if name.endswith((".jpg", ".jpeg")) else "PNG")
    content.seek(0)
    return UploadFile(filename=name, file=content)


@pytest.mark.asyncio
async def test_upload_logo_success_no_old_logo(mocker, async_db_mock, tmp_path):
    mocker.patch("app.core.config.settings.UPLOAD_DIR", str(tmp_path))
    existing = Company(id=1, logo_path=None)
    mocker.patch.object(company_service.repo, "get_current", return_value=existing)
    mock_audit = mocker.patch("app.features.system.audit_service.audit_service.async_log_change",
                              new_callable=AsyncMock)
    result = await company_service.upload_logo(async_db_mock, logo_file(), 50)
    assert (tmp_path / "public" / result.logo_path).is_file()
    async_db_mock.commit.assert_awaited_once()
    async_db_mock.refresh.assert_awaited_once_with(existing)
    mock_audit.assert_awaited_once()


@pytest.mark.asyncio
async def test_upload_logo_exception_on_save(mocker, async_db_mock):
    existing = Company(id=1)
    mocker.patch.object(company_service.repo, "get_current", return_value=existing)
    mocker.patch("app.features.companies.company_service.upload_storage.save", side_effect=OSError("disk failure"))
    file = logo_file()
    with pytest.raises(LogoSaveError):
        await company_service.upload_logo(async_db_mock, file, 1)
    async_db_mock.commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [False, True])
async def test_old_logo_removed_only_after_successful_commit(mocker, async_db_mock, tmp_path, legacy):
    mocker.patch("app.core.config.settings.UPLOAD_DIR", str(tmp_path))
    directory = tmp_path if legacy else tmp_path / "public"
    directory.mkdir(exist_ok=True)
    old = directory / "old.jpg"
    old.write_bytes(b"old logo")
    existing = Company(id=1, logo_path="old.jpg")
    mocker.patch.object(company_service.repo, "get_current", return_value=existing)
    mocker.patch("app.features.system.audit_service.audit_service.async_log_change", new_callable=AsyncMock)

    async def commit():
        assert old.exists()
        assert (tmp_path / "public" / existing.logo_path).exists()
    async_db_mock.commit.side_effect = commit
    result = await company_service.upload_logo(async_db_mock, logo_file(), 10)
    assert not old.exists()
    assert (tmp_path / "public" / result.logo_path).exists()


@pytest.mark.asyncio
async def test_commit_failure_keeps_old_logo_and_removes_new_file(mocker, async_db_mock, tmp_path):
    mocker.patch("app.core.config.settings.UPLOAD_DIR", str(tmp_path))
    directory = tmp_path / "public"
    directory.mkdir()
    old = directory / "old.jpg"
    old.write_bytes(b"preserve")
    existing = Company(id=1, logo_path="old.jpg")
    mocker.patch.object(company_service.repo, "get_current", return_value=existing)
    async_db_mock.commit.side_effect = RuntimeError("commit failure")
    async_db_mock.rollback = AsyncMock()
    file = logo_file()
    with pytest.raises(RuntimeError, match="commit failure"):
        await company_service.upload_logo(async_db_mock, file, 10)
    assert old.read_bytes() == b"preserve"
    assert list(directory.iterdir()) == [old]
    async_db_mock.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_logo_content_validation_rejects_text(mocker, async_db_mock, tmp_path):
    from app.core.exceptions import DomainException
    mocker.patch("app.core.config.settings.UPLOAD_DIR", str(tmp_path))
    mocker.patch.object(company_service.repo, "get_current", return_value=Company(id=1))
    file = UploadFile(filename="logo.png", file=io.BytesIO(b"text"))
    with pytest.raises(DomainException, match="imagem"):
        await company_service.upload_logo(async_db_mock, file, 1)
    async_db_mock.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_logo_cleanup_does_not_remove_private_report(mocker, tmp_path):
    mocker.patch("app.core.config.settings.UPLOAD_DIR", str(tmp_path))
    directory = tmp_path / "reports"
    directory.mkdir()
    report = directory / "report.jpg"
    report.write_bytes(b"preserve")
    await company_service._cleanup_old_logo("reports/report.jpg")
    assert report.exists()


def test_company_service_repo_property(monkeypatch):
    custom_repo = MagicMock()
    monkeypatch.setattr(company_service, "repo", custom_repo)
    assert company_service.repo == custom_repo


@pytest.mark.asyncio
async def test_company_service_with_base_url(mocker, async_db_mock, tmp_path):
    mocker.patch("app.core.config.settings.UPLOAD_DIR", str(tmp_path))
    existing = Company(id=1, name="Company", cnpj="11222333000181", address="Rua Teste, 123", logo_path="logo.png")
    mocker.patch.object(company_service.repo, "get_current", new_callable=AsyncMock,
                        side_effect=[existing, None, existing, existing])
    mocker.patch.object(company_service.repo, "create", new_callable=AsyncMock, return_value=existing)
    mocker.patch.object(company_service.repo, "update", new_callable=AsyncMock, return_value=existing)
    mocker.patch("app.features.system.audit_service.audit_service.async_log_change", new_callable=AsyncMock)

    res_get = await company_service.get_company(async_db_mock, base_url="https://api.test.com")
    assert res_get.logo_path == "https://api.test.com/uploads/logo.png"

    create_in = CompanyCreate(name="New", cnpj="11222333000181", address="Rua Teste, 123")
    res_create = await company_service.create_company(async_db_mock, obj_in=create_in, current_user_id=1,
                                                      base_url="https://api.test.com")
    assert res_create.logo_path == "https://api.test.com/uploads/logo.png"

    update_in = CompanyUpdate(name="Updated")
    res_update = await company_service.update_company(async_db_mock, obj_in=update_in, current_user_id=1,
                                                      base_url="https://api.test.com")
    assert res_update.logo_path == "https://api.test.com/uploads/logo.png"

    res_upload = await company_service.upload_logo(async_db_mock, logo_file(), 10, base_url="https://api.test.com")
    assert "https://api.test.com/uploads/" in res_upload.logo_path
