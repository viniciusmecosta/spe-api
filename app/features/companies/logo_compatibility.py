from pathlib import Path

from fastapi import Depends, HTTPException
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared import deps
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.core.config import settings
from app.features.companies.company_models import Company
from app.features.system.notification_context import logo_file


class CompanyLogoService:
    def __init__(self, db: Annotated[AsyncSession, Depends(deps.get_async_db)]):
        self.db = db

    async def get_public_upload(self, filename: str):
        if Path(filename).name != filename:
            raise HTTPException(status_code=404)
        if Path(filename).suffix.lower() in ('.png', '.jpg', '.jpeg'):
            company = await self.db.scalar(select(Company).where(Company.logo_path == filename).limit(1))
            if company:
                legacy = logo_file(filename)
                if legacy:
                    return FileResponse(legacy)
        raise HTTPException(status_code=404)


async def public_upload(filename: str, service: Annotated[CompanyLogoService, Depends()]):
    return await service.get_public_upload(filename)
