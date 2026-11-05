from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.reports.daily_report_service import DailyReportService
from app.features.system.telegram_service import TelegramService
from app.shared.enums import RecordType


@pytest.mark.parametrize(
    "names",
    [
        ("João Pedro Nevoa", "João Pedro Souza"),
        ("João Pedro Nevoa", "João Pedro Nevoa"),
        ("João <Pedro> Nevoa", "João <Pedro> Souza"),
    ],
)
@pytest.mark.parametrize("channel", ["email", "telegram"])
async def test_notifications_keep_employees_with_matching_names_separate(names, channel):
    rows = [
        (
            SimpleNamespace(
                user_id=user_id,
                record_type=RecordType.ENTRY,
                record_datetime=datetime.fromisoformat(f"2026-10-26T{hour}:00:00-03:00"),
            ),
            SimpleNamespace(id=user_id, name=name),
        )
        for user_id, name, hour in [(1, names[0], "08"), (2, names[1], "09")]
    ]
    session = MagicMock()
    session.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=rows)))
    day = date(2026, 10, 26)
    if channel == "email":
        with patch(
            "app.features.reports.daily_report_service.anomaly_service.get_anomalies",
            new=AsyncMock(return_value=[]),
        ):
            result = await DailyReportService().generate_daily_report_html(session, day)
        assert result.count("<strong>") == 2
        assert result.count('background-color: #fffbf0') == 2
    else:
        grouped = TelegramService()._group_daily_activity(rows)
        assert len(grouped["26/10/2026"]) == 2
        assert all(len(punches) == 1 for punches in grouped["26/10/2026"].values())
        result = await TelegramService().generate_report_text(session, day, day)
    assert "08:00" in result
    assert "09:00" in result
    assert "<Pedro>" not in result
