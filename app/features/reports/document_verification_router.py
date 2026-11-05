from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile

from app.features.reports.document_verification_service import (
    DocumentVerificationService,
)
from app.features.users.user_models import User
from app.shared import deps

router = APIRouter()


@router.post("/verify")
async def verify_document(
    file: Annotated[UploadFile, File(...)],
    current_user: Annotated[User, Depends(deps.get_current_manager)],
    service: Annotated[DocumentVerificationService, Depends()],
) -> dict[str, bool | str]:
    return await service.verify(file)
