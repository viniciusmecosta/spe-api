from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.features.printers.printer_schemas import (
    PrinterCreate,
    PrinterResponse,
    PrinterUpdate,
)
from app.features.printers.printer_service import printer_service
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
    responses={**FORBIDDEN_RESPONSE},
)
async def read_printers(
        db: Annotated[Session, Depends(deps.get_db)],
        current_user: Annotated[User, Depends(deps.get_current_manager)],
        skip: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> list[PrinterResponse]:
    return printer_service.get_all(db, skip=skip, limit=limit)


@router.get(
    "/{printer_id}",
    responses={**NOT_FOUND_RESPONSE, **FORBIDDEN_RESPONSE},
)
async def read_printer(
        printer_id: int,
        db: Annotated[Session, Depends(deps.get_db)],
        current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> PrinterResponse:
    return printer_service.get_by_id(db, printer_id=printer_id)


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    responses={**BAD_REQUEST_RESPONSE, **FORBIDDEN_RESPONSE},
)
async def create_printer(
        printer_in: PrinterCreate,
        db: Annotated[Session, Depends(deps.get_db)],
        current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> PrinterResponse:
    return printer_service.create(db, obj_in=printer_in, current_user_id=current_user.id)


@router.patch(
    "/{printer_id}",
    responses={**BAD_REQUEST_RESPONSE, **CRUD_RESPONSES},
)
async def update_printer(
        printer_id: int,
        printer_in: PrinterUpdate,
        db: Annotated[Session, Depends(deps.get_db)],
        current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> PrinterResponse:
    return printer_service.update(db, printer_id=printer_id, obj_in=printer_in, current_user_id=current_user.id)


@router.delete(
    "/{printer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**CRUD_RESPONSES},
)
async def delete_printer(
        printer_id: int,
        db: Annotated[Session, Depends(deps.get_db)],
        current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> None:
    printer_service.delete(db, printer_id=printer_id, current_user_id=current_user.id)
