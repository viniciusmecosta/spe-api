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


class AsyncCompanyRepository(AsyncBaseRepository[Company, CompanyCreate, CompanyUpdate]):
    def __init__(self):
        super().__init__(Company)

    async def get_current(self, db: AsyncSession) -> Company | None:
        stmt = select(Company)
        result = await db.scalars(stmt)
        return result.first()


company_repository = CompanyRepository()
async_company_repository = AsyncCompanyRepository()
