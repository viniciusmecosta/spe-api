from typing import Optional

from sqlalchemy.orm import Session

from app.domain.models.company import Company
from app.schemas.company import CompanyCreate, CompanyUpdate


class CompanyRepository:
    def get_current(self, db: Session) -> Optional[Company]:
        return db.query(Company).first()

    def create(self, db: Session, obj_in: CompanyCreate) -> Company:
        db_obj = Company(
            name=obj_in.name,
            cnpj=obj_in.cnpj,
            address=obj_in.address,
            phone=obj_in.phone
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(self, db: Session, db_obj: Company, obj_in: CompanyUpdate) -> Company:
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj


company_repository = CompanyRepository()
