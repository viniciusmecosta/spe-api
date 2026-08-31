from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.database.repository import AsyncBaseRepository, BaseRepository
from app.features.companies.company_models import Company
from app.features.companies.company_schemas import CompanyCreate, CompanyUpdate


class CompanyRepository(BaseRepository[Company, CompanyCreate, CompanyUpdate]):
    def __init__(self):
        super().__init__(Company)

    def get_current(self, db: Session) -> Company | None:
        stmt = select(Company)
        return db.scalars(stmt).first()

    def get(self, db: Session, company_id: int) -> Company | None:
        return super().get(db, company_id)

    def create(self, db: Session, *, obj_in: CompanyCreate) -> Company:
        return super().create(db, obj_in=obj_in)

    def update(self, db: Session, *, db_obj: Company, obj_in: CompanyUpdate | dict[str, Any]) -> Company:
        return super().update(db, db_obj=db_obj, obj_in=obj_in)


class AsyncCompanyRepository(AsyncBaseRepository[Company, CompanyCreate, CompanyUpdate]):
    def __init__(self):
        super().__init__(Company)

    async def get_current(self, db: AsyncSession) -> Company | None:
        stmt = select(Company)
        result = await db.scalars(stmt)
        return result.first()

    async def get(self, db: AsyncSession, company_id: int) -> Company | None:
        return await super().get(db, company_id)

    async def create(self, db: AsyncSession, *, obj_in: CompanyCreate) -> Company:
        return await super().create(db, obj_in=obj_in)

    async def update(self, db: AsyncSession, *, db_obj: Company, obj_in: CompanyUpdate | dict[str, Any]) -> Company:
        return await super().update(db, db_obj=db_obj, obj_in=obj_in)


company_repository = CompanyRepository()
async_company_repository = AsyncCompanyRepository()
