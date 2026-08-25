from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.repository import BaseRepository
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

    def create(self, db: Session, obj_in: CompanyCreate) -> Company:
        return super().create(db, obj_in=obj_in)

    def update(self, db: Session, db_obj: Company, obj_in: CompanyUpdate) -> Company:
        return super().update(db, db_obj=db_obj, obj_in=obj_in)


company_repository = CompanyRepository()
