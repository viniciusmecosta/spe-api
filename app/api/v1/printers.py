from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
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
from app.schemas.printer import Printer, PrinterCreate, PrinterUpdate
from app.services.printer_service import printer_service

router = APIRouter(responses={**UNAUTHORIZED_RESPONSE})


@router.get(
    "/",
    responses={**FORBIDDEN_RESPONSE},
)
def read_printers(
        db: Annotated[Session, Depends(deps.get_db)],
        current_user: Annotated[User, Depends(deps.get_current_manager)],
        skip: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> list[Printer]:
    return printer_service.get_all(db, skip=skip, limit=limit)


@router.get(
    "/{printer_id}",
    responses={**NOT_FOUND_RESPONSE, **FORBIDDEN_RESPONSE},
)
def read_printer(
    printer_id: int,
        db: Annotated[Session, Depends(deps.get_db)],
        current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> Printer:
    return printer_service.get_by_id(db, printer_id=printer_id)


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    responses={**BAD_REQUEST_RESPONSE, **FORBIDDEN_RESPONSE},
)
def create_printer(
    printer_in: PrinterCreate,
        db: Annotated[Session, Depends(deps.get_db)],
        current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> Printer:
    return printer_service.create(db, obj_in=printer_in)


@router.patch(
    "/{printer_id}",
    responses={**BAD_REQUEST_RESPONSE, **CRUD_RESPONSES},
)
def update_printer(
    printer_id: int,
    printer_in: PrinterUpdate,
        db: Annotated[Session, Depends(deps.get_db)],
        current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> Printer:
    return printer_service.update(db, printer_id=printer_id, obj_in=printer_in)


@router.delete(
    "/{printer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**CRUD_RESPONSES},
)
def delete_printer(
    printer_id: int,
        db: Annotated[Session, Depends(deps.get_db)],
        current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> None:
    printer_service.delete(db, printer_id=printer_id)
