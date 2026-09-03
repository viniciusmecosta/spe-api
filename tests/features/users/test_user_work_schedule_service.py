from datetime import date, time
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.features.users.user_exceptions import (
    BulkScheduleNotFoundError,
    BulkScheduleValidationError,
    ScheduleOverlapError,
    SchedulePayrollClosedError,
)
from app.features.users.user_models import User, UserWorkScheduleConfig
from app.features.users.user_work_schedule_service import user_work_schedule_service


@pytest.mark.asyncio
async def test_check_payroll_closure_ok(db_session_mock, mocker):
    mocker.patch("app.features.payroll.payroll_repository.payroll_repository.get_by_month", return_value=None)
    await user_work_schedule_service.check_payroll_closure(db_session_mock, date(2026, 9, 1), date(2026, 9, 30))


@pytest.mark.asyncio
async def test_check_payroll_closure_closed(db_session_mock, mocker):
    closure = MagicMock()
    closure.is_closed = True
    mocker.patch("app.features.payroll.payroll_repository.payroll_repository.get_by_month", return_value=closure)
    start_date = date(2026, 9, 1)
    end_date = date(2026, 9, 30)
    with pytest.raises(SchedulePayrollClosedError) as exc:
        await user_work_schedule_service.check_payroll_closure(db_session_mock, start_date, end_date)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_check_payroll_closure_year_span(db_session_mock, mocker):
    mocker.patch("app.features.payroll.payroll_repository.payroll_repository.get_by_month", return_value=None)
    await user_work_schedule_service.check_payroll_closure(db_session_mock, date(2026, 11, 1), date(2027, 2, 1))


def test_apply_schedule_updates_variations():
    sch = UserWorkScheduleConfig(id=1, user_id=1, day_of_week=0)
    sch_data = {
        "day_of_week": 1,
        "entry_1": "22:00:00",
        "exit_1": "06:00:00",
        "entry_2": time(10, 0),
        "exit_2": time(8, 0)
    }
    user_work_schedule_service._apply_schedule_updates(sch, sch_data, date(2026, 9, 1), date(2026, 9, 30))
    assert sch.day_of_week == 1
    assert sch.daily_hours == 30.0


def test_apply_schedule_updates_invalid_and_none():
    sch = UserWorkScheduleConfig(id=1, user_id=1, day_of_week=0)
    sch_data = {
        "day_of_week": 0,
        "entry_1": "invalid:time",
        "exit_1": 12345,
        "entry_2": None,
        "exit_2": None
    }
    user_work_schedule_service._apply_schedule_updates(sch, sch_data, date(2026, 9, 1), date(2026, 9, 30))
    assert sch.daily_hours == 0.0


def test_extract_schedule_data():
    sch = UserWorkScheduleConfig(
        day_of_week=1,
        daily_hours=8.0,
        valid_from=date(2026, 9, 1),
        valid_until=date(2026, 9, 30),
        entry_1=time(8, 0),
        exit_1=time(12, 0),
        entry_2=time(13, 0),
        exit_2=time(17, 0)
    )
    data = user_work_schedule_service._extract_schedule_data(sch)
    assert data["day_of_week"] == 1
    assert data["daily_hours"] == 8.0
    assert data["entry_1"] == "08:00:00"


def test_handle_schedule_overlap():
    sch1 = UserWorkScheduleConfig(id=1, day_of_week=1, valid_from=date(2026, 9, 1), valid_until=date(2026, 9, 30))
    user = User(id=1, historical_schedules=[sch1])

    user_work_schedule_service.handle_schedule_overlap(user, 1, date(2026, 9, 1), date(2026, 9, 30), ignore_id=1)
    user_work_schedule_service.handle_schedule_overlap(user, 2, date(2026, 9, 1), date(2026, 9, 30))
    user_work_schedule_service.handle_schedule_overlap(user, 1, date(2026, 10, 1), date(2026, 10, 31))

    overlap_date = date(2026, 9, 15)
    with pytest.raises(ScheduleOverlapError) as exc:
        user_work_schedule_service.handle_schedule_overlap(user, 1, overlap_date, None)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_get_bulk_schedules(db_session_mock):
    cfg1 = UserWorkScheduleConfig(
        id=1, user_id=1, day_of_week=1, daily_hours=8.0,
        valid_from=date(2026, 9, 1), valid_until=date(2026, 9, 30),
        entry_1=time(8, 0), exit_1=time(17, 0), entry_2=None, exit_2=None
    )
    query_mock = MagicMock()
    query_mock.filter.return_value.all.return_value = [cfg1]
    db_session_mock.query.return_value = query_mock

    res = await user_work_schedule_service.get_bulk_schedules(db_session_mock, 9, 2026)
    assert len(res) == 1
    assert res[0]["valid_from"] == date(2026, 9, 1)
    assert len(res[0]["users"]) == 1
    assert res[0]["users"][0]["user_id"] == 1


@pytest.mark.asyncio
async def test_get_bulk_schedule_found(db_session_mock):
    cfg1 = UserWorkScheduleConfig(
        id=1, user_id=1, day_of_week=1, daily_hours=8.0,
        valid_from=date(2026, 9, 1), valid_until=date(2026, 9, 30),
        entry_1=time(8, 0), exit_1=time(17, 0), entry_2=None, exit_2=None
    )
    query_mock = MagicMock()
    query_mock.filter.return_value.all.return_value = [cfg1]
    db_session_mock.query.return_value = query_mock

    res = await user_work_schedule_service.get_bulk_schedule(db_session_mock, date(2026, 9, 1), date(2026, 9, 30))
    assert res["valid_from"] == date(2026, 9, 1)
    assert len(res["users"]) == 1


@pytest.mark.asyncio
async def test_get_bulk_schedule_not_found(db_session_mock):
    query_mock = MagicMock()
    query_mock.filter.return_value.all.return_value = []
    db_session_mock.query.return_value = query_mock

    start_date = date(2026, 9, 1)
    end_date = date(2026, 9, 30)
    with pytest.raises(BulkScheduleNotFoundError) as exc:
        await user_work_schedule_service.get_bulk_schedule(db_session_mock, start_date, end_date)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_bulk_add_schedules_success(db_session_mock, mocker):
    mocker.patch.object(user_work_schedule_service, "check_payroll_closure", new_callable=AsyncMock)
    user = User(id=1, name="Test User")
    mocker.patch("app.features.users.user_repository.user_repository.get", return_value=user)
    mocker.patch.object(user_work_schedule_service, "handle_schedule_overlap")
    mocker.patch("app.features.system.audit_service.audit_service.log_change")

    bulk_data = {
        "valid_from": date(2026, 9, 1),
        "valid_until": date(2026, 9, 30),
        "users": [
            {
                "user_id": 1,
                "schedules": [
                    {"day_of_week": 1, "daily_hours": 8.0}
                ]
            }
        ]
    }

    res = await user_work_schedule_service.bulk_add_schedules(db_session_mock, bulk_data, 99)
    assert "sucesso" in res["message"]
    db_session_mock.add.assert_called()


@pytest.mark.asyncio
async def test_bulk_add_schedules_missing_dates(db_session_mock):
    bulk_data = {}
    with pytest.raises(BulkScheduleValidationError) as exc:
        await user_work_schedule_service.bulk_add_schedules(db_session_mock, bulk_data, 99)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_bulk_add_schedules_exceeds_duration(db_session_mock):
    bulk_data = {
        "valid_from": date(2026, 9, 1),
        "valid_until": date(2026, 11, 30),
        "users": []
    }
    with pytest.raises(BulkScheduleValidationError) as exc:
        await user_work_schedule_service.bulk_add_schedules(db_session_mock, bulk_data, 99)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_bulk_add_schedules_no_users(db_session_mock):
    bulk_data = {
        "valid_from": date(2026, 9, 1),
        "valid_until": date(2026, 9, 30),
        "users": []
    }
    with pytest.raises(BulkScheduleValidationError) as exc:
        await user_work_schedule_service.bulk_add_schedules(db_session_mock, bulk_data, 99)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_bulk_add_schedules_user_not_found(db_session_mock, mocker):
    mocker.patch.object(user_work_schedule_service, "check_payroll_closure", new_callable=AsyncMock)
    mocker.patch("app.features.users.user_repository.user_repository.get", return_value=None)

    bulk_data = {
        "valid_from": date(2026, 9, 1),
        "valid_until": date(2026, 9, 30),
        "users": [{"user_id": 999, "schedules": []}]
    }
    with pytest.raises(BulkScheduleValidationError) as exc:
        await user_work_schedule_service.bulk_add_schedules(db_session_mock, bulk_data, 99)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_bulk_add_schedules_overlap_error(db_session_mock, mocker):
    mocker.patch.object(user_work_schedule_service, "check_payroll_closure", new_callable=AsyncMock)
    user = User(id=1, name="Test User")
    mocker.patch("app.features.users.user_repository.user_repository.get", return_value=user)
    mocker.patch.object(user_work_schedule_service, "handle_schedule_overlap",
                        side_effect=ScheduleOverlapError())

    bulk_data = {
        "valid_from": date(2026, 9, 1),
        "valid_until": date(2026, 9, 30),
        "users": [
            {"user_id": 1, "schedules": [{"day_of_week": 0}]}
        ]
    }
    with pytest.raises(BulkScheduleValidationError) as exc:
        await user_work_schedule_service.bulk_add_schedules(db_session_mock, bulk_data, 99)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_update_bulk_schedules_success(db_session_mock, mocker):
    mocker.patch.object(user_work_schedule_service, "check_payroll_closure", new_callable=AsyncMock)
    mocker.patch("app.features.system.audit_service.audit_service.log_change")

    old_cfg_update = UserWorkScheduleConfig(id=10, user_id=1, day_of_week=1, valid_from=date(2026, 9, 1),
                                            valid_until=date(2026, 9, 30))
    old_cfg_delete = UserWorkScheduleConfig(id=11, user_id=1, day_of_week=2, valid_from=date(2026, 9, 1),
                                            valid_until=date(2026, 9, 30))

    query_mock = MagicMock()
    query_mock.filter.return_value.all.return_value = [old_cfg_update, old_cfg_delete]
    db_session_mock.query.return_value = query_mock

    user = User(id=1, name="Test User")
    mocker.patch("app.features.users.user_repository.user_repository.get", return_value=user)
    mocker.patch.object(user_work_schedule_service, "handle_schedule_overlap")

    bulk_data = {
        "valid_from": date(2026, 9, 1),
        "valid_until": date(2026, 9, 30),
        "users": [
            {
                "user_id": 1,
                "schedules": [
                    {"day_of_week": 1, "daily_hours": 9.0},
                    {"day_of_week": 3, "daily_hours": 8.0}
                ]
            }
        ]
    }

    res = await user_work_schedule_service.update_bulk_schedules(db_session_mock, date(2026, 9, 1), date(2026, 9, 30),
                                                           bulk_data, 99)
    assert res["message"] == "Expedientes atualizados com sucesso."
    db_session_mock.delete.assert_called_with(old_cfg_delete)


@pytest.mark.asyncio
async def test_update_bulk_schedules_invalid_dates(db_session_mock):
    start_date = date(2026, 9, 1)
    end_date = date(2026, 9, 30)
    empty_data = {}
    with pytest.raises(BulkScheduleValidationError) as exc:
        await user_work_schedule_service.update_bulk_schedules(db_session_mock, start_date, end_date, empty_data, 99)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_update_bulk_schedules_exceeds_duration(db_session_mock):
    start_date = date(2026, 9, 1)
    end_date = date(2026, 9, 30)
    bulk_data = {
        "valid_from": date(2026, 9, 1),
        "valid_until": date(2026, 11, 30),
        "users": []
    }
    with pytest.raises(BulkScheduleValidationError) as exc:
        await user_work_schedule_service.update_bulk_schedules(db_session_mock, start_date, end_date, bulk_data, 99)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_update_bulk_schedules_user_not_found(db_session_mock, mocker):
    mocker.patch.object(user_work_schedule_service, "check_payroll_closure", new_callable=AsyncMock)
    query_mock = MagicMock()
    query_mock.filter.return_value.all.return_value = []
    db_session_mock.query.return_value = query_mock
    mocker.patch("app.features.users.user_repository.user_repository.get", return_value=None)

    start_date = date(2026, 9, 1)
    end_date = date(2026, 9, 30)
    bulk_data = {
        "valid_from": date(2026, 9, 1),
        "valid_until": date(2026, 9, 30),
        "users": [{"user_id": 999, "schedules": [{"day_of_week": 0}]}]
    }
    with pytest.raises(BulkScheduleValidationError) as exc:
        await user_work_schedule_service.update_bulk_schedules(db_session_mock, start_date, end_date, bulk_data, 99)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_update_bulk_schedules_overlap_error(db_session_mock, mocker):
    mocker.patch.object(user_work_schedule_service, "check_payroll_closure", new_callable=AsyncMock)
    old_cfg = UserWorkScheduleConfig(id=10, user_id=1, day_of_week=1, valid_from=date(2026, 9, 1),
                                     valid_until=date(2026, 9, 30))
    query_mock = MagicMock()
    query_mock.filter.return_value.all.return_value = [old_cfg]
    db_session_mock.query.return_value = query_mock

    user = User(id=1, name="Test User")
    mocker.patch("app.features.users.user_repository.user_repository.get", return_value=user)
    mocker.patch.object(user_work_schedule_service, "handle_schedule_overlap",
                        side_effect=ScheduleOverlapError())

    start_date = date(2026, 9, 1)
    end_date = date(2026, 9, 30)
    bulk_data = {
        "valid_from": date(2026, 9, 1),
        "valid_until": date(2026, 9, 30),
        "users": [
            {"user_id": 1, "schedules": [{"day_of_week": 1}, {"day_of_week": 2}]}
        ]
    }
    with pytest.raises(BulkScheduleValidationError) as exc:
        await user_work_schedule_service.update_bulk_schedules(db_session_mock, start_date, end_date, bulk_data, 99)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_delete_bulk_schedules_success(db_session_mock, mocker):
    mocker.patch.object(user_work_schedule_service, "check_payroll_closure", new_callable=AsyncMock)
    mocker.patch("app.features.system.audit_service.audit_service.log_change")

    old_cfg = UserWorkScheduleConfig(id=10, user_id=1, day_of_week=1, valid_from=date(2026, 9, 1),
                                     valid_until=date(2026, 9, 30))
    query_mock = MagicMock()
    query_mock.filter.return_value.all.return_value = [old_cfg]
    db_session_mock.query.return_value = query_mock

    res = await user_work_schedule_service.delete_bulk_schedules(db_session_mock, date(2026, 9, 1), date(2026, 9, 30),
                                                                 99)
    assert "sucesso" in res["message"]
    db_session_mock.delete.assert_called_with(old_cfg)


@pytest.mark.asyncio
async def test_delete_bulk_schedules_not_found(db_session_mock, mocker):
    mocker.patch.object(user_work_schedule_service, "check_payroll_closure", new_callable=AsyncMock)
    query_mock = MagicMock()
    query_mock.filter.return_value.all.return_value = []
    db_session_mock.query.return_value = query_mock

    start_date = date(2026, 9, 1)
    end_date = date(2026, 9, 30)
    with pytest.raises(BulkScheduleNotFoundError) as exc:
        await user_work_schedule_service.delete_bulk_schedules(db_session_mock, start_date, end_date, 99)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_bulk_operations_enqueue_background_reprocessing(db_session_mock, mocker):
    mocker.patch.object(user_work_schedule_service, "check_payroll_closure", new_callable=AsyncMock)
    mocker.patch("app.features.system.audit_service.audit_service.log_change")

    user_mock = User(id=1, name="Test User")
    mocker.patch("app.features.users.user_repository.user_repository.get", return_value=user_mock)

    bg_mock = MagicMock()
    valid_from = date(2026, 8, 1)
    valid_until = date(2026, 8, 15)

    bulk_data = {
        "valid_from": valid_from,
        "valid_until": valid_until,
        "users": [{"user_id": 1, "schedules": [{"day_of_week": 0, "entry_1": "08:00", "exit_1": "17:00"}]}]
    }

    await user_work_schedule_service.bulk_add_schedules(
        db_session_mock,
        bulk_data=bulk_data,
        current_user_id=99,
        background_tasks=bg_mock
    )
    bg_mock.add_task.assert_called_once()

    bg_mock.reset_mock()
    old_cfg = UserWorkScheduleConfig(id=10, user_id=1, day_of_week=0, valid_from=valid_from, valid_until=valid_until)
    query_mock = MagicMock()
    query_mock.filter.return_value.all.return_value = [old_cfg]
    db_session_mock.query.return_value = query_mock

    await user_work_schedule_service.update_bulk_schedules(
        db_session_mock,
        old_valid_from=valid_from,
        old_valid_until=valid_until,
        bulk_data=bulk_data,
        current_user_id=99,
        background_tasks=bg_mock
    )
    bg_mock.add_task.assert_called_once()

    bg_mock.reset_mock()
    await user_work_schedule_service.delete_bulk_schedules(
        db_session_mock,
        valid_from=valid_from,
        valid_until=valid_until,
        current_user_id=99,
        background_tasks=bg_mock
    )
    bg_mock.add_task.assert_called_once()


@pytest.mark.asyncio
async def test_user_work_schedule_service_async_session_branches(mocker):
    from unittest.mock import AsyncMock
    async_sess = AsyncMock()
    async_sess.sync_session = MagicMock()

    mocker.patch("app.features.users.user_work_schedule_service.async_payroll_repository.get_by_month",
                 new_callable=AsyncMock, return_value=None)
    await user_work_schedule_service.check_payroll_closure(async_sess, date(2026, 1, 1), date(2026, 1, 31))

    cfg = UserWorkScheduleConfig(id=1, user_id=1, day_of_week=0, valid_from=date(2026, 1, 1),
                                 valid_until=date(2026, 1, 31))

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [cfg]
    async_sess.scalars.return_value = mock_scalars

    res_bulk_list = await user_work_schedule_service.get_bulk_schedules(async_sess, month=1, year=2026)
    assert len(res_bulk_list) == 1

    res_single_bulk = await user_work_schedule_service.get_bulk_schedule(async_sess, date(2026, 1, 1),
                                                                         date(2026, 1, 31))
    assert res_single_bulk["valid_from"] == date(2026, 1, 1)

    mocker.patch("app.features.users.user_work_schedule_service.audit_service.async_log_change", new_callable=AsyncMock)
    mocker.patch.object(user_work_schedule_service, "check_payroll_closure", new_callable=AsyncMock)

    await user_work_schedule_service.delete_bulk_schedules(
        async_sess,
        valid_from=date(2026, 1, 1),
        valid_until=date(2026, 1, 31),
        current_user_id=1,
    )
    async_sess.commit.assert_called_once()
