"""P5 (spec §6.12): the reference photo goes to the cabinet, per cabinet, under the P1
record; the ERP strips every metadata tag and keeps no copy (P2).

The demo marina is seeded and the real collector runs once against the demo simulator;
every request to a cabinet goes through one counting transport, and the simulator keeps
the bytes it received — so "nothing was sent" and "no EXIF reached the cabinet" are
checked on what actually arrived.
"""
import asyncio
import hashlib
import io
from datetime import timedelta

import httpx
import pytest
from PIL import Image

from app.demo import seed as demo
from app.models.berth import Berth, VesselPhoto
from app.models.cabinet import Cabinet
from app.models.metering import CommandAudit
from app.services import cabinets as svc
from app.services import reference_photo as photo
from simulator import demo_world as w
from simulator.demo_sim import DemoWorld, create_demo_app
from tests.conftest import TestSession

NOW = (w.EPOCH + timedelta(days=38, hours=20, minutes=30)).replace(microsecond=0)
REAL = "KRK_REAL_TEST_02"


class Counting(httpx.AsyncBaseTransport):
    def __init__(self, inner):
        self.inner, self.urls = inner, []

    async def handle_async_request(self, request):
        self.urls.append(str(request.url))
        return await self.inner.handle_async_request(request)


def _jpeg_with_exif(size=(40, 20), orientation=6) -> bytes:
    img = Image.new("RGB", size, (200, 30, 30))
    exif = Image.Exif()
    exif[0x010F] = "SecretCam"                     # Make
    exif[0x0112] = orientation                     # Orientation: rotate 90 to show
    exif[0x8825] = {1: "N", 2: (45.0, 10.0, 0.0), 3: "E", 4: (14.0, 30.0, 0.0)}   # GPS
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    data = buf.getvalue()
    assert b"SecretCam" in data
    return data


@pytest.fixture(scope="module")
def demo_marina(setup_test_database):
    from app.services.collector import Collector
    from app.services.pedestal_api_factory import PedestalAPIClientFactory, get_pedestal_factory
    from app.utils import time as erp_time

    db = TestSession()
    demo.remove(db)
    out = demo.seed(db, port=18080, seed_value=28, password="pw", days=1, now=NOW)
    db.close()
    world = DemoWorld(seed=28, password="pw", clock=lambda: NOW)
    transport = Counting(httpx.ASGITransport(app=create_demo_app(world)))
    erp_time._simulated_clock = lambda: NOW
    factory = get_pedestal_factory()
    factory._clients.clear()
    factory.transport = transport
    factory.sleep = lambda s: asyncio.sleep(0)
    try:
        col = Collector(factory=PedestalAPIClientFactory(), session_factory=TestSession,
                        transport=transport, sleep=lambda s: asyncio.sleep(0))
        asyncio.run(col.run_all_once())
        yield out["marina_id"], transport, world
    finally:
        erp_time._simulated_clock = None
        factory.transport = None
        factory.sleep = None
        factory._clients.clear()
        db = TestSession()
        real = [c.id for c in db.query(Cabinet).filter(Cabinet.display_id == REAL)]
        db.query(CommandAudit).filter(CommandAudit.cabinet_id.in_(real)).delete(
            synchronize_session=False)
        db.query(Cabinet).filter(Cabinet.id.in_(real)).delete(synchronize_session=False)
        db.commit()
        demo.remove(db)
        db.close()


def _cab(mid, display_id) -> Cabinet:
    db = TestSession()
    try:
        return db.query(Cabinet).filter(Cabinet.marina_id == mid,
                                        Cabinet.display_id == display_id).one()
    finally:
        db.close()


def _berth_of(cab) -> Berth:
    db = TestSession()
    try:
        return (db.query(Berth).filter(Berth.cabinet_id == cab.id)
                .order_by(Berth.cabinet_berth_id).first())
    finally:
        db.close()


def _upload(client, headers, mid, berth, data=None, reason="new season photo", people="true"):
    return client.post(f"/api/marinas/{mid}/berths/{berth.id}/reference-photo",
                       files={"file": ("boat.jpg", data or _jpeg_with_exif(), "image/jpeg")},
                       data={"reason": reason, "no_people_confirmed": people}, headers=headers)


def _record(client, headers, mid, cab, enabled=True):
    return client.put(f"/api/marinas/{mid}/cabinets/{cab.id}/reference-upload",
                      json={"enabled": enabled, "reason": "gateway set bidirectional"},
                      headers=headers)


# ─── prepare(): the picture the cabinet gets ────────────────────────────────

def test_every_metadata_tag_is_gone_and_the_picture_stands_the_right_way():
    out = photo.prepare(_jpeg_with_exif(size=(40, 20), orientation=6))
    assert b"SecretCam" not in out.jpeg
    with Image.open(io.BytesIO(out.jpeg)) as img:
        assert img.format == "JPEG"
        assert len(img.getexif()) == 0 and "exif" not in img.info and "icc_profile" not in img.info
        assert img.size == (20, 40)             # orientation 6 applied to the pixels
    assert out.sha256 == hashlib.sha256(out.jpeg).hexdigest()


def test_png_and_webp_come_in_jpeg_goes_out():
    for fmt in ("PNG", "WEBP"):
        buf = io.BytesIO()
        Image.new("RGBA", (16, 16), (0, 0, 255, 128)).save(buf, format=fmt)
        out = photo.prepare(buf.getvalue())
        assert out.source_format == fmt and out.jpeg[:3] == b"\xff\xd8\xff"


def test_what_is_not_a_photo_or_too_large_is_refused(monkeypatch):
    with pytest.raises(photo.PhotoRefused) as e:
        photo.prepare(b"<svg xmlns='http://www.w3.org/2000/svg'/>")
    assert e.value.status == 422
    buf = io.BytesIO()
    Image.new("RGB", (8, 8)).save(buf, format="GIF")
    with pytest.raises(photo.PhotoRefused, match="JPEG, PNG or WebP"):
        photo.prepare(buf.getvalue())
    monkeypatch.setattr(photo, "MAX_BYTES", 200)
    with pytest.raises(photo.PhotoRefused) as e:
        photo.prepare(_jpeg_with_exif(size=(400, 400)))
    assert e.value.status == 413 and "10 MB" in e.value.sentence


# ─── the P1 record ───────────────────────────────────────────────────────────

def test_a_real_cabinet_gets_no_record_until_r26(client, admin_headers, demo_marina):
    mid, transport, _ = demo_marina
    db = TestSession()
    try:
        real = svc.provision_cabinet(
            db, marina_id=mid, pedestal_pk=1, display_id=REAL, device_type="full",
            base_url="http://100.64.0.10:8000", service_email="erp@krk.invalid",
            service_password="real-cabinet-pw", is_simulated=False)
    finally:
        db.close()
    r = _record(client, admin_headers, mid, real)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "waiting_for_cabinet_r26"
    assert photo.record(TestSession(), real) is None


def test_only_an_admin_writes_the_record(client, manager_headers, demo_marina):
    mid, _, _ = demo_marina
    assert _record(client, manager_headers, mid, _cab(mid, "SIM_C_04")).status_code == 403


def test_without_the_record_nothing_is_sent(client, admin_headers, demo_marina):
    mid, transport, world = demo_marina
    cab = _cab(mid, "SIM_C_06")
    before = len(transport.urls)
    r = _upload(client, admin_headers, mid, _berth_of(cab))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "reference_upload_not_recorded"
    assert transport.urls[before:] == [] and world.states["SIM_C_06"].reference_images == {}


def test_the_client_itself_refuses_without_the_record(demo_marina):
    from app.services.pedestal_api_factory import get_pedestal_factory
    mid, transport, _ = demo_marina
    cab = _cab(mid, "SIM_C_06")
    before = len(transport.urls)
    db = TestSession()
    try:
        out = asyncio.run(get_pedestal_factory().for_cabinet(cab).push_reference_image(
            cab, 1, b"\xff\xd8\xff\xd9", db))
    finally:
        db.close()
    assert out.code == "erp_bug" and transport.urls[before:] == []


# ─── the upload ──────────────────────────────────────────────────────────────

def test_the_upload_needs_an_admin_a_reason_and_the_no_people_confirmation(
        client, admin_headers, manager_headers, demo_marina):
    mid, transport, _ = demo_marina
    cab = _cab(mid, "SIM_C_04")
    assert _record(client, admin_headers, mid, cab).status_code == 200
    berth = _berth_of(cab)
    before = len(transport.urls)
    assert _upload(client, manager_headers, mid, berth).status_code == 403
    assert _upload(client, admin_headers, mid, berth, reason="x").status_code == 422
    r = _upload(client, admin_headers, mid, berth, people="false")
    assert r.status_code == 422 and r.json()["detail"]["code"] == "people_not_confirmed"
    assert transport.urls[before:] == []


def test_the_clean_jpeg_reaches_the_cabinet_and_only_its_hash_is_kept(
        client, admin_headers, demo_marina):
    mid, transport, world = demo_marina
    cab = _cab(mid, "SIM_C_04")
    berth = _berth_of(cab)
    r = _upload(client, admin_headers, mid, berth)
    assert r.status_code == 200, r.text
    body = r.json()
    got = world.states["SIM_C_04"].reference_images[berth.cabinet_berth_id]
    assert len(got) == 1 and b"SecretCam" not in got[0]
    assert hashlib.sha256(got[0]).hexdigest() == body["sha256"]
    with Image.open(io.BytesIO(got[0])) as img:
        assert len(img.getexif()) == 0
    db = TestSession()
    try:
        row = db.query(VesselPhoto).filter(VesselPhoto.berth_id == berth.id).one()
        assert (row.sha256, row.outcome, row.size_bytes) == (body["sha256"], "ok", len(got[0]))
        audit = (db.query(CommandAudit).filter(CommandAudit.cabinet_id == cab.id,
                                               CommandAudit.endpoint_key == "berths.push_image_ext")
                 .one())
        assert audit.outcome == "ok" and audit.reason == "new season photo"
        assert audit.request_url.endswith(f"/berths/{berth.cabinet_berth_id}/reference-image")
    finally:
        db.close()
    detail = client.get(f"/api/marinas/{mid}/berths/{berth.id}/detail", headers=admin_headers).json()
    up = detail["functions"][0]
    assert up["key"] == "reference_upload" and up["available"] is True and up["sentence"] is None
    assert detail["reference"]["photos"][0]["sha256"] == body["sha256"]
    assert "path" not in detail["reference"]["photos"][0]


def test_the_cabinets_503_switches_the_record_off(client, admin_headers, demo_marina):
    mid, transport, world = demo_marina
    cab = _cab(mid, "SIM_C_05")
    assert _record(client, admin_headers, mid, cab).status_code == 200
    world.states["SIM_C_05"].enabled.pop("berths.push_image_ext")    # gateway: not enabled
    berth = _berth_of(cab)
    r = _upload(client, admin_headers, mid, berth)
    assert r.status_code == 503
    db = TestSession()
    try:
        rec = photo.record(db, cab)
        assert rec.available is False and "503" in rec.note
        assert db.query(VesselPhoto).filter(VesselPhoto.berth_id == berth.id).one().outcome \
            == "not_enabled"
    finally:
        db.close()
    up = client.get(f"/api/marinas/{mid}/berths/{berth.id}/detail",
                    headers=admin_headers).json()["functions"][0]
    assert up["available"] is False and "Switched off" in up["sentence"]
    before = len(transport.urls)
    assert _upload(client, admin_headers, mid, berth).status_code == 409   # and no second try
    assert transport.urls[before:] == []


def test_an_offline_cabinet_gets_no_photo(client, admin_headers, demo_marina):
    mid, transport, _ = demo_marina
    cab = _cab(mid, "SIM_C_07")
    assert _record(client, admin_headers, mid, cab).status_code == 200
    db = TestSession()
    try:
        db.get(Cabinet, cab.id).last_heartbeat_at = NOW - timedelta(hours=1)
        db.commit()
    finally:
        db.close()
    before = len(transport.urls)
    r = _upload(client, admin_headers, mid, _berth_of(cab))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "not_controllable"
    assert transport.urls[before:] == []
