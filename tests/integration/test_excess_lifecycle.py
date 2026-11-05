from datetime import date

import pytest
from sqlalchemy import select
from test_api_workflows import api

from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.daily_summaries.daily_summary_models import DailySummary
from app.features.system.system_models import AuditLog
from app.shared.daily_excess_service import daily_excess_service
from app.shared.enums import AdjustmentType

__all__ = ["api"]
pytestmark = pytest.mark.asyncio


async def _seed_excess_scenario(api):
    user_id = await api.create_employee()
    await api.request("POST", "/schedules/bulk", json={
        "valid_from": "2026-09-01", "valid_until": "2026-09-30", "users": [{
            "user_id": user_id, "schedules": [{"day_of_week": 1, "daily_minutes": 480,
              "entry_1": "08:00", "exit_1": "12:00", "entry_2": "13:00", "exit_2": "17:00",
              "is_daily_excess_enabled": True}],
        }],
    })
    await api.add_punch(user_id, "ENTRY", "08:00")
    await api.add_punch(user_id, "EXIT", "17:00")
    adjustments = await api.json("GET", "/adjustments", params={"scope": "team", "month": 9, "year": 2026})
    excess = next(item for item in adjustments if item["adjustment_type"] == "DAILY_EXCESS")
    return user_id, excess


async def test_excess_approval_transitions_update_summary_and_audit(api, pg_session_factory):
    user_id, excess = await _seed_excess_scenario(api)
    excess_id = excess["id"]

    async def verify(accounted, authorized):
        async with pg_session_factory() as session:
            row = await session.scalar(select(DailySummary).where(
                DailySummary.user_id == user_id, DailySummary.apuration_date == date(2026, 9, 29),
            ))
            assert row.worked_minutes == 540
            assert row.excess_minutes == 60
            assert row.accounted_minutes == accounted
            assert row.authorized_excess_minutes == authorized

    await verify(480, 0)
    response = await api.request("PUT", f"/adjustments/{excess_id}/review", json={"status": "APPROVED", "approved_amount_minutes": 30})
    assert response.json()["approved_amount_minutes"] == 30
    await verify(510, 30)
    async with pg_session_factory() as session:
        before = await session.scalar(select(AdjustmentRequest).where(AdjustmentRequest.id == excess_id))
        prior_status = before.status
        prior_hours = before.approved_amount_hours
        prior_reviewed_at = before.reviewed_at
        audits_before = len(list(await session.scalars(select(AuditLog).where(
            AuditLog.entity_id == excess_id, AuditLog.action == "APPROVE_ADJUSTMENT",
        ))))
    response = await api.request("PUT", f"/adjustments/{excess_id}/review", 400,
                                 json={"status": "APPROVED", "approved_amount_hours": 2})
    assert "excedente" in response.json()["detail"].lower()
    await api.request("PUT", f"/adjustments/{excess_id}/review", 400,
                      json={"status": "APPROVED", "approved_amount_hours": 61 / 60})
    await verify(510, 30)
    async with pg_session_factory() as session:
        after = await session.scalar(select(AdjustmentRequest).where(AdjustmentRequest.id == excess_id))
        assert after.status == prior_status
        assert after.approved_amount_hours == prior_hours
        assert after.reviewed_at == prior_reviewed_at
        audits_after = len(list(await session.scalars(select(AuditLog).where(
            AuditLog.entity_id == excess_id, AuditLog.action == "APPROVE_ADJUSTMENT",
        ))))
        assert audits_after == audits_before
    await api.request("PUT", f"/adjustments/{excess_id}/review", json={"status": "APPROVED", "approved_amount_hours": 1})
    await verify(540, 60)
    await api.request("PUT", f"/adjustments/{excess_id}/review", json={"status": "APPROVED", "approved_amount_hours": 0.5})
    await api.request("PUT", f"/adjustments/{excess_id}/review", json={"status": "APPROVED", "approved_amount_hours": 0.75})
    await verify(525, 45)
    async with pg_session_factory() as session:
        audit = await session.scalar(select(AuditLog).where(
            AuditLog.action == "APPROVE_ADJUSTMENT", AuditLog.entity_id == excess_id,
        ).order_by(AuditLog.id.desc()))
        assert audit.old_data["approved_amount_minutes"] == 30
        assert audit.new_data["approved_amount_minutes"] == 45
    await api.request("PUT", f"/adjustments/{excess_id}/review", json={"status": "REJECTED", "comment": "Revisão sintética"})
    await verify(480, 0)
    await api.request("PUT", f"/adjustments/admin/{excess_id}/revert-status",
                      json={"status": "PENDING", "comment": "Revisão sintética"})
    await verify(480, 0)
    await api.request("PUT", f"/adjustments/{excess_id}/review", json={"status": "APPROVED", "approved_amount_hours": 0})
    await verify(480, 0)
    await api.request("PUT", f"/adjustments/{excess_id}/review", json={"status": "APPROVED", })
    await verify(540, 60)


@pytest.mark.parametrize("review", ["pending", "approved", "rejected"])
async def test_holiday_removes_excess_and_deletion_restores_it(api, pg_session_factory, review):
    user_id, excess = await _seed_excess_scenario(api)
    if review == "approved":
        await api.request("PUT", f"/adjustments/{excess['id']}/review", json={"status": "APPROVED", "approved_amount_hours": 0.5})
    elif review == "rejected":
        await api.request("PUT", f"/adjustments/{excess['id']}/review", json={"status": "REJECTED", "comment": "Revisão sintética"})
    holiday = await api.json("POST", "/holidays/", 201, json={"date": "2026-09-29", "name": "Feriado sintético"})
    async with pg_session_factory() as session:
        pending = await session.scalar(select(AdjustmentRequest).where(
            AdjustmentRequest.user_id == user_id, AdjustmentRequest.target_date == date(2026, 9, 29),
            AdjustmentRequest.adjustment_type == AdjustmentType.DAILY_EXCESS,
            AdjustmentRequest.deleted_at.is_(None),
        ))
        row = await session.scalar(select(DailySummary).where(
            DailySummary.user_id == user_id, DailySummary.apuration_date == date(2026, 9, 29),
        ))
        assert (row.worked_minutes, row.accounted_minutes, row.expected_minutes, row.excess_minutes) == (540, 540, 0, 0)
        assert pending is None
        if review != "pending":
            invalidation = await session.scalar(select(AuditLog).where(
                AuditLog.action == "INVALIDATE_DAILY_EXCESS", AuditLog.entity_id == excess["id"],
            ))
            assert invalidation.old_data["status"] == review.upper()
        await daily_excess_service.evaluate_user_day_async(session, user_id, date(2026, 9, 29))
        await session.commit()
        pending = await session.scalar(select(AdjustmentRequest).where(
            AdjustmentRequest.user_id == user_id, AdjustmentRequest.target_date == date(2026, 9, 29),
            AdjustmentRequest.adjustment_type == AdjustmentType.DAILY_EXCESS,
            AdjustmentRequest.deleted_at.is_(None),
        ))
        assert pending is None
    await api.request("DELETE", f"/holidays/{holiday['id']}")
    async with pg_session_factory() as session:
        pending = await session.scalar(select(AdjustmentRequest).where(
            AdjustmentRequest.user_id == user_id, AdjustmentRequest.target_date == date(2026, 9, 29),
            AdjustmentRequest.adjustment_type == AdjustmentType.DAILY_EXCESS,
            AdjustmentRequest.deleted_at.is_(None),
        ))
        row = await session.scalar(select(DailySummary).where(
            DailySummary.user_id == user_id, DailySummary.apuration_date == date(2026, 9, 29),
        ))
        assert (row.worked_minutes, row.accounted_minutes, row.expected_minutes, row.excess_minutes) == (540, 480, 480, 60)
        assert pending is not None
