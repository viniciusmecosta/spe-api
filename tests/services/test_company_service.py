import os
import uuid
import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException, UploadFile
from app.domain.models.company import Company
from app.schemas.company import CompanyCreate, CompanyUpdate
from app.services.company_service import company_service
from app.core.config import settings

def test_get_company_none(mocker, db_session_mock):
    mocker.patch("app.repositories.company_repository.company_repository.get_current", return_value=None)
    result = company_service.get_company(db_session_mock)
    assert result is None

def test_get_company_existing(mocker, db_session_mock):
    mock_company = Company(id=1, name="Test")
    mocker.patch("app.repositories.company_repository.company_repository.get_current", return_value=mock_company)
    result = company_service.get_company(db_session_mock)
    assert result == mock_company

def test_create_company_already_exists(mocker, db_session_mock):
    mock_company = Company(id=1, name="Test")
    mocker.patch("app.repositories.company_repository.company_repository.get_current", return_value=mock_company)
    obj_in = CompanyCreate(name="Test 2", cnpj="11222333000181", address="Addr", phone="123")
    
    with pytest.raises(HTTPException) as exc_info:
        company_service.create_company(db_session_mock, obj_in, 1)
    
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Empresa já cadastrada. Utilize a atualização."

def test_create_company_success(mocker, db_session_mock):
    mocker.patch("app.repositories.company_repository.company_repository.get_current", return_value=None)
    obj_in = CompanyCreate(name="New", cnpj="44555666000181", address="Addr2", phone="321")
    created_company = Company(id=2, name="New", cnpj="44555666000181", address="Addr2", phone="321")
    mocker.patch("app.repositories.company_repository.company_repository.create", return_value=created_company)
    mock_audit = mocker.patch("app.services.audit_service.audit_service.log")
    
    result = company_service.create_company(db_session_mock, obj_in, 99)
    assert result == created_company
    mock_audit.assert_called_once_with(
        db_session_mock, user_id=99, action="CREATE", entity="COMPANY", entity_id=2,
        new_data=obj_in.model_dump()
    )

def test_update_company_not_found(mocker, db_session_mock):
    mocker.patch("app.repositories.company_repository.company_repository.get_current", return_value=None)
    obj_in = CompanyUpdate(name="Up")
    
    with pytest.raises(HTTPException) as exc_info:
        company_service.update_company(db_session_mock, obj_in, 1)
        
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Nenhuma empresa cadastrada para atualizar."

def test_update_company_success(mocker, db_session_mock):
    existing = Company(id=1, name="Old", cnpj="11222333000181", address="A1", phone="P1", logo_path="L1")
    mocker.patch("app.repositories.company_repository.company_repository.get_current", return_value=existing)
    
    updated = Company(id=1, name="New", cnpj="11222333000181", address="A1", phone="P1", logo_path="L1")
    mocker.patch("app.repositories.company_repository.company_repository.update", return_value=updated)
    
    mocker.patch("app.services.audit_service.audit_service.compute_diffs", return_value=({"name": "Old"}, {"name": "New"}))
    mock_audit = mocker.patch("app.services.audit_service.audit_service.log")
    
    obj_in = CompanyUpdate(name="New")
    result = company_service.update_company(db_session_mock, obj_in, 100)
    
    assert result == updated
    mock_audit.assert_called_once_with(
        db_session_mock, user_id=100, action="UPDATE", entity="COMPANY", entity_id=1,
        old_data={"name": "Old"}, new_data={"name": "New"}
    )

def test_upload_logo_not_found(mocker, db_session_mock):
    mocker.patch("app.repositories.company_repository.company_repository.get_current", return_value=None)
    file_mock = MagicMock(spec=UploadFile)
    
    with pytest.raises(HTTPException) as exc_info:
        company_service.upload_logo(db_session_mock, file_mock, 1)
        
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Nenhuma empresa cadastrada para associar o logotipo."

def test_upload_logo_invalid_ext(mocker, db_session_mock):
    existing = Company(id=1)
    mocker.patch("app.repositories.company_repository.company_repository.get_current", return_value=existing)
    file_mock = MagicMock(spec=UploadFile)
    file_mock.filename = "image.gif"
    
    with pytest.raises(HTTPException) as exc_info:
        company_service.upload_logo(db_session_mock, file_mock, 1)
        
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Formato de arquivo inválido. Apenas PNG, JPG ou JPEG são aceitos."

def test_upload_logo_success_no_old_logo(mocker, db_session_mock):
    existing = Company(id=1, logo_path=None)
    mocker.patch("app.repositories.company_repository.company_repository.get_current", return_value=existing)
    
    file_mock = MagicMock(spec=UploadFile)
    file_mock.filename = "new_logo.png"
    file_mock.file = MagicMock()
    
    mocker.patch("uuid.uuid4", return_value=MagicMock(hex="123456"))
    mock_open = mocker.patch("builtins.open", mocker.mock_open())
    mock_copy = mocker.patch("shutil.copyfileobj")
    mock_audit = mocker.patch("app.services.audit_service.audit_service.log")
    
    result = company_service.upload_logo(db_session_mock, file_mock, 50)
    
    assert result.logo_path == "logo_123456.png"
    mock_open.assert_called_once()
    mock_copy.assert_called_once()
    db_session_mock.add.assert_called_once_with(existing)
    db_session_mock.commit.assert_called_once()
    db_session_mock.refresh.assert_called_once_with(existing)
    mock_audit.assert_called_once_with(
        db_session_mock, user_id=50, action="UPDATE_LOGO", entity="COMPANY", entity_id=1,
        old_data={"logo_path": None}, new_data={"logo_path": "logo_123456.png"}
    )

def test_upload_logo_exception_on_save(mocker, db_session_mock):
    existing = Company(id=1)
    mocker.patch("app.repositories.company_repository.company_repository.get_current", return_value=existing)
    file_mock = MagicMock(spec=UploadFile)
    file_mock.filename = "logo.jpg"
    
    mocker.patch("builtins.open", side_effect=Exception("Test Exception"))
    
    with pytest.raises(HTTPException) as exc_info:
        company_service.upload_logo(db_session_mock, file_mock, 1)
        
    assert exc_info.value.status_code == 400
    assert "Erro ao salvar o arquivo: Test Exception" in exc_info.value.detail

def test_upload_logo_success_old_logo_exists_and_removed(mocker, db_session_mock):
    existing = Company(id=1, logo_path="old.jpg")
    mocker.patch("app.repositories.company_repository.company_repository.get_current", return_value=existing)
    
    file_mock = MagicMock(spec=UploadFile)
    file_mock.filename = "new.jpeg"
    file_mock.file = MagicMock()
    
    mocker.patch("builtins.open", mocker.mock_open())
    mocker.patch("shutil.copyfileobj")
    mocker.patch("app.services.audit_service.audit_service.log")
    mocker.patch("uuid.uuid4", return_value=MagicMock(hex="654321"))
    
    mock_exists = mocker.patch("os.path.exists", return_value=True)
    mock_remove = mocker.patch("os.remove")
    
    result = company_service.upload_logo(db_session_mock, file_mock, 10)
    
    assert result.logo_path == "logo_654321.jpeg"
    mock_exists.assert_called_once()
    mock_remove.assert_called_once()

def test_upload_logo_success_old_logo_remove_oserror(mocker, db_session_mock):
    existing = Company(id=1, logo_path="old.jpg")
    mocker.patch("app.repositories.company_repository.company_repository.get_current", return_value=existing)
    
    file_mock = MagicMock(spec=UploadFile)
    file_mock.filename = "new.png"
    file_mock.file = MagicMock()
    
    mocker.patch("builtins.open", mocker.mock_open())
    mocker.patch("shutil.copyfileobj")
    mocker.patch("app.services.audit_service.audit_service.log")
    
    mocker.patch("os.path.exists", return_value=True)
    mock_remove = mocker.patch("os.remove", side_effect=OSError("Cannot remove"))
    
    result = company_service.upload_logo(db_session_mock, file_mock, 10)
    
    assert result.logo_path.endswith(".png")
    mock_remove.assert_called_once()
