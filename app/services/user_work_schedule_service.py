from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.domain.models.user import User, UserWorkScheduleConfig
from app.repositories.payroll_repository import payroll_repository
from app.repositories.user_repository import user_repository
from app.services.audit_service import audit_service


class UserWorkScheduleService:
    def _handle_existing_schedule(self, db, user, existing_sch, sch_data, sch_id, valid_from, valid_until, today):
        self.check_payroll_closure(db, existing_sch.valid_from, existing_sch.valid_until)
        new_valid_from = valid_from if valid_from else today
        self.check_payroll_closure(db, new_valid_from, valid_until)
        self.handle_schedule_overlap(user, sch_data.day_of_week, new_valid_from, valid_until,
                                     ignore_id=sch_id)
        self._apply_schedule_updates_from_obj(existing_sch, sch_data, new_valid_from, valid_until)

    def _create_new_schedule(self, db, user, sch_data, valid_from, valid_until, today, is_create):
        new_valid_from = valid_from if valid_from else today
        if not is_create:
            self.check_payroll_closure(db, new_valid_from, valid_until)
        self.handle_schedule_overlap(user, sch_data.day_of_week, new_valid_from, valid_until)

        new_sch = UserWorkScheduleConfig(
            day_of_week=sch_data.day_of_week, daily_hours=sch_data.daily_hours,
            entry_1=getattr(sch_data, 'entry_1', None), exit_1=getattr(sch_data, 'exit_1', None),
            entry_2=getattr(sch_data, 'entry_2', None), exit_2=getattr(sch_data, 'exit_2', None),
            valid_from=new_valid_from, valid_until=valid_until
        )
        user.historical_schedules.append(new_sch)

    def _process_single_schedule(self, db: Session, user: User, sch_data: any, is_create: bool):
        sch_id = getattr(sch_data, 'id', None)
        daily_hours = sch_data.daily_hours
        valid_from = getattr(sch_data, 'valid_from', None)
        valid_until = getattr(sch_data, 'valid_until', None)

        if daily_hours < 0 or daily_hours > 24:
            raise HTTPException(status_code=400, detail="As horas diárias devem estar entre 0 e 24.")

        today = date.today()
        if sch_id and not is_create:
            existing_sch = next((sch for sch in user.historical_schedules if sch.id == sch_id), None)
            if existing_sch:
                self._handle_existing_schedule(db, user, existing_sch, sch_data, sch_id, valid_from, valid_until, today)
        else:
            self._create_new_schedule(db, user, sch_data, valid_from, valid_until, today, is_create)

    def _apply_schedule_updates_from_obj(self, sch, sch_data, valid_from, valid_until):
        sch.day_of_week = sch_data.day_of_week
        sch.daily_hours = sch_data.daily_hours
        sch.entry_1 = getattr(sch_data, 'entry_1', None)
        sch.exit_1 = getattr(sch_data, 'exit_1', None)
        sch.entry_2 = getattr(sch_data, 'entry_2', None)
        sch.exit_2 = getattr(sch_data, 'exit_2', None)
        sch.valid_from = valid_from
        sch.valid_until = valid_until

    def _apply_schedule_updates(self, sch, sch_data: dict, valid_from, valid_until):
        sch.day_of_week = sch_data.get('day_of_week', sch.day_of_week)
        sch.daily_hours = sch_data.get('daily_hours', sch.daily_hours)
        sch.entry_1 = sch_data.get('entry_1', sch.entry_1)
        sch.exit_1 = sch_data.get('exit_1', sch.exit_1)
        sch.entry_2 = sch_data.get('entry_2', sch.entry_2)
        sch.exit_2 = sch_data.get('exit_2', sch.exit_2)
        sch.valid_from = valid_from
        sch.valid_until = valid_until

    def _extract_schedule_data(self, sch: UserWorkScheduleConfig) -> dict:
        return {
            "day_of_week": sch.day_of_week,
            "daily_hours": sch.daily_hours,
            "valid_from": str(sch.valid_from) if sch.valid_from else None,
            "valid_until": str(sch.valid_until) if sch.valid_until else None,
            "entry_1": str(sch.entry_1) if sch.entry_1 else None,
            "exit_1": str(sch.exit_1) if sch.exit_1 else None,
            "entry_2": str(sch.entry_2) if sch.entry_2 else None,
            "exit_2": str(sch.exit_2) if sch.exit_2 else None
        }

    def check_payroll_closure(self, db: Session, valid_from: date, valid_until: date = None):
        start_year = valid_from.year
        start_month = valid_from.month

        end_date = valid_until if valid_until else date.today()
        end_year = end_date.year
        end_month = end_date.month

        current_year = start_year
        current_month = start_month

        while (current_year < end_year) or (current_year == end_year and current_month <= end_month):
            closure = payroll_repository.get_by_month(db, current_month, current_year)
            if closure and closure.is_closed:
                raise HTTPException(
                    status_code=403,
                    detail=f"Não é permitido alterar configurações de expediente. A folha de ponto de {current_month:02d}/{current_year} já está fechada."
                )
            current_month += 1
            if current_month > 12:
                current_month = 1
                current_year += 1

    def handle_schedule_overlap(self, user: User, day_of_week: int, valid_from: date, valid_until: date,
                                ignore_id: int = None):
        for sch in user.historical_schedules:
            if ignore_id and sch.id == ignore_id:
                continue
            if sch.day_of_week != day_of_week:
                continue

            sch_end = sch.valid_until if sch.valid_until else date.max
            new_end = valid_until if valid_until else date.max

            if sch.valid_from <= new_end and sch_end >= valid_from:
                raise HTTPException(
                    status_code=400,
                    detail=f"Já existe um expediente vigente para esse dia informado. Edite o expediente existente para alterá-lo em vez de criar um novo por cima."
                )

    def _remove_stale_schedules(self, db: Session, user: User, schedules_in: list):
        current_sch_ids = [s.id for s in user.current_schedules]
        incoming_ids = [getattr(s, 'id', None) for s in schedules_in if getattr(s, 'id', None) is not None]

        schedules_to_remove = [sch for sch in user.historical_schedules if
                               sch.id in current_sch_ids and sch.id not in incoming_ids]
        for sch in schedules_to_remove:
            self.check_payroll_closure(db, sch.valid_from, sch.valid_until)
            user.historical_schedules.remove(sch)

    def sync_user_schedules(self, db: Session, user: User, schedules_in: list, is_create: bool = False):
        if schedules_in is None:
            return

        if not is_create:
            self._remove_stale_schedules(db, user, schedules_in)

        for sch_data in schedules_in:
            self._process_single_schedule(db, user, sch_data, is_create)

    def add_schedule(self, db: Session, user_id: int, sch_data: dict, current_user_id: int) -> UserWorkScheduleConfig:
        user = user_repository.get(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        valid_from = sch_data.get('valid_from') or date.today()
        self.check_payroll_closure(db, valid_from, sch_data.get('valid_until'))
        self.handle_schedule_overlap(user, sch_data.get('day_of_week'), valid_from, sch_data.get('valid_until'))

        new_sch = UserWorkScheduleConfig(user_id=user.id)
        self._apply_schedule_updates(new_sch, sch_data, valid_from, sch_data.get('valid_until'))

        db.add(new_sch)
        db.commit()
        db.refresh(new_sch)

        audit_service.log(
            db, user_id=current_user_id, action="CREATE",
            entity="USER_WORK_SCHEDULE", entity_id=new_sch.id,
            new_data={
                "user_id": new_sch.user_id,
                "day_of_week": new_sch.day_of_week,
                "daily_hours": new_sch.daily_hours,
                "valid_from": str(new_sch.valid_from) if new_sch.valid_from else None,
                "valid_until": str(new_sch.valid_until) if new_sch.valid_until else None
            }
        )
        return new_sch

    def update_schedule(self, db: Session, user_id: int, schedule_id: int, sch_data: dict,
                        current_user_id: int) -> UserWorkScheduleConfig:
        sch = db.query(UserWorkScheduleConfig).filter(
            UserWorkScheduleConfig.id == schedule_id,
            UserWorkScheduleConfig.user_id == user_id
        ).first()
        if not sch:
            raise HTTPException(status_code=404, detail="Schedule not found")

        old_data = self._extract_schedule_data(sch)

        self.check_payroll_closure(db, sch.valid_from, sch.valid_until)

        valid_from = sch_data.get('valid_from', sch.valid_from)
        valid_until = sch_data.get('valid_until', sch.valid_until)
        self.check_payroll_closure(db, valid_from, valid_until)

        user = user_repository.get(db, user_id)
        self.handle_schedule_overlap(user, sch_data.get('day_of_week', sch.day_of_week), valid_from, valid_until,
                                     ignore_id=sch.id)

        self._apply_schedule_updates(sch, sch_data, valid_from, valid_until)

        db.add(sch)
        db.commit()
        db.refresh(sch)

        new_data_raw = self._extract_schedule_data(sch)
        actual_old, actual_new = audit_service.compute_diffs(old_data, new_data_raw)

        audit_service.log(
            db, user_id=current_user_id, action="UPDATE",
            entity="USER_WORK_SCHEDULE", entity_id=sch.id,
            old_data=actual_old, new_data=actual_new
        )

        return sch

    def delete_schedule(self, db: Session, user_id: int, schedule_id: int, current_user_id: int):
        sch = db.query(UserWorkScheduleConfig).filter(
            UserWorkScheduleConfig.id == schedule_id,
            UserWorkScheduleConfig.user_id == user_id
        ).first()
        if not sch:
            raise HTTPException(status_code=404, detail="Schedule not found")

        self.check_payroll_closure(db, sch.valid_from, sch.valid_until)

        old_data = {
            "user_id": sch.user_id,
            "day_of_week": sch.day_of_week,
            "valid_from": str(sch.valid_from) if sch.valid_from else None,
            "valid_until": str(sch.valid_until) if sch.valid_until else None
        }

        db.delete(sch)
        db.commit()

        audit_service.log(
            db, user_id=current_user_id, action="DELETE",
            entity="USER_WORK_SCHEDULE", entity_id=schedule_id,
            old_data=old_data, new_data=None
        )


user_work_schedule_service = UserWorkScheduleService()
