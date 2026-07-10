import os
import shutil
import uuid
from typing import Optional

from fastapi import HTTPException, status, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
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
            db, user_id=current_user_id, action="CREATE", entity="COMPANY", entity_id=company.id,
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
            "phone": existing.phone,
            "logo_path": existing.logo_path
        }

        company = company_repository.update(db, existing, obj_in)

        new_data_raw = {
            "name": company.name,
            "cnpj": company.cnpj,
            "address": company.address,
            "phone": company.phone,
            "logo_path": company.logo_path
        }

        actual_old, actual_new = audit_service.compute_diffs(old_data, new_data_raw)

        audit_service.log(
            db, user_id=current_user_id, action="UPDATE", entity="COMPANY", entity_id=company.id,
            old_data=actual_old, new_data=actual_new
        )
        return company

    def upload_logo(self, db: Session, file: UploadFile, current_user_id: int) -> Company:
        existing = company_repository.get_current(db)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Nenhuma empresa cadastrada para associar o logotipo."
            )

        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in [".png", ".jpg", ".jpeg"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Formato de arquivo inválido. Apenas PNG, JPG ou JPEG são aceitos."
            )

        filename = f"logo_{uuid.uuid4().hex}{ext}"
        full_file_path = os.path.join(settings.UPLOAD_DIR, filename)

        try:
            with open(full_file_path, "wb") as f:
                shutil.copyfileobj(file.file, f)
        except OSError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Falha ao salvar arquivo no servidor: {str(e)}"
            )

        if existing.logo_path:
            old_full_path = os.path.join(settings.UPLOAD_DIR, existing.logo_path)
            if os.path.exists(old_full_path):
                try:
                    os.remove(old_full_path)
                except OSError:
                    pass

        old_logo = existing.logo_path
        existing.logo_path = filename
        db.add(existing)
        db.commit()
        db.refresh(existing)

        audit_service.log(
            db, user_id=current_user_id, action="UPDATE_LOGO", entity="COMPANY", entity_id=existing.id,
            old_data={"logo_path": old_logo}, new_data={"logo_path": filename}
        )
        return existing


company_service = CompanyService()
