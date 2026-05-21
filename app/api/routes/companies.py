from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session
from typing import Optional

from app.api import deps
from app.domain.models.user import User
from app.schemas.company import CompanyCreate, CompanyUpdate, CompanyResponse
from app.services.company_service import company_service

router = APIRouter()


@router.get("/", response_model=Optional[CompanyResponse])
def get_company(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    return company_service.get_company(db)


@router.post("/", response_model=CompanyResponse)
def create_company(
    obj_in: CompanyCreate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_maintainer)
):
    return company_service.create_company(db, obj_in, current_user.id)


@router.put("/", response_model=CompanyResponse)
def update_company(
    obj_in: CompanyUpdate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_maintainer)
):
    return company_service.update_company(db, obj_in, current_user.id)


@router.post("/logo", response_model=CompanyResponse)
def upload_company_logo(
        file: UploadFile = File(...),
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_maintainer)
):
    return company_service.upload_logo(db, file, current_user.id)
