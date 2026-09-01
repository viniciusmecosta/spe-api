import asyncio
import os
import shutil
import uuid
from typing import Annotated

from fastapi import Depends, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database.session import get_async_db
from app.features.companies.company_exceptions import (
    CompanyAlreadyExistsError,
    CompanyNotFoundError,
    InvalidLogoFormatError,
    LogoSaveError,
)
from app.features.companies.company_models import Company
from app.features.companies.company_repository import AsyncCompanyRepository, async_company_repository
from app.features.companies.company_schemas import (
    CompanyCreate,
    CompanyResponse,
    CompanyUpdate,
)
from app.features.system.audit_service import audit_service, serialize_model


class CompanyService:
    def __init__(
        self,
            db: Annotated[AsyncSession, Depends(get_async_db)] = None,
            repo: Annotated[AsyncCompanyRepository, Depends()] = None,
    ):
        self.db = db
        self._repo = repo

    @property
    def repo(self) -> AsyncCompanyRepository:
        return self._repo if self._repo is not None else async_company_repository

    @repo.setter
    def repo(self, value: AsyncCompanyRepository) -> None:
        self._repo = value

    async def get_company(self, db: AsyncSession | None = None) -> Company | None:
        session = db if db is not None else self.db
        assert session is not None
        return await self.repo.get_current(session)

    def enrich_logo_url(self, company: Company | None, base_url: str) -> CompanyResponse | None:
        if not company:
            return None
        response_obj = CompanyResponse.model_validate(company)
        if response_obj.logo_path:
            clean_base_url = base_url.rstrip("/")
            response_obj.logo_path = f"{clean_base_url}/uploads/{response_obj.logo_path}"
        return response_obj

    async def create_company(self, db: AsyncSession | None = None, obj_in: CompanyCreate | None = None,
                             current_user_id: int = 0) -> Company:
        session = db if db is not None else self.db
        assert session is not None
        assert obj_in is not None
        existing = await self.repo.get_current(session)
        if existing:
            raise CompanyAlreadyExistsError()
        company = await self.repo.create(session, obj_in=obj_in)
        await audit_service.async_log_change(session, current_user_id, "CREATE", new_model=company)
        return company

    async def update_company(self, db: AsyncSession | None = None, obj_in: CompanyUpdate | None = None,
                             current_user_id: int = 0) -> Company:
        session = db if db is not None else self.db
        assert session is not None
        assert obj_in is not None
        existing = await self.repo.get_current(session)
        if not existing:
            raise CompanyNotFoundError("Nenhuma empresa cadastrada para atualizar.")

        old_data = serialize_model(existing)
        company = await self.repo.update(session, db_obj=existing, obj_in=obj_in)
        await audit_service.async_log_change(session, current_user_id, "UPDATE", old_model=old_data, new_model=company)
        return company

    async def upload_logo(self, db: AsyncSession | None = None, file: UploadFile | None = None,
                          current_user_id: int = 0) -> Company:
        session = db if db is not None else self.db
        assert session is not None
        assert file is not None
        existing = await self.repo.get_current(session)
        if not existing:
            raise CompanyNotFoundError("Nenhuma empresa cadastrada para associar o logotipo.")

        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext not in [".png", ".jpg", ".jpeg"]:
            raise InvalidLogoFormatError()

        filename = f"logo_{uuid.uuid4().hex}{ext}"
        full_file_path = os.path.join(settings.UPLOAD_DIR, filename)

        def _save_file() -> None:
            with open(full_file_path, "wb") as f:
                shutil.copyfileobj(file.file, f)

        try:
            await asyncio.to_thread(_save_file)
        except Exception as e:
            raise LogoSaveError(f"Erro ao salvar o arquivo: {e}")

        if existing.logo_path:
            old_full_path = os.path.join(settings.UPLOAD_DIR, existing.logo_path)

            def _delete_old_file() -> None:
                if os.path.exists(old_full_path):
                    try:
                        os.remove(old_full_path)
                    except OSError:
                        pass

            await asyncio.to_thread(_delete_old_file)

        old_logo = existing.logo_path
        existing.logo_path = filename
        session.add(existing)
        await session.commit()
        await session.refresh(existing)

        await audit_service.async_log_change(
            session, current_user_id, "UPDATE_LOGO", entity="COMPANY", entity_id=existing.id,
            old_data={"logo_path": old_logo}, new_data={"logo_path": filename}
        )
        return existing


company_service = CompanyService()
