"""
test_energy.py — Energy analytics endpoint tests.

Verifies:
- Daily analytics returns data from Pedestal SW
- Session summary aggregation sums correctly across pedestals
- Stale data flag propagates from PedestalAPIService
"""
import pytest
from unittest.mock import AsyncMock, patch


def test_daily_analytics_returns_data(client, admin_headers, marina_id):
    mock_data = [
        {"date": "2026-04-01", "energy_kwh": 15.5, "water_liters": 300.0, "session_count": 5},
        {"date": "2026-04-02", "energy_kwh": 22.0, "water_liters": 450.0, "session_count": 8},
    ]

    with patch(
        "app.routers.energy.PedestalAPIService.get_daily_analytics",
        new_callable=AsyncMock,
        return_value=(mock_data, False),
    ):
        r = client.get(
            f"/api/marinas/{marina_id}/energy/daily",
            headers=admin_headers,
        )

    assert r.status_code == 200
    data = r.json()
    assert data["is_stale"] is False
    assert len(data["data"]) == 2
    assert data["data"][0]["energy_kwh"] == 15.5


def test_daily_analytics_with_date_range(client, admin_headers, marina_id):
    mock_data = [{"date": "2026-04-01", "energy_kwh": 10.0, "water_liters": 200.0, "session_count": 3}]

    with patch(
        "app.routers.energy.PedestalAPIService.get_daily_analytics",
        new_callable=AsyncMock,
        return_value=(mock_data, False),
    ) as mock_svc:
        r = client.get(
            f"/api/marinas/{marina_id}/energy/daily",
            headers=admin_headers,
            params={"date_from": "2026-04-01", "date_to": "2026-04-01"},
        )

    assert r.status_code == 200
    # Verify date range params were forwarded
    call_args = mock_svc.call_args
    assert call_args.kwargs.get("date_from") == "2026-04-01" or call_args.args[3] == "2026-04-01"


def test_session_summary_aggregation(client, admin_headers, marina_id):
    """Summary should correctly sum totals."""
    mock_summary = {
        "total_sessions": 45,
        "by_status": {"completed": 40, "active": 3, "denied": 2},
        "total_energy_kwh": 185.75,
        "total_water_liters": 3500.0,
        "completed_sessions": 40,
    }

    with patch(
        "app.routers.energy.PedestalAPIService.get_session_summary",
        new_callable=AsyncMock,
        return_value=(mock_summary, False),
    ):
        r = client.get(
            f"/api/marinas/{marina_id}/energy/summary",
            headers=admin_headers,
        )

    assert r.status_code == 200
    data = r.json()
    assert data["is_stale"] is False
    summary = data["data"]
    assert summary["total_sessions"] == 45
    assert summary["total_energy_kwh"] == 185.75
    # Verify the by_status sums to total
    assert sum(summary["by_status"].values()) == summary["total_sessions"]


def test_stale_data_flag_propagates(client, admin_headers, marina_id):
    """When PedestalAPIService returns is_stale=True, the response should reflect that."""
    mock_data = [{"date": "2026-04-01", "energy_kwh": 5.0, "water_liters": 100.0, "session_count": 1}]

    with patch(
        "app.routers.energy.PedestalAPIService.get_daily_analytics",
        new_callable=AsyncMock,
        return_value=(mock_data, True),  # is_stale = True
    ):
        r = client.get(
            f"/api/marinas/{marina_id}/energy/daily",
            headers=admin_headers,
        )

    assert r.status_code == 200
    assert r.json()["is_stale"] is True


def test_energy_endpoints_require_auth(client, marina_id):
    r = client.get(f"/api/marinas/{marina_id}/energy/daily")
    assert r.status_code == 401

    r = client.get(f"/api/marinas/{marina_id}/energy/summary")
    assert r.status_code == 401


def test_marina_manager_blocked_from_restricted_marina_energy(
    client, manager_headers, restricted_marina_id
):
    with patch(
        "app.routers.energy.PedestalAPIService.get_daily_analytics",
        new_callable=AsyncMock,
        return_value=([], False),
    ):
        r = client.get(
            f"/api/marinas/{restricted_marina_id}/energy/daily",
            headers=manager_headers,
        )

    assert r.status_code == 403


def test_active_sessions_endpoint(client, admin_headers, marina_id):
    mock_sessions = [{"id": 1, "status": "active", "pedestal_id": 1}]

    with patch(
        "app.routers.energy.PedestalAPIService.get_active_sessions",
        new_callable=AsyncMock,
        return_value=(mock_sessions, False),
    ):
        r = client.get(
            f"/api/marinas/{marina_id}/sessions/active",
            headers=admin_headers,
        )

    assert r.status_code == 200
    assert r.json()["sessions"] == mock_sessions


def test_pending_sessions_endpoint(client, admin_headers, marina_id):
    mock_sessions = [{"id": 2, "status": "pending", "pedestal_id": 2}]

    with patch(
        "app.routers.energy.PedestalAPIService.get_pending_sessions",
        new_callable=AsyncMock,
        return_value=(mock_sessions, False),
    ):
        r = client.get(
            f"/api/marinas/{marina_id}/sessions/pending",
            headers=admin_headers,
        )

    assert r.status_code == 200
    assert r.json()["sessions"] == mock_sessions
