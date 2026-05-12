from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Any, List

from app.api import deps
from app.domain.models.enums import UserRole
from app.domain.models.user import User, WorkSchedule
from app.repositories.user_repository import user_repository
from app.schemas.work_schedule import WorkSchedule as WorkScheduleSchema, WorkScheduleCreate

router = APIRouter()


@router.get("/user/{user_id}", response_model=List[WorkScheduleSchema])
def read_user_schedules(
        user_id: int,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    user = user_repository.get(db, user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    if current_user.id != user_id and current_user.role not in [UserRole.MANAGER, UserRole.ADMIN, UserRole.MAINTAINER]:
        raise HTTPException(status_code=403, detail="Permissão insuficiente")

    return user.schedules


@router.put("/user/{user_id}", response_model=List[WorkScheduleSchema])
def update_user_schedules(
        user_id: int,
        schedules: List[WorkScheduleCreate],
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager),
) -> Any:
    user = user_repository.get(db, user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    db.query(WorkSchedule).filter(WorkSchedule.user_id == user_id).delete()

    new_schedules = []
    for schedule_in in schedules:
        db_obj = WorkSchedule(
            user_id=user_id,
            day_of_week=schedule_in.day_of_week,
            daily_hours=schedule_in.daily_hours
        )
        db.add(db_obj)
        new_schedules.append(db_obj)

    db.commit()
    db.refresh(user)
    return new_schedules
