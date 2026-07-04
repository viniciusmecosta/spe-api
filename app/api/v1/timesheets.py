from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api import deps
from app.domain.models.user import User
from app.services.timesheet_service import timesheet_service

router = APIRouter()


def validate_date_not_future(month: int, year: int):
    now = datetime.now()
    if year > now.year or (year == now.year and month > now.month):
        raise HTTPException(
            status_code=400,
            detail="Não é possível solicitar espelhos de ponto referentes a meses futuros."
        )


@router.get("/user/{user_id}/pdf")
def get_official_timesheet_user_pdf(
        user_id: int,
        month: int = Query(..., ge=1, le=12),
        year: int = Query(..., ge=2000),
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager)
):
    validate_date_not_future(month, year)
    pdf_buffer = timesheet_service.generate_user_timesheet_pdf(db, user_id, month, year)
    filename = f"espelho_ponto_{user_id}_{month:02d}_{year}.pdf"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/all/pdf")
def get_official_timesheet_all_pdf(
        month: int = Query(..., ge=1, le=12),
        year: int = Query(..., ge=2000),
        employee_ids: Optional[List[int]] = Query(None),
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager)
):
    validate_date_not_future(month, year)
    zip_buffer = timesheet_service.generate_all_timesheets_pdf_zip(db, month, year, employee_ids)
    filename = f"espelhos_ponto_lote_{month:02d}_{year}.zip"

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
