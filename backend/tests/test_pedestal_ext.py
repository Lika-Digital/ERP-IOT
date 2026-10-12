"""
test_pedestal_ext.py — berth occupancy, camera frame, camera stream — against the simulator.

TC-PX-01..11 keep their numbers. Since phase 2:
- TC-PX-12..15 (controls-tab audit) live in test_controls.py, against the simulator;
- TC-PX-17..19 (client builds the right path) are covered by
  test_cabinet_contract.py, which checks every path against spec §2.2.
"""
import pytest


def _occ(client, headers, marina_id, ref=1):
    return client.get(f"/api/marinas/{marina_id}/pedestals/{ref}/berths/occupancy",
                      headers=headers)


# ─── TC-PX-01  berth occupancy — success with berths ─────────────────────────

def test_berth_occupancy_returns_structured_data(client, admin_headers, marina_id, sim):
    r = _occ(client, admin_headers, marina_id)
    assert r.status_code == 200
    body = r.json()
    assert body["marina_id"] == marina_id and body["pedestal_id"] == 1
    assert body["is_stale"] is False
    assert body["data"]["pedestal_id"] == "MAR_KRK_ORM_01"   # the cabinet answers display_id
    assert [b["berth_id"] for b in body["data"]["berths"]] == [1, 2, 3, 4]
    assert body["data"]["berths"][0]["occupied"] is True
    assert body["data"]["berths"][1]["occupied"] is False


# ─── TC-PX-02  berth occupancy — empty berths with message ───────────────────

def test_berth_occupancy_empty_berths_shows_message(client, admin_headers, marina_id, sim):
    sim.state.sim.berths = []
    body = _occ(client, admin_headers, marina_id).json()
    assert body["data"]["berths"] == []
    assert "No berth definitions" in body["data"]["message"]


# ─── TC-PX-03  berth occupancy — feature unavailable (503) ───────────────────

def test_berth_occupancy_503_when_feature_unavailable(client, admin_headers, marina_id, sim):
    del sim.state.sim.enabled["berths.occupancy_ext"]
    r = _occ(client, admin_headers, marina_id)
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "not_enabled"


# ─── TC-PX-04 / 16  camera frame — JPEG bytes, image/jpeg ────────────────────

def test_camera_frame_returns_jpeg_bytes(client, admin_headers, marina_id, sim):
    r = client.get(f"/api/marinas/{marina_id}/pedestals/1/camera/frame", headers=admin_headers)
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert r.content.startswith(b"\xff\xd8")


# ─── TC-PX-05  camera frame — 503 on service failure ─────────────────────────

def test_camera_frame_503_on_service_failure(client, admin_headers, marina_id, sim):
    sim.state.sim.fail_next = [500] * 10
    r = client.get(f"/api/marinas/{marina_id}/pedestals/1/camera/frame", headers=admin_headers)
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "no_contact"


# ─── TC-PX-06 / 07  camera stream URL ────────────────────────────────────────

def test_camera_stream_url_returns_data(client, admin_headers, marina_id, sim):
    r = client.get(f"/api/marinas/{marina_id}/pedestals/1/camera/stream", headers=admin_headers)
    assert r.status_code == 200 and r.json()["data"]["stream_url"].startswith("rtsp://")


def test_camera_stream_url_503_when_unavailable(client, admin_headers, marina_id, sim):
    del sim.state.sim.enabled["camera.stream_ext"]
    r = client.get(f"/api/marinas/{marina_id}/pedestals/1/camera/stream", headers=admin_headers)
    assert r.status_code == 503


# ─── TC-PX-08  several pedestals, independent calls ──────────────────────────

def test_unknown_pedestal_is_a_503_with_a_code_not_a_crash(client, admin_headers, marina_id, sim):
    assert _occ(client, admin_headers, marina_id, 1).status_code == 200
    r = _occ(client, admin_headers, marina_id, 99)
    assert r.status_code == 503 and r.json()["detail"]["code"] == "not_found"


# ─── TC-PX-09 / 10  RBAC ─────────────────────────────────────────────────────

def test_marina_manager_blocked_from_restricted_marina_berths(
    client, manager_headers, restricted_marina_id, sim
):
    assert _occ(client, manager_headers, restricted_marina_id).status_code == 403
    assert sim.state.sim.calls == []


def test_marina_manager_can_access_own_marina_berths(client, manager_headers, marina_id, sim):
    assert _occ(client, manager_headers, marina_id).status_code == 200


# ─── TC-PX-11  unauthenticated returns 401 ───────────────────────────────────

@pytest.mark.parametrize("endpoint", ["berths/occupancy", "camera/frame", "camera/stream"])
def test_unauthenticated_ext_endpoints_return_401(client, marina_id, endpoint):
    """Strogo 401. Pritegnuto u fazi 1 (spec §0.1)."""
    r = client.get(f"/api/marinas/{marina_id}/pedestals/1/{endpoint}")
    assert r.status_code == 401, f"Expected 401 for {endpoint}, got {r.status_code}"
