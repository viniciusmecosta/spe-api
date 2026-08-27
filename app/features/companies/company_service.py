import os
import shutil
from typing import Annotated
import uuid

from fastapi import Depends, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.features.companies.company_exceptions import (
    CompanyAlreadyExistsError,
    CompanyNotFoundError,
    InvalidLogoFormatError,
    LogoSaveError,
)
from app.features.companies.company_models import Company
from app.features.companies.company_repository import company_repository
from app.features.companies.company_schemas import (
    CompanyCreate,
    CompanyResponse,
    CompanyUpdate,
)
from app.features.system.audit_service import audit_service, serialize_model
from app.shared import deps


class CompanyService:
    def __init__(self, db: Annotated[Session, Depends(deps.get_db)] = None):
        self.db = db

    def get_company(self, db: Session | None = None) -> Company | None:
        session = db if db is not None else self.db
        assert session is not None
        return company_repository.get_current(session)

    def enrich_logo_url(self, company: Company | None, base_url: str) -> CompanyResponse | None:
        if not company:
            return None
        response_obj = CompanyResponse.model_validate(company)
        if response_obj.logo_path:
            clean_base_url = base_url.rstrip("/")
            response_obj.logo_path = f"{clean_base_url}/uploads/{response_obj.logo_path}"
        return response_obj

    def create_company(self, db: Session | None = None, obj_in: CompanyCreate | None = None, current_user_id: int = 0) -> Company:
        session = db if db is not None else self.db
        assert session is not None
        assert obj_in is not None
        existing = company_repository.get_current(session)
        if existing:
            raise CompanyAlreadyExistsError()
        company = company_repository.create(session, obj_in=obj_in)
        audit_service.log_change(session, current_user_id, "CREATE", new_model=company)
        return company

    def update_company(self, db: Session | None = None, obj_in: CompanyUpdate | None = None, current_user_id: int = 0) -> Company:
        session = db if db is not None else self.db
        assert session is not None
        assert obj_in is not None
        existing = company_repository.get_current(session)
        if not existing:
            raise CompanyNotFoundError("Nenhuma empresa cadastrada para atualizar.")

        old_data = serialize_model(existing)
        company = company_repository.update(session, db_obj=existing, obj_in=obj_in)
        audit_service.log_change(session, current_user_id, "UPDATE", old_model=old_data, new_model=company)
        return company

    def upload_logo(self, db: Session | None = None, file: UploadFile | None = None, current_user_id: int = 0) -> Company:
        session = db if db is not None else self.db
        assert session is not None
        assert file is not None
        existing = company_repository.get_current(session)
        if not existing:
            raise CompanyNotFoundError("Nenhuma empresa cadastrada para associar o logotipo.")

        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext not in [".png", ".jpg", ".jpeg"]:
            raise InvalidLogoFormatError()

        filename = f"logo_{uuid.uuid4().hex}{ext}"
        full_file_path = os.path.join(settings.UPLOAD_DIR, filename)

        try:
            with open(full_file_path, "wb") as f:
                shutil.copyfileobj(file.file, f)
        except Exception as e:
            raise LogoSaveError(f"Erro ao salvar o arquivo: {e}")

        if existing.logo_path:
            old_full_path = os.path.join(settings.UPLOAD_DIR, existing.logo_path)
            if os.path.exists(old_full_path):
                try:
                    os.remove(old_full_path)
                except OSError:
                    pass

        old_logo = existing.logo_path
        existing.logo_path = filename
        session.add(existing)
        session.commit()
        session.refresh(existing)

        audit_service.log_change(
            session, current_user_id, "UPDATE_LOGO", entity="COMPANY", entity_id=existing.id,
            old_data={"logo_path": old_logo}, new_data={"logo_path": filename}
        )
        return existing


company_service = CompanyService()
