"""TC-ERP-BOOT-01b — the screens render, in a real browser, against the simulator.

Three real processes and a real browser:
  - the cabinet simulator (backend/simulator/cabinet_sim.py) on its own port,
  - the ERP backend after a real migration, pointed at the simulator,
  - the real production bundle (frontend/dist) behind a small proxy that does
    for /api and /ws what nginx does in production,
  - Chromium through Playwright.

First the D20 sign-in in the browser: the one-time link sets the password, the QR
step links 2FA with a real TOTP code, the backup codes are shown once; then a
fresh sign-in with password + backup code.

Then the DOM checks the spec asks to be made in the DOM, not in JSON:
  SIM-01 full cabinet: outlets and controls present
  SIM-06 Smart Mode OFF: readings rendered, ZERO control elements
  SIM-02 retrofit: no water element anywhere
  SIM-05 silent cabinet: every berth grey
  SIM-07 no plug: the cabinet's sentence is shown, no error page
  D21    a decoy touch -> one agent pass -> the alarm on the Security screen, its
         evidence (markup in a User-Agent) shown as text; the Admin acknowledges
  UI     at 360 px wide, in the light and the dark theme, sign-in, the 2FA step,
         berths and Security have no page-level horizontal scroll (TC-UIR-04); the
         theme switch flips the theme and remembers it.
         With SCREENSHOT_DIR set, the same screens are saved as PNGs (desktop and
         360 px, both themes) for a design review.

Like boot_check.py it cannot pass empty: every check is counted and the exit
code is 0 only when all of them ran and passed. A page error or console error
anywhere fails it.

Usage:  backend/.venv/Scripts/python.exe scripts/browser_check.py
Needs:  frontend/dist (the gate builds it first), Chromium for Playwright.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from boot_check import BACKEND, ROOT, free_port, http  # noqa: E402

DIST = ROOT / "frontend" / "dist"
ADMIN_EMAIL = "browser@check.erp"
ADMIN_PASSWORD = "browser-check-password"  # noqa: S105 — throwaway, temp DB only
SIM_EMAIL, SIM_PASSWORD = "erp@sim.local", "sim-password"  # noqa: S105

EXPECTED = [
    "sim: cabinet simulator comes up",
    "erp: migration + backend come up",
    "spa: the real bundle is served",
    "D20: one-time link in the browser - password, QR, code, backup codes once",
    "D20: sign-in in the browser - password, then a backup code",
    "D20: Users screen - the admin is listed with 2FA linked",
    "erp: marina pointed at the simulator",
    "BOOT-01b: /marinas/:id/berths renders berth rows from the simulator",
    "SIM-01: full cabinet - outlets and controls in the DOM",
    "SIM-06: Smart Mode OFF - readings shown, zero controls in the DOM",
    "SIM-02: retrofit - no water element anywhere",
    "SIM-05: silent cabinet - every berth grey",
    "SIM-07: no plug - the cabinet's sentence is shown",
    "D21: Security screen - decoy touch -> agent -> alarm, evidence shown as text, Admin decides",
    "UI: sign-in, 2FA, berths, Security fit 360 px without horizontal scroll, light and dark; theme switch",
    "BOOT-01b: no page errors and no console errors in any scenario",
]
_passed: list[str] = []


def ok(i: int) -> None:
    _passed.append(EXPECTED[i])
    print(f"  [ok]   {EXPECTED[i]}", flush=True)


def fail(i: int, detail: str) -> None:
    print(f"  [FAIL] {EXPECTED[i]}\n         {detail}", flush=True)
    from boot_check import _annotate
    _annotate(EXPECTED[i], detail)
    summary()
    raise SystemExit(1)


def summary() -> None:
    print(f"\n  BROWSER: {len(_passed)}/{len(EXPECTED)} checks passed", flush=True)
    for c in EXPECTED:
        if c not in _passed:
            print(f"         not passed: {c}", flush=True)


def wait_port(port: int, proc: subprocess.Popen, what: str, timeout=40) -> bool:
    import socket
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if proc is not None and proc.poll() is not None:
            return False
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def spa_app(backend: str):
    """What nginx does in production: static bundle, /api and /ws to the backend."""
    import httpx
    import websockets
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import FileResponse, Response
    from starlette.routing import Mount, Route, WebSocketRoute
    from starlette.staticfiles import StaticFiles
    from starlette.websockets import WebSocket

    async def api(request: Request):
        async with httpx.AsyncClient(base_url=backend, timeout=30) as c:
            r = await c.request(request.method, request.url.path,
                                params=request.query_params, content=await request.body(),
                                headers={k: v for k, v in request.headers.items()
                                         if k.lower() not in ("host", "content-length")})
        return Response(r.content, r.status_code, media_type=r.headers.get("content-type"))

    async def ws(socket: WebSocket):
        await socket.accept()
        url = backend.replace("http", "ws") + "/ws?" + socket.url.query
        import asyncio
        try:
            async with websockets.connect(url) as upstream:
                async def up():
                    while True:
                        await upstream.send(await socket.receive_text())

                async def down():
                    async for msg in upstream:
                        await socket.send_text(msg)
                await asyncio.gather(up(), down())
        except Exception:  # noqa: BLE001 — either side closing ends the bridge
            pass

    async def index(request: Request):
        # nginx: try_files $uri /index.html — a real file in dist/ (favicon,
        # theme-init.js) is served as itself, every other path gets the SPA
        f = (DIST / request.path_params["path"]).resolve()
        if request.path_params["path"] and f.is_file() and DIST.resolve() in f.parents:
            return FileResponse(f)
        return FileResponse(DIST / "index.html")

    return Starlette(routes=[
        Route("/api/{path:path}", api, methods=["GET", "POST", "PATCH", "PUT", "DELETE"]),
        WebSocketRoute("/ws", ws),
        Mount("/assets", StaticFiles(directory=DIST / "assets")),
        Route("/{path:path}", index),
    ])


def serve_in_thread(app, port: int):
    import uvicorn
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    return server


def main() -> int:
    print("TC-ERP-BOOT-01b - screens render in a real browser\n", flush=True)
    if not (DIST / "index.html").is_file():
        fail(2, "frontend/dist missing - build it first (the gate does)")

    procs: list[subprocess.Popen] = []
    tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    t = Path(tmp.name)
    try:
        # ── simulator ──────────────────────────────────────────────────────
        sim_port = free_port()
        sim_url = f"http://127.0.0.1:{sim_port}"
        env = {**os.environ, "PYTHONPATH": str(BACKEND)}
        procs.append(subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "simulator.cabinet_sim:app", "--host", "127.0.0.1",
             "--port", str(sim_port), "--log-level", "warning"],
            cwd=str(BACKEND), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT))
        if not wait_port(sim_port, procs[-1], "sim"):
            fail(0, "simulator did not come up")
        ok(0)

        # ── ERP backend, real migration ────────────────────────────────────
        db_url = f"sqlite:///{t / 'browser.db'}"
        erp_env = {k: v for k, v in os.environ.items()
                   if k not in ("JWT_SECRET", "DATABASE_URL", "DEFAULT_ADMIN_PASSWORD")}
        erp_env.update({
            "PYTHONPATH": str(BACKEND), "DATABASE_URL": db_url,
            "JWT_SECRET": "browser-check-" + os.urandom(8).hex(),
            "ERP_ENCRYPTION_KEY": "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg=",
        })
        r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                           cwd=str(BACKEND), env=erp_env, capture_output=True, text=True)
        if r.returncode != 0:
            fail(1, r.stderr[-1500:])
        erp_port = free_port()
        erp_url = f"http://127.0.0.1:{erp_port}"
        log = open(t / "erp.log", "w", encoding="utf-8")
        procs.append(subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
             "--port", str(erp_port), "--log-level", "warning"],
            cwd=tmp.name, env=erp_env, stdout=log, stderr=subprocess.STDOUT))
        if not wait_port(erp_port, procs[-1], "erp"):
            log.flush()
            fail(1, (t / "erp.log").read_text(encoding="utf-8")[-1500:])
        ok(1)

        import first_admin
        link = first_admin.link_token(erp_env, ADMIN_EMAIL, cwd=tmp.name)
        token = None   # the full token comes from the browser, after 2FA

        # ── the real bundle ────────────────────────────────────────────────
        spa_port = free_port()
        spa_url = f"http://127.0.0.1:{spa_port}"
        server = serve_in_thread(spa_app(erp_url), spa_port)
        if not wait_port(spa_port, None, "spa"):
            fail(2, "spa proxy did not come up")
        code, body = http("GET", spa_url + "/")
        if code != 200 or "<div id=\"root\"" not in body:
            fail(2, f"{code} {body[:200]}")
        ok(2)

        # ── browser ────────────────────────────────────────────────────────
        from playwright.sync_api import sync_playwright

        problems: list[str] = []
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
            # A refused command answers 409 on purpose (SIM-07); the browser logs
            # every non-2xx as "Failed to load resource". That is the network,
            # not the app — anything else on the console is a failure.
            page.on("console", lambda m: m.type == "error"
                    and "Failed to load resource" not in m.text
                    and problems.append(f"console: {m.text}"))

            # ── D20: the one-time link, in the browser ──────────────────────
            page.goto(f"{spa_url}/setup#token={link}")
            try:
                page.wait_for_selector("[data-setup-email]", timeout=15000)
                if page.inner_text("[data-setup-email]") != ADMIN_EMAIL:
                    fail(3, "the link page shows the wrong account")
                page.fill("#new-password", ADMIN_PASSWORD)
                page.fill("#repeat-password", ADMIN_PASSWORD)
                page.click("button[type=submit]")
                page.wait_for_selector("[data-totp-secret]", timeout=15000)
                if page.locator("img[alt^='QR code']").count() != 1:
                    fail(3, "no QR code on the linking step")
                secret = page.inner_text("[data-totp-secret]").strip()
                page.fill("#code", first_admin.code_now(secret))
                page.click("button[type=submit]")
                page.wait_for_selector("[data-backup-code]", timeout=15000)
                codes = page.locator("[data-backup-code]").all_inner_texts()
                if len(codes) != 10:
                    fail(3, f"expected 10 backup codes, got {len(codes)}")
                page.check("input[type=checkbox]")
                page.click("button:has-text('Continue')")
                page.wait_for_url("**/marinas", timeout=15000)
            except SystemExit:
                raise
            except Exception as exc:  # noqa: BLE001
                fail(3, f"{type(exc).__name__}: {exc}")
            if "#token" in page.url or link in page.url:
                fail(3, "the used link is still in the address bar")
            ok(3)

            # ── D20: sign out, sign in again with password + backup code ─────
            page.click("button:has-text('Sign out')")
            page.wait_for_url("**/login", timeout=15000)
            page.fill("input[type=email]", ADMIN_EMAIL)
            page.fill("input[type=password]", ADMIN_PASSWORD)
            page.click("button[type=submit]")
            try:
                page.wait_for_selector("[data-step='mfa-code']", timeout=15000)
                page.fill("#code", "000000")              # wrong first: the answer is shown
                page.click("button[type=submit]")
                page.wait_for_selector("[data-error]", timeout=15000)
                if "/login" not in page.url:
                    fail(4, "a wrong code threw the user out of the sign-in page")
                page.fill("#code", codes[0])
                page.click("button[type=submit]")
                page.wait_for_url("**/marinas", timeout=15000)
            except SystemExit:
                raise
            except Exception as exc:  # noqa: BLE001
                fail(4, f"{type(exc).__name__}: {exc}")
            ok(4)
            token = page.evaluate(
                "() => JSON.parse(localStorage.getItem('erp-iot-auth')).state.token")

            page.goto(f"{spa_url}/users")
            try:
                page.wait_for_selector(f"[data-user='{ADMIN_EMAIL}']", timeout=15000)
            except Exception as exc:  # noqa: BLE001
                fail(5, f"Users screen: {exc}")
            if "linked" not in page.inner_text(f"[data-user='{ADMIN_EMAIL}']"):
                fail(5, "the admin's 2FA is not shown as linked")
            ok(5)

            # ── provisioning through the phase-3 admin API, with the browser's token ──
            def marina(name, device_type, mapping):
                """A marina on the simulator, provisioned through the phase-3 admin API:
                cabinet, one ERP berth per cabinet berth, and the berth -> outlet mapping."""
                code, body = http("POST", f"{erp_url}/api/marinas", {
                    "name": name, "pedestal_api_base_url": sim_url,
                    "pedestal_service_email": SIM_EMAIL, "pedestal_service_password": SIM_PASSWORD,
                }, token=token)
                if code not in (200, 201):
                    fail(6, f"marina: {code} {body[:300]}")
                mid = json.loads(body)["id"]
                code, body = http("POST", f"{erp_url}/api/marinas/{mid}/cabinets", {
                    "pedestal_pk": 1, "display_id": "MAR_KRK_ORM_01", "device_type": device_type,
                }, token=token)
                if code != 201:
                    fail(6, f"cabinet: {code} {body[:300]}")
                cab_id = json.loads(body)["id"]
                for cab_berth, outlets in mapping.items():
                    code, body = http("POST", f"{erp_url}/api/marinas/{mid}/berth-registry", {
                        "berth_number": f"A-{cab_berth:02d}", "cabinet_id": cab_id,
                        "cabinet_berth_id": cab_berth}, token=token)
                    if code != 201:
                        fail(6, f"berth: {code} {body[:300]}")
                    bid = json.loads(body)["id"]
                    code, body = http("PUT", f"{erp_url}/api/marinas/{mid}/berth-registry/{bid}/outlets",
                                      {"outlets": outlets}, token=token)
                    if code != 200:
                        fail(6, f"mapping: {code} {body[:300]}")
                return mid

            def profile(name):
                http("POST", f"{sim_url}/__sim/profile/{name}")

            marina_id = marina("Krk (sim)", "full", {1: ["Q1"], 2: ["Q2"], 3: ["Q3", "V1"], 4: ["Q4", "V1"]})
            retrofit_id = marina("Retrofit (sim)", "retrofit", {1: ["Q1"], 2: ["Q2"], 3: ["Q3"], 4: ["Q4"]})
            ok(6)

            def load(mid=None):
                page.goto(f"{spa_url}/marinas/{mid or marina_id}/berths")
                page.wait_for_selector("[data-berth]", timeout=15000)

            try:
                load()
            except Exception as exc:  # noqa: BLE001
                fail(7, f"no berth rows: {exc}")
            n = page.locator("[data-berth]").count()
            if n != 4:
                fail(7, f"expected 4 berth rows from the simulator, got {n}")
            ok(7)

            if page.locator("[data-outlet]").count() < 5 or page.locator("[data-control]").count() == 0:
                fail(8, "full cabinet: outlets or controls missing")
            ok(8)

            profile("smart_off")
            http("PATCH", f"{sim_url}/__sim/credentials", {"email": SIM_EMAIL, "password": SIM_PASSWORD})
            load()
            if page.locator("[data-outlet]").count() == 0:
                fail(9, "Smart Mode OFF: readings must still render")
            if page.locator("[data-control]").count() != 0 or page.locator("button:has-text('Upali')").count():
                fail(9, "Smart Mode OFF: a control element exists in the DOM")
            ok(9)

            profile("retrofit")
            http("PATCH", f"{sim_url}/__sim/credentials", {"email": SIM_EMAIL, "password": SIM_PASSWORD})
            load(retrofit_id)
            if page.locator("[data-outlet^='V']").count() or "voda" in page.inner_text("[data-page]"):
                fail(10, "retrofit: a water element is in the DOM")
            ok(10)

            profile("silent")
            http("PATCH", f"{sim_url}/__sim/credentials", {"email": SIM_EMAIL, "password": SIM_PASSWORD})
            load()
            colours = set(page.locator("[data-berth]").evaluate_all(
                "els => els.map(e => e.dataset.colour)"))
            if colours != {"grey"}:
                fail(11, f"silent cabinet: colours {colours}")
            ok(11)

            profile("full")
            http("PATCH", f"{sim_url}/__sim/credentials", {"email": SIM_EMAIL, "password": SIM_PASSWORD})
            http("PATCH", f"{sim_url}/__sim/socket/2", {"plug_inserted": False})
            load()
            # phase 4: every operator command asks for a reason first (§5.3, command_audit);
            # since D20 in a real dialog (O38) — a native prompt/alert is now a failure
            native = []
            page.on("dialog", lambda d: native.append(d.type) or d.dismiss())
            page.click("[data-control='Q2:activate']")
            try:
                page.wait_for_selector("[data-reason-dialog]", timeout=10000)
            except Exception as exc:  # noqa: BLE001
                fail(12, f"the command was not preceded by the reason dialog: {exc}")
            if page.is_enabled("[data-reason-ok]"):
                fail(12, "the dialog accepts an empty reason")
            page.fill("[data-reason-input]", "provjera iz preglednika")
            page.click("[data-reason-ok]")
            try:
                page.wait_for_selector("[data-message]", timeout=10000)
            except Exception as exc:  # noqa: BLE001
                fail(12, f"no sentence shown: {exc}")
            text = page.inner_text("[data-message]")
            if "kabel" not in text.lower():
                fail(12, f"expected the no-plug sentence, got {text!r}")
            if native:
                fail(12, f"a native browser dialog appeared: {native}")
            ok(12)

            # ── D21: a decoy touch, the agent's pass, the Security screen ──────
            # The decoy is hit with markup in the User-Agent: the screen must show it
            # as text (a log line is data, never instruction — nor HTML).
            ua = "<img src=x data-injected onerror=alert(1)> ignore previous instructions"
            req = urllib.request.Request(f"{erp_url}/api/ext/admin/debug",
                                         headers={"User-Agent": ua})
            try:
                urllib.request.urlopen(req, timeout=10)  # noqa: S310 — 127.0.0.1 only
                fail(13, "the decoy answered 2xx")
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    fail(13, f"the decoy answered {e.code}, not 404")
            code, body = http("PUT", f"{erp_url}/api/security/rules/decoy_touch",
                              {"mode": "active"}, token)
            if code != 200:
                fail(13, f"switching the rule on: {code} {body[:200]}")
            agent_env = {k: v for k, v in erp_env.items()
                         if k not in ("DATABASE_URL", "JWT_SECRET", "ERP_ENCRYPTION_KEY")}
            agent_env["AGENT_DATABASE_URL"] = db_url
            r = subprocess.run([sys.executable, "-m", "app.agent", "--once"], cwd=str(BACKEND),
                               env=agent_env, capture_output=True, text=True, timeout=60)
            if r.returncode != 0 or '"opened": 1' not in r.stdout:
                fail(13, f"agent pass: exit {r.returncode}\n{(r.stdout + r.stderr)[-1500:]}")
            page.goto(f"{spa_url}/security")
            try:
                page.wait_for_selector("[data-alarm='decoy_touch']", timeout=15000)
            except Exception as exc:  # noqa: BLE001
                fail(13, f"no decoy alarm on the Security screen: {exc}")
            alarm = page.locator("[data-alarm='decoy_touch']")
            if page.locator("[data-injected]").count() != 0:
                fail(13, "markup from the User-Agent was rendered as an element")
            if "<img src=x data-injected" not in alarm.inner_text():
                fail(13, "the User-Agent is not shown, as text, in the evidence")
            alarm.locator("button:has-text('Acknowledge')").click()
            page.wait_for_selector("[data-reason-dialog]", timeout=10000)
            page.fill("[data-reason-input]", "provjera iz preglednika")
            page.click("[data-reason-ok]")
            try:
                page.wait_for_selector("[data-alarm='decoy_touch'] >> text=acknowledged",
                                       timeout=10000)
            except Exception as exc:  # noqa: BLE001
                fail(13, f"the decision did not show: {exc}")
            ok(13)

            # ── UI: 360 px, light and dark, and the theme switch ──────────────
            shots = os.environ.get("SCREENSHOT_DIR")
            shot_dir = Path(shots) if shots else None
            if shot_dir:
                shot_dir.mkdir(parents=True, exist_ok=True)
                # an open alarm next to the acknowledged one, for the review only
                try:
                    urllib.request.urlopen(urllib.request.Request(  # noqa: S310 — 127.0.0.1 only
                        f"{erp_url}/api/ext/admin/debug", headers={"User-Agent": "curl/8.5"}), timeout=10)
                except urllib.error.HTTPError:
                    pass
                subprocess.run([sys.executable, "-m", "app.agent", "--once"], cwd=str(BACKEND),
                               env=agent_env, capture_output=True, text=True, timeout=60)
            signed_in = page.context.storage_state()
            wide: list[str] = []

            def watch(pg):
                pg.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
                pg.on("console", lambda m: m.type == "error"
                      and "Failed to load resource" not in m.text
                      and problems.append(f"console: {m.text}"))

            def visit(scheme, size, name, pg, ready):
                pg.wait_for_selector(ready, timeout=15000)
                pg.wait_for_timeout(150)
                if size == "mobile":
                    w = pg.evaluate("() => [document.documentElement.scrollWidth, window.innerWidth]")
                    if w[0] > w[1]:
                        wide.append(f"{name} ({scheme}): {w[0]} px in a {w[1]} px window")
                if shot_dir:
                    # the app scrolls inside <main>: grow the window to the content for the picture
                    h = pg.evaluate("() => Math.max(document.documentElement.scrollHeight,"
                                    " document.querySelector('main')?.scrollHeight ?? 0)")
                    vp = pg.viewport_size
                    pg.set_viewport_size({"width": vp["width"], "height": max(vp["height"], h + 60)})
                    pg.screenshot(path=str(shot_dir / f"{name}-{scheme}-{size}.png"), full_page=True)
                    pg.set_viewport_size(vp)

            for scheme in ("light", "dark"):
                for size, vp in (("mobile", {"width": 360, "height": 780}),
                                 ("desktop", {"width": 1280, "height": 860})):
                    if size == "desktop" and not shot_dir:
                        continue
                    anon = browser.new_context(color_scheme=scheme, viewport=vp)
                    pg = anon.new_page()
                    watch(pg)
                    pg.goto(f"{spa_url}/login")
                    visit(scheme, size, "1-login", pg, "input[type=email]")
                    pg.fill("input[type=email]", ADMIN_EMAIL)
                    pg.fill("input[type=password]", ADMIN_PASSWORD)
                    pg.click("button[type=submit]")
                    visit(scheme, size, "2-login-2fa", pg, "[data-step='mfa-code']")
                    anon.close()

                    ctx = browser.new_context(color_scheme=scheme, viewport=vp, storage_state=signed_in)
                    pg = ctx.new_page()
                    watch(pg)
                    pg.goto(f"{spa_url}/marinas/{marina_id}/berths")
                    visit(scheme, size, "3-berths", pg, "[data-berth]")
                    pg.goto(f"{spa_url}/security")
                    visit(scheme, size, "4-security", pg, "[data-alarm]")
                    theme = pg.evaluate("() => document.documentElement.className")
                    if scheme not in theme:
                        wide.append(f"system {scheme} preference not applied: <html class={theme!r}>")
                    ctx.close()

            # the switch flips the theme and remembers it across a reload
            ctx = browser.new_context(color_scheme="light", storage_state=signed_in)
            pg = ctx.new_page()
            watch(pg)
            pg.goto(f"{spa_url}/security")
            pg.wait_for_selector("[data-theme-toggle]", timeout=15000)
            pg.click("[data-theme-toggle]")
            pg.reload()
            pg.wait_for_selector("[data-theme-toggle]", timeout=15000)
            if "dark" not in pg.evaluate("() => document.documentElement.className"):
                wide.append("the theme switch did not flip to dark, or did not remember it")
            ctx.close()
            if wide:
                fail(14, "\n         ".join(wide))
            ok(14)

            browser.close()

        if problems:
            fail(15, "\n         ".join(problems[:10]))
        ok(15)
        server.should_exit = True
    except Exception as exc:  # noqa: BLE001 — a step that blew up: say which, with the ERP's log
        erp_log = t / "erp.log"
        tail = (erp_log.read_text(encoding="utf-8", errors="replace")[-3000:]
                if erp_log.exists() else "(no erp.log)")
        fail(min(len(_passed), len(EXPECTED) - 1),
             f"{type(exc).__name__}: {str(exc)[:500]}\n--- erp.log (tail) ---\n{tail}")
    finally:
        for p in procs:
            p.terminate()
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
        tmp.cleanup()

    summary()
    return 0 if _passed == EXPECTED else 1


if __name__ == "__main__":
    sys.exit(main())
