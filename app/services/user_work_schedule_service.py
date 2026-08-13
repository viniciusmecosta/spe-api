from collections import defaultdict
from datetime import date, timedelta
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import or_, and_
from sqlalchemy.orm import Session
from typing import Dict, List, Any

from app.domain.models.enums import DayOfWeek
from app.domain.models.user import User, UserWorkScheduleConfig
from app.repositories.payroll_repository import payroll_repository
from app.repositories.user_repository import user_repository
from app.services.audit_service import audit_service


class UserWorkScheduleService:
    def _apply_schedule_updates(self, sch: UserWorkScheduleConfig, sch_data: dict, valid_from: date, valid_until: date):
        from datetime import datetime, date, time
        
        sch.day_of_week = sch_data.get('day_of_week', sch.day_of_week)
        sch.entry_1 = sch_data.get('entry_1', sch.entry_1)
        sch.exit_1 = sch_data.get('exit_1', sch.exit_1)
        sch.entry_2 = sch_data.get('entry_2', sch.entry_2)
        sch.exit_2 = sch_data.get('exit_2', sch.exit_2)
        sch.valid_from = valid_from
        sch.valid_until = valid_until

        def _to_datetime(t_obj):
            if not t_obj:
                return None
            if isinstance(t_obj, str):
                try:
                    parts = t_obj.split(':')
                    if len(parts) >= 2:
                        return datetime.combine(date.today(), time(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0))
                except Exception:
                    return None
            if isinstance(t_obj, time):
                return datetime.combine(date.today(), t_obj)
            return None

        total_seconds = 0.0
        
        dt_entry1 = _to_datetime(sch.entry_1)
        dt_exit1 = _to_datetime(sch.exit_1)
        if dt_entry1 and dt_exit1:
            diff = (dt_exit1 - dt_entry1).total_seconds()
            if diff < 0:
                diff += 24 * 3600
            total_seconds += diff
            
        dt_entry2 = _to_datetime(sch.entry_2)
        dt_exit2 = _to_datetime(sch.exit_2)
        if dt_entry2 and dt_exit2:
            diff = (dt_exit2 - dt_entry2).total_seconds()
            if diff < 0:
                diff += 24 * 3600
            total_seconds += diff

        sch.daily_hours = round(total_seconds / 3600, 2)

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
                    status_code=400,
                    detail=f"Não é permitido alterar configurações de expediente. A folha de ponto de {current_month:02d}/{current_year} já está fechada."
                )
            current_month += 1
            if current_month > 12:
                current_month = 1
                current_year += 1

    def handle_schedule_overlap(self, user: User, day_of_week: int, valid_from: date, valid_until: date, ignore_id: int = None):
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
                    detail="Já existe um expediente vigente para esse dia informado. Edite o expediente existente para alterá-lo em vez de criar um novo por cima."
                )

    def get_bulk_schedules(self, db: Session, month: int, year: int) -> List[Dict[str, Any]]:
        start_of_month = date(year, month, 1)
        next_month = start_of_month.replace(day=28) + timedelta(days=4)
        end_of_month = next_month - timedelta(days=next_month.day)

        configs = db.query(UserWorkScheduleConfig).filter(
            UserWorkScheduleConfig.valid_from <= end_of_month,
            or_(
                UserWorkScheduleConfig.valid_until == None,
                UserWorkScheduleConfig.valid_until >= start_of_month
            )
        ).all()

        groups = defaultdict(lambda: defaultdict(list))
        
        for cfg in configs:
            key = (cfg.valid_from, cfg.valid_until)
            groups[key][cfg.user_id].append({
                "day_of_week": cfg.day_of_week,
                "daily_hours": cfg.daily_hours,
                "entry_1": cfg.entry_1,
                "exit_1": cfg.exit_1,
                "entry_2": cfg.entry_2,
                "exit_2": cfg.exit_2,
            })

        result = []
        for (v_from, v_until), users_dict in groups.items():
            users_list = []
            for user_id, sch_list in users_dict.items():
                users_list.append({
                    "user_id": user_id,
                    "schedules": sch_list
                })
            
            result.append({
                "valid_from": v_from,
                "valid_until": v_until,
                "users": users_list
            })

        return result

    def get_bulk_schedule(self, db: Session, valid_from: date, valid_until: date) -> Dict[str, Any]:
        configs = db.query(UserWorkScheduleConfig).filter(
            UserWorkScheduleConfig.valid_from == valid_from,
            UserWorkScheduleConfig.valid_until == valid_until
        ).all()

        if not configs:
            raise HTTPException(status_code=404, detail="Expediente em massa não encontrado para esse período.")

        users_dict = defaultdict(list)
        for cfg in configs:
            users_dict[cfg.user_id].append({
                "day_of_week": cfg.day_of_week,
                "daily_hours": cfg.daily_hours,
                "entry_1": cfg.entry_1,
                "exit_1": cfg.exit_1,
                "entry_2": cfg.entry_2,
                "exit_2": cfg.exit_2,
            })

        users_list = []
        for user_id, sch_list in users_dict.items():
            users_list.append({
                "user_id": user_id,
                "schedules": sch_list
            })

        return {
            "valid_from": valid_from,
            "valid_until": valid_until,
            "users": users_list
        }

    def _process_single_user_bulk_add(self, user, schedules_in, valid_from, valid_until, errors, new_schedules):
        for sch_data_dict in schedules_in:
            day_of_week = sch_data_dict.get('day_of_week')
            day_name = DayOfWeek(day_of_week).nome
            try:
                self.handle_schedule_overlap(user, day_of_week, valid_from, valid_until)
            except HTTPException:
                errors.append(
                    f"Usuário {user.name} (ID: {user.id}) - {day_name}: Já existe um expediente vigente para esse dia informado.")
                continue
            new_sch = UserWorkScheduleConfig(user_id=user.id)
            self._apply_schedule_updates(new_sch, sch_data_dict, valid_from, valid_until)
            new_schedules.append(new_sch)

    def bulk_add_schedules(self, db, bulk_data: dict, current_user_id: int):
        valid_from = bulk_data.get('valid_from')
        valid_until = bulk_data.get('valid_until')

        if not valid_from or not valid_until:
            raise HTTPException(status_code=400, detail="Data de início (valid_from) e fim (valid_until) são obrigatórias.")
            
        if (valid_until - valid_from).days > 31:
            raise HTTPException(status_code=400, detail="A duração do expediente não pode ser superior a 1 mês.")

        users_input = bulk_data.get('users', [])

        if not users_input:
            raise HTTPException(status_code=400, detail="Nenhum usuário informado.")

        errors = []
        new_schedules = []

        self.check_payroll_closure(db, valid_from, valid_until)

        for user_data in users_input:
            uid = user_data.get('user_id')
            user = user_repository.get(db, uid)
            if not user:
                errors.append(f"Usuário com ID {uid} não encontrado.")
                continue
            self._process_single_user_bulk_add(user, user_data.get('schedules', []), valid_from, valid_until, errors,
                                               new_schedules)

        if errors:
            raise HTTPException(status_code=400, detail=errors)

        for sch in new_schedules:
            db.add(sch)

        from fastapi.encoders import jsonable_encoder
        audit_service.log(
            db, user_id=current_user_id, action="CREATE",
            entity="USER_WORK_SCHEDULE_BULK", entity_id=0,
            new_data={"valid_from": str(valid_from), "valid_until": str(valid_until), "bulk_data": jsonable_encoder(bulk_data)}
        )

        return {"message": f"{len(new_schedules)} expedientes criados com sucesso."}

    def update_bulk_schedules(self, db: Session, old_valid_from: date, old_valid_until: date, bulk_data: dict, current_user_id: int):
        new_valid_from = bulk_data.get('valid_from')
        new_valid_until = bulk_data.get('valid_until')

        if not new_valid_from or not new_valid_until:
            raise HTTPException(status_code=400, detail="Data de início (valid_from) e fim (valid_until) são obrigatórias.")
            
        if (new_valid_until - new_valid_from).days > 31:
            raise HTTPException(status_code=400, detail="A duração do expediente não pode ser superior a 1 mês.")

        self.check_payroll_closure(db, old_valid_from, old_valid_until)
        self.check_payroll_closure(db, new_valid_from, new_valid_until)

        old_configs = db.query(UserWorkScheduleConfig).filter(
            UserWorkScheduleConfig.valid_from == old_valid_from,
            UserWorkScheduleConfig.valid_until == old_valid_until
        ).all()

        existing_map = {(cfg.user_id, cfg.day_of_week): cfg for cfg in old_configs}
        
        users_input = bulk_data.get('users', [])
        incoming_map = {}
        for user_data in users_input:
            uid = user_data.get('user_id')
            for sch_data_dict in user_data.get('schedules', []):
                incoming_map[(uid, sch_data_dict.get('day_of_week'))] = sch_data_dict

        errors = []
        to_delete = []
        to_update = []
        to_create = []

        self._map_bulk_updates(db, existing_map, incoming_map, to_delete, to_update, to_create, errors)

        if errors:
            raise HTTPException(status_code=400, detail=errors)

        return self._apply_bulk_updates_db(db, to_delete, to_update, to_create, new_valid_from, new_valid_until, errors,
                                           old_valid_from, old_valid_until, bulk_data, current_user_id)

    def _map_bulk_updates(self, db, existing_map, incoming_map, to_delete, to_update, to_create, errors):
        for key, old_cfg in existing_map.items():
            if key not in incoming_map:
                to_delete.append(old_cfg)
            else:
                to_update.append((old_cfg, incoming_map[key]))
        for key, new_data in incoming_map.items():
            if key not in existing_map:
                uid, _ = key
                user = user_repository.get(db, uid)
                if not user:
                    errors.append(f"Usuário com ID {uid} não encontrado.")
                    continue
                to_create.append((user, new_data))

    def _apply_bulk_updates_db(self, db, to_delete, to_update, to_create, new_valid_from, new_valid_until, errors,
                               old_valid_from, old_valid_until, bulk_data, current_user_id):
        for old_cfg, new_data in to_update:
            user = user_repository.get(db, old_cfg.user_id)
            try:
                self.handle_schedule_overlap(user, new_data.get('day_of_week'), new_valid_from, new_valid_until, ignore_id=old_cfg.id)
            except HTTPException:
                day_name = DayOfWeek(new_data.get('day_of_week')).nome
                errors.append(f"Usuário {user.name} (ID: {user.id}) - {day_name}: Já existe um expediente vigente.")
                
        for user, new_data in to_create:
            try:
                self.handle_schedule_overlap(user, new_data.get('day_of_week'), new_valid_from, new_valid_until)
            except HTTPException:
                day_name = DayOfWeek(new_data.get('day_of_week')).nome
                errors.append(f"Usuário {user.name} (ID: {user.id}) - {day_name}: Já existe um expediente vigente.")

        if errors:
            raise HTTPException(status_code=400, detail=errors)

        for cfg in to_delete:
            db.delete(cfg)

        for cfg, new_data in to_update:
            self._apply_schedule_updates(cfg, new_data, new_valid_from, new_valid_until)
            db.add(cfg)

        for user, new_data in to_create:
            new_sch = UserWorkScheduleConfig(user_id=user.id)
            self._apply_schedule_updates(new_sch, new_data, new_valid_from, new_valid_until)
            db.add(new_sch)

        audit_service.log(
            db, user_id=current_user_id, action="UPDATE",
            entity="USER_WORK_SCHEDULE_BULK", entity_id=0,
            old_data={"valid_from": str(old_valid_from), "valid_until": str(old_valid_until)},
            new_data={"valid_from": str(new_valid_from), "valid_until": str(new_valid_until), "bulk_data": jsonable_encoder(bulk_data)}
        )

        return {"message": "Expedientes atualizados com sucesso."}

    def delete_bulk_schedules(self, db: Session, valid_from: date, valid_until: date, current_user_id: int):
        self.check_payroll_closure(db, valid_from, valid_until)
        
        configs = db.query(UserWorkScheduleConfig).filter(
            UserWorkScheduleConfig.valid_from == valid_from,
            UserWorkScheduleConfig.valid_until == valid_until
        ).all()

        if not configs:
            raise HTTPException(status_code=404, detail="Expediente em massa não encontrado.")

        count = len(configs)
        for cfg in configs:
            db.delete(cfg)
            
        audit_service.log(
            db, user_id=current_user_id, action="DELETE",
            entity="USER_WORK_SCHEDULE_BULK", entity_id=0,
            old_data={"valid_from": str(valid_from), "valid_until": str(valid_until), "count": count},
            new_data=None
        )
        
        return {"message": f"{count} registros removidos com sucesso."}

user_work_schedule_service = UserWorkScheduleService()
