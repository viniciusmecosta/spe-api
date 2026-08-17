from datetime import date
from unittest.mock import MagicMock

from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.holidays.holiday_models import Holiday
from app.features.users.user_models import User, UserWorkScheduleConfig
from app.features.users.work_hour_service import work_hour_service
from app.shared.enums import AdjustmentType
from app.shared.time_calculation_service import DailyTimeResult


def test_calculate_balance_no_schedule(mocker, db_session_mock):
    mocker.patch("app.features.time_records.time_record_repository.time_record_repository.get_by_range",
                 return_value=[])
    mocker.patch("app.features.holidays.holiday_repository.holiday_repository.get_all", return_value=[])
    mock_user = MagicMock(spec=User)
    mock_user.historical_schedules = []
    mocker.patch("app.features.users.user_repository.user_repository.get", return_value=mock_user)

    response = work_hour_service.calculate_balance(db_session_mock, 1, date(2023, 10, 1), date(2023, 10, 5))

    assert response.balance_hours == 0.0
    assert response.expected_hours == 0.0
    assert response.total_worked_hours == 0.0


def test_calculate_balance_with_schedule_perfect_attendance(mocker, db_session_mock):
    mock_user = MagicMock(spec=User)
    mock_schedule = MagicMock(spec=UserWorkScheduleConfig)
    mock_schedule.valid_from = date(2023, 1, 1)
    mock_schedule.valid_until = None
    mock_schedule.daily_hours = 8.0
    mock_schedule.day_of_week = 0
    mock_user.historical_schedules = [mock_schedule]

    mocker.patch("app.features.users.user_repository.user_repository.get", return_value=mock_user)
    mocker.patch("app.features.holidays.holiday_repository.holiday_repository.get_all", return_value=[])
    mocker.patch("app.features.time_records.time_record_repository.time_record_repository.get_by_range",
                 return_value=[])

    mock_calc = mocker.patch("app.shared.time_calculation_service.time_calculation_service.calculate_daily_time")
    res_mock = DailyTimeResult(
        raw_worked_seconds=8 * 3600,
        net_worked_seconds=8 * 3600,
        gross_worked_seconds=8 * 3600,
        waiver_seconds=0,
        unapproved_extra_seconds=0,
        extra_seconds=0,
        missing_seconds=0,
        entries=[],
        exits=[],
        punches=[],
        punch_blocks=[]
    )
    mock_calc.return_value = res_mock

    response = work_hour_service.calculate_balance(db_session_mock, 1, date(2023, 10, 2), date(2023, 10, 2))

    assert response.expected_hours == 8.0
    assert response.total_worked_hours == 8.0
    assert response.balance_hours == 0.0


def test_calculate_balance_with_holiday(mocker, db_session_mock):
    mock_user = MagicMock(spec=User)
    mock_schedule = MagicMock(spec=UserWorkScheduleConfig)
    mock_schedule.valid_from = date(2023, 1, 1)
    mock_schedule.valid_until = None
    mock_schedule.daily_hours = 8.0
    mock_schedule.day_of_week = 0
    mock_user.historical_schedules = [mock_schedule]

    mock_holiday = MagicMock(spec=Holiday)
    mock_holiday.date = date(2023, 10, 2)

    mocker.patch("app.features.users.user_repository.user_repository.get", return_value=mock_user)
    mocker.patch("app.features.holidays.holiday_repository.holiday_repository.get_all", return_value=[mock_holiday])
    mocker.patch("app.features.time_records.time_record_repository.time_record_repository.get_by_range",
                 return_value=[])

    mock_calc = mocker.patch("app.shared.time_calculation_service.time_calculation_service.calculate_daily_time")
    res_mock = DailyTimeResult(
        raw_worked_seconds=0,
        net_worked_seconds=0,
        gross_worked_seconds=0,
        waiver_seconds=0,
        unapproved_extra_seconds=0,
        extra_seconds=0,
        missing_seconds=0,
        entries=[],
        exits=[],
        punches=[],
        punch_blocks=[]
    )
    mock_calc.return_value = res_mock

    response = work_hour_service.calculate_balance(db_session_mock, 1, date(2023, 10, 2), date(2023, 10, 2))

    assert response.expected_hours == 0.0
    assert response.total_worked_hours == 0.0
    assert response.balance_hours == 0.0


def test_calculate_balance_with_waiver_and_unapproved_extra(mocker, db_session_mock):
    mock_user = MagicMock(spec=User)
    mock_schedule = MagicMock(spec=UserWorkScheduleConfig)
    mock_schedule.valid_from = date(2023, 1, 1)
    mock_schedule.valid_until = None
    mock_schedule.daily_hours = 8.0
    mock_schedule.day_of_week = 0
    mock_user.historical_schedules = [mock_schedule]

    mocker.patch("app.features.users.user_repository.user_repository.get", return_value=mock_user)
    mocker.patch("app.features.holidays.holiday_repository.holiday_repository.get_all", return_value=[])
    mocker.patch("app.features.time_records.time_record_repository.time_record_repository.get_by_range",
                 return_value=[])

    mock_waiver = MagicMock(spec=AdjustmentRequest)
    mock_waiver.target_date = date(2023, 10, 2)
    mock_waiver.adjustment_type = AdjustmentType.WAIVER

    mock_unapproved = MagicMock(spec=AdjustmentRequest)
    mock_unapproved.target_date = date(2023, 10, 2)
    mock_unapproved.adjustment_type = AdjustmentType.EXTRA_TIME

    class MultiQueryMock:
        def __init__(self):
            self.calls = 0

        def filter(self, *args, **kwargs):
            return self

        def all(self):
            self.calls += 1
            if self.calls == 1:
                return [mock_waiver]
            return [mock_unapproved]

    db_session_mock.query.return_value = MultiQueryMock()

    mock_calc = mocker.patch("app.shared.time_calculation_service.time_calculation_service.calculate_daily_time")
    res_mock = DailyTimeResult(
        raw_worked_seconds=10 * 3600,
        net_worked_seconds=8 * 3600,
        gross_worked_seconds=10 * 3600,
        waiver_seconds=8 * 3600,
        unapproved_extra_seconds=2 * 3600,
        extra_seconds=2 * 3600,
        missing_seconds=0,
        entries=[],
        exits=[],
        punches=[],
        punch_blocks=[]
    )
    mock_calc.return_value = res_mock

    response = work_hour_service.calculate_balance(db_session_mock, 1, date(2023, 10, 2), date(2023, 10, 2))

    assert response.expected_hours == 8.0
    assert response.total_worked_hours == 8.0
    assert response.balance_hours == 0.0
    assert mock_calc.call_args[1]["waiver_adj"] == mock_waiver
    assert mock_calc.call_args[1]["unapproved_extra_adjs"] == [mock_unapproved]
    assert mock_calc.call_args[1]["is_excused"] is True
