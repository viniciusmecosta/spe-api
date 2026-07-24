from typing import Optional

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.orm import Session

from app.api import deps
from app.domain.models.user import User
from app.schemas.company import CompanyCreate, CompanyResponse, CompanyUpdate
from app.services.company_service import company_service

router = APIRouter()


def _enrich_logo_url(company, request: Request) -> CompanyResponse | None:
    if not company:
        return None
    response_obj = CompanyResponse.model_validate(company)
    if response_obj.logo_path:
        base_url = str(request.base_url).rstrip("/")
        response_obj.logo_path = f"{base_url}/uploads/{response_obj.logo_path}"
    return response_obj


@router.get("/", response_model=Optional[CompanyResponse])
def get_company(
        request: Request,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_active_user)
):
    company = company_service.get_company(db)
    return _enrich_logo_url(company, request)


@router.post("/", response_model=CompanyResponse)
def create_company(
        obj_in: CompanyCreate,
        request: Request,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_maintainer)
):
    company = company_service.create_company(db, obj_in, current_user.id)
    return _enrich_logo_url(company, request)


@router.put("/", response_model=CompanyResponse)
def update_company(
        obj_in: CompanyUpdate,
        request: Request,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_maintainer)
):
    company = company_service.update_company(db, obj_in, current_user.id)
    return _enrich_logo_url(company, request)


@router.post("/logo", response_model=CompanyResponse)
def upload_company_logo(
        request: Request,
        file: UploadFile = File(...),
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_maintainer)
):
    company = company_service.upload_logo(db, file, current_user.id)
    return _enrich_logo_url(company, request)
