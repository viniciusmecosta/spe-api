from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.orm import Session

from app.api import deps
from app.api.openapi_responses import (
    BAD_REQUEST_RESPONSE,
    CRUD_RESPONSES,
    FORBIDDEN_RESPONSE,
    NOT_FOUND_RESPONSE,
    UNAUTHORIZED_RESPONSE,
)
from app.domain.models.user import User
from app.schemas.company import CompanyCreate, CompanyResponse, CompanyUpdate
from app.services.company_service import company_service

router = APIRouter(responses={**UNAUTHORIZED_RESPONSE})


@router.get(
    "/",
    dependencies=[Depends(deps.get_current_active_user)],
)
def get_company(
    request: Request,
    db: Annotated[Session, Depends(deps.get_db)],
) -> CompanyResponse | None:
    company = company_service.get_company(db)
    return company_service.enrich_logo_url(company, str(request.base_url))


@router.post(
    "/",
    responses={**BAD_REQUEST_RESPONSE, **FORBIDDEN_RESPONSE},
)
def create_company(
    obj_in: CompanyCreate,
    request: Request,
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_maintainer)],
) -> CompanyResponse:
    company = company_service.create_company(db, obj_in, current_user.id)
    return company_service.enrich_logo_url(company, str(request.base_url))


@router.put(
    "/",
    responses={**FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
def update_company(
    obj_in: CompanyUpdate,
    request: Request,
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_maintainer)],
) -> CompanyResponse:
    company = company_service.update_company(db, obj_in, current_user.id)
    return company_service.enrich_logo_url(company, str(request.base_url))


@router.post(
    "/logo",
    responses={**BAD_REQUEST_RESPONSE, **CRUD_RESPONSES},
)
def upload_company_logo(
    request: Request,
    file: Annotated[UploadFile, File(...)],
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_maintainer)],
) -> CompanyResponse:
    company = company_service.upload_logo(db, file, current_user.id)
    return company_service.enrich_logo_url(company, str(request.base_url))
