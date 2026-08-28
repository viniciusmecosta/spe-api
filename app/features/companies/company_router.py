from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, UploadFile

from app.features.companies.company_schemas import (
    CompanyCreate,
    CompanyResponse,
    CompanyUpdate,
)
from app.features.companies.company_service import CompanyService
from app.features.users.user_models import User
from app.shared import deps
from app.shared.openapi_responses import (
    BAD_REQUEST_RESPONSE,
    CRUD_RESPONSES,
    FORBIDDEN_RESPONSE,
    NOT_FOUND_RESPONSE,
    UNAUTHORIZED_RESPONSE,
)

router = APIRouter(responses={**UNAUTHORIZED_RESPONSE})


@router.get(
    "/",
    dependencies=[Depends(deps.get_current_active_user)],
)
async def get_company(
        request: Request,
        service: Annotated[CompanyService, Depends()],
) -> CompanyResponse | None:
    company = await service.get_company()
    return service.enrich_logo_url(company, str(request.base_url))


@router.post(
    "/",
    responses={**BAD_REQUEST_RESPONSE, **FORBIDDEN_RESPONSE},
)
async def create_company(
        obj_in: CompanyCreate,
        request: Request,
        service: Annotated[CompanyService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_maintainer)],
) -> CompanyResponse:
    company = await service.create_company(obj_in=obj_in, current_user_id=current_user.id)
    return service.enrich_logo_url(company, str(request.base_url))


@router.put(
    "/",
    responses={**FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def update_company(
        obj_in: CompanyUpdate,
        request: Request,
        service: Annotated[CompanyService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_maintainer)],
) -> CompanyResponse:
    company = await service.update_company(obj_in=obj_in, current_user_id=current_user.id)
    return service.enrich_logo_url(company, str(request.base_url))


@router.post(
    "/logo",
    responses={**BAD_REQUEST_RESPONSE, **CRUD_RESPONSES},
)
async def upload_company_logo(
        request: Request,
        service: Annotated[CompanyService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_maintainer)],
        file: Annotated[UploadFile, File(...)],
) -> CompanyResponse:
    company = await service.upload_logo(file=file, current_user_id=current_user.id)
    return service.enrich_logo_url(company, str(request.base_url))
