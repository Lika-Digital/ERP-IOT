"""The demo marina locally (D28, spec §6.11) — start, stop, status, scenarios.

    python scripts/demo.py start        # the simulator, in the background, on 127.0.0.1:18080
    python scripts/demo.py stop         # one command, and it is gone
    python scripts/demo.py status
    python scripts/demo.py seed         # the demo marina in the ERP's database (once)
    python scripts/demo.py remove       # ... and out again
    python scripts/demo.py scenario offline SIM_C_04

On the VPS the simulator is the systemd unit deploy/erp-sim.service instead.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
PY = BACKEND / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
PIDFILE = BACKEND / ".demo-sim.pid"
PORT = int(os.environ.get("DEMO_SIM_PORT", 18080))


def _alive() -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/__demo/state", timeout=2):  # noqa: S310
            return True
    except Exception:  # noqa: BLE001
        return False


def start() -> int:
    if _alive():
        print(f"already running on 127.0.0.1:{PORT}")
        return 0
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    log = open(BACKEND / ".demo-sim.log", "a", encoding="utf-8")  # noqa: SIM115 — the child keeps it
    p = subprocess.Popen([str(PY), "-m", "simulator.demo_sim", "--port", str(PORT), "serve"],
                         cwd=BACKEND, stdout=log, stderr=subprocess.STDOUT, creationflags=flags,
                         start_new_session=os.name != "nt")
    PIDFILE.write_text(str(p.pid))
    for _ in range(60):
        if _alive():
            print(f"demo simulator on 127.0.0.1:{PORT} (pid {p.pid})")
            return 0
        time.sleep(0.5)
    print("the simulator did not come up — see backend/.demo-sim.log", file=sys.stderr)
    return 1


def stop() -> int:
    if not PIDFILE.exists():
        print("not running" if not _alive() else "running, but not started here (no pid file)")
        return 0
    pid = int(PIDFILE.read_text())
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        else:
            os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    PIDFILE.unlink(missing_ok=True)
    print("stopped")
    return 0


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "status"
    if cmd == "start":
        return start()
    if cmd == "stop":
        return stop()
    if cmd in ("seed", "remove"):
        return subprocess.call([str(PY), "-m", "app.demo", cmd, *argv[1:]], cwd=BACKEND)
    if cmd in ("status", "scenario"):
        if not _alive():
            print("not running")
            return 1
        return subprocess.call([str(PY), "-m", "simulator.demo_sim", "--port", str(PORT),
                                "state" if cmd == "status" else "scenario", *argv[1:]], cwd=BACKEND)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
