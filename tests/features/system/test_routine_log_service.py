from datetime import date
from unittest.mock import patch

import pytest
from app.features.system.routine_log_service import RoutineLogService


@pytest.mark.asyncio
async def test_get_logs(db_session_mock):
    service = RoutineLogService(db=db_session_mock)
    with patch("app.features.system.routine_log_service.routine_log_repository.get_logs") as mock_get_logs:
        mock_get_logs.return_value = ["log1", "log2"]
        start_date = date(2023, 1, 1)
        end_date = date(2023, 1, 2)

        result = await service.get_logs(
            db=db_session_mock,
            routine_type="type1",
            status="success",
            start_date=start_date,
            end_date=end_date,
            order_by="asc",
            skip=10,
            limit=20
        )

        assert result == ["log1", "log2"]
        mock_get_logs.assert_called_once_with(
            db_session_mock,
            routine_type="type1",
            status="success",
            start_date=start_date,
            end_date=end_date,
            order_by="asc",
            skip=10,
            limit=20
        )


@pytest.mark.asyncio
async def test_get_logs_defaults(db_session_mock):
    service = RoutineLogService(db=db_session_mock)
    with patch("app.features.system.routine_log_service.routine_log_repository.get_logs") as mock_get_logs:
        mock_get_logs.return_value = []

        result = await service.get_logs(db=db_session_mock)

        assert result == []
        mock_get_logs.assert_called_once_with(
            db_session_mock,
            routine_type=None,
            status=None,
            start_date=None,
            end_date=None,
            order_by="desc",
            skip=0,
            limit=100
        )
