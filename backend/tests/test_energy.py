"""
test_energy.py — energy analytics and session lists, against the simulator.

Verifies:
- daily analytics and summary pass through from the cabinet
- the date range reaches the cabinet as query parameters
- a stale answer says so (is_stale + outcome "stale"), and only for the SAME range (O20)
- auth and RBAC
"""

DAILY = [
    {"date": "2026-04-01", "energy_kwh": 15.5, "water_liters": 300.0, "session_count": 5},
    {"date": "2026-04-02", "energy_kwh": 22.0, "water_liters": 450.0, "session_count": 8},
]


def test_daily_analytics_returns_data(client, admin_headers, marina_id, sim):
    sim.state.sim.analytics_daily = DAILY
    r = client.get(f"/api/marinas/{marina_id}/energy/daily", headers=admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["is_stale"] is False
    assert len(data["data"]) == 2
    assert data["data"][0]["energy_kwh"] == 15.5


def test_daily_analytics_with_date_range(client, admin_headers, marina_id, sim):
    sim.state.sim.analytics_daily = DAILY[:1]
    r = client.get(f"/api/marinas/{marina_id}/energy/daily", headers=admin_headers,
                   params={"date_from": "2026-04-01", "date_to": "2026-04-01"})
    assert r.status_code == 200
    assert ("GET", "/api/ext/analytics/consumption/daily") in sim.state.sim.calls


def test_session_summary_aggregation(client, admin_headers, marina_id, sim):
    sim.state.sim.analytics_summary = {
        "total_sessions": 45,
        "by_status": {"completed": 40, "active": 3, "denied": 2},
        "total_energy_kwh": 185.75,
        "total_water_liters": 3500.0,
        "completed_sessions": 40,
    }
    r = client.get(f"/api/marinas/{marina_id}/energy/summary", headers=admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["is_stale"] is False
    summary = data["data"]
    assert summary["total_sessions"] == 45
    assert summary["total_energy_kwh"] == 185.75
    assert sum(summary["by_status"].values()) == summary["total_sessions"]


def test_stale_data_flag_propagates(client, admin_headers, marina_id, sim):
    sim.state.sim.analytics_daily = DAILY
    url = f"/api/marinas/{marina_id}/energy/daily"
    assert client.get(url, headers=admin_headers).json()["is_stale"] is False
    sim.state.sim.fail_next = [500] * 10
    r = client.get(url, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["is_stale"] is True
    assert r.json()["outcome"]["code"] == "stale"
    assert r.json()["data"] == DAILY


def test_stale_fallback_is_per_date_range(client, admin_headers, marina_id, sim):
    """O20: another range never borrows this range's cached data."""
    sim.state.sim.analytics_daily = DAILY
    url = f"/api/marinas/{marina_id}/energy/daily"
    client.get(url, headers=admin_headers, params={"date_from": "2026-04-01"})
    sim.state.sim.fail_next = [500] * 10
    r = client.get(url, headers=admin_headers, params={"date_from": "2026-03-01"})
    assert r.json()["data"] is None
    assert r.json()["outcome"]["code"] == "no_contact"


def test_energy_endpoints_require_auth(client, marina_id):
    assert client.get(f"/api/marinas/{marina_id}/energy/daily").status_code == 401
    assert client.get(f"/api/marinas/{marina_id}/energy/summary").status_code == 401


def test_marina_manager_blocked_from_restricted_marina_energy(
    client, manager_headers, restricted_marina_id, sim
):
    r = client.get(f"/api/marinas/{restricted_marina_id}/energy/daily", headers=manager_headers)
    assert r.status_code == 403


def test_active_and_pending_sessions_endpoints(client, admin_headers, marina_id, sim):
    active = {"id": 1, "status": "active", "pedestal_id": 1}
    pending = {"id": 2, "status": "pending", "pedestal_id": 1}
    sim.state.sim.sessions = [active, pending]
    r = client.get(f"/api/marinas/{marina_id}/sessions/active", headers=admin_headers)
    assert r.status_code == 200 and r.json()["sessions"] == [active]
    r = client.get(f"/api/marinas/{marina_id}/sessions/pending", headers=admin_headers)
    assert r.status_code == 200 and r.json()["sessions"] == [pending]
