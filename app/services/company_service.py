from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional

from app.domain.models.company import Company
from app.repositories.company_repository import company_repository
from app.schemas.company import CompanyCreate, CompanyUpdate
from app.services.audit_service import audit_service


class CompanyService:
    def get_company(self, db: Session) -> Optional[Company]:
        return company_repository.get_current(db)

    def create_company(self, db: Session, obj_in: CompanyCreate, current_user_id: int) -> Company:
        existing = company_repository.get_current(db)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Empresa já cadastrada. Utilize a atualização."
            )
        company = company_repository.create(db, obj_in)
        audit_service.log(
            db, actor_id=current_user_id, action="CREATE", entity="COMPANY", entity_id=company.id,
            new_data=obj_in.model_dump()
        )
        return company

    def update_company(self, db: Session, obj_in: CompanyUpdate, current_user_id: int) -> Company:
        existing = company_repository.get_current(db)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Nenhuma empresa cadastrada para atualizar."
            )

        old_data = {
            "name": existing.name,
            "cnpj": existing.cnpj,
            "address": existing.address,
            "phone": existing.phone
        }

        company = company_repository.update(db, existing, obj_in)

        new_data = {
            "name": company.name,
            "cnpj": company.cnpj,
            "address": company.address,
            "phone": company.phone
        }

        audit_service.log(
            db, actor_id=current_user_id, action="UPDATE", entity="COMPANY", entity_id=company.id,
            old_data=old_data, new_data=new_data
        )
        return company


company_service = CompanyService()