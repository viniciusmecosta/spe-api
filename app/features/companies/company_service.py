import os
import uuid
from pathlib import Path
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
from app.features.companies.company_repository import (
    AsyncCompanyRepository,
    async_company_repository,
)
from app.features.companies.company_schemas import (
    CompanyCreate,
    CompanyResponse,
    CompanyUpdate,
)
from app.features.system.audit_service import audit_service, serialize_model
from app.shared.storage import resolve_stored_file
from app.shared.upload_storage import UploadCategory, upload_storage


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

    async def get_company(self, db: AsyncSession | None = None,
                          base_url: str | None = None) -> Company | CompanyResponse | None:
        session = db if db is not None else self.db
        assert session is not None
        company = await self.repo.get_current(session)
        if base_url and company:
            return self.enrich_logo_url(company, base_url)
        return company

    def enrich_logo_url(self, company: Company | None, base_url: str) -> CompanyResponse | None:
        if not company:
            return None
        response_obj = CompanyResponse.model_validate(company)
        if response_obj.logo_path:
            clean_base_url = base_url.rstrip("/")
            response_obj.logo_path = f"{clean_base_url}/uploads/{response_obj.logo_path}"
        return response_obj

    async def create_company(self, db: AsyncSession | None = None, obj_in: CompanyCreate | None = None,
                             current_user_id: int = 0, base_url: str | None = None) -> Company | CompanyResponse:
        session = db if db is not None else self.db
        assert session is not None
        assert obj_in is not None
        existing = await self.repo.get_current(session)
        if existing:
            raise CompanyAlreadyExistsError()
        company = await self.repo.create(session, obj_in=obj_in)
        await audit_service.async_log_change(session, current_user_id, "CREATE", new_model=company)
        if base_url:
            return self.enrich_logo_url(company, base_url)
        return company

    async def update_company(self, db: AsyncSession | None = None, obj_in: CompanyUpdate | None = None,
                             current_user_id: int = 0, base_url: str | None = None) -> Company | CompanyResponse:
        session = db if db is not None else self.db
        assert session is not None
        assert obj_in is not None
        existing = await self.repo.get_current(session)
        if not existing:
            raise CompanyNotFoundError("Nenhuma empresa cadastrada para atualizar.")

        old_data = serialize_model(existing)
        company = await self.repo.update(session, db_obj=existing, obj_in=obj_in)
        await audit_service.async_log_change(session, current_user_id, "UPDATE", old_model=old_data, new_model=company)
        if base_url:
            return self.enrich_logo_url(company, base_url)
        return company

    def _validate_logo_extension(self, filename: str | None) -> str:
        ext = os.path.splitext(filename or "")[1].lower()
        if ext not in [".png", ".jpg", ".jpeg"]:
            raise InvalidLogoFormatError()
        return ext

    async def _cleanup_old_logo(self, old_logo_path: str | None) -> None:
        if not old_logo_path:
            return
        old_file = resolve_stored_file(old_logo_path, 'public')
        if old_file is None:
            raw = Path(old_logo_path.replace('\\', '/'))
            if raw.name != str(raw) or raw.suffix.lower() not in {'.png', '.jpg', '.jpeg'}:
                return
            old_file = resolve_stored_file(old_logo_path)
            if old_file is not None and old_file.parent != Path(settings.UPLOAD_DIR).resolve():
                return
        if old_file is not None:
            await upload_storage.remove_path(old_file)

    async def upload_logo(self, db: AsyncSession | None = None, file: UploadFile | None = None,
                          current_user_id: int = 0, base_url: str | None = None) -> Company | CompanyResponse:
        session = db if db is not None else self.db
        assert session is not None
        assert file is not None
        existing = await self.repo.get_current(session)
        if not existing:
            raise CompanyNotFoundError("Nenhuma empresa cadastrada para associar o logotipo.")

        ext = self._validate_logo_extension(file.filename)
        filename = f"logo_{uuid.uuid4().hex}{ext}"

        try:
            stored = await upload_storage.save(file, UploadCategory.LOGO, filename)
        except OSError as exc:
            raise LogoSaveError("Não foi possível salvar o logotipo.") from exc
        old_logo = existing.logo_path
        existing.logo_path = filename
        session.add(existing)
        try:
            await session.commit()
        except BaseException:
            await session.rollback()
            await upload_storage.remove(stored)
            raise
        await session.refresh(existing)
        await self._cleanup_old_logo(old_logo)

        await audit_service.async_log_change(
            session, current_user_id, "UPDATE_LOGO", entity="COMPANY", entity_id=existing.id,
            old_data={"logo_path": old_logo}, new_data={"logo_path": filename}
        )
        if base_url:
            return self.enrich_logo_url(existing, base_url)
        return existing


company_service = CompanyService()
