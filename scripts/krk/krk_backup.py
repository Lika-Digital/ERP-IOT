"""1 · Online, consistent copy of both cabinet databases (SQLite backup API, not cp).

    sudo install -d -o cloud-iot -g cloud-iot -m 700 /var/backups/cloud-iot-erp
    sudo -u cloud-iot /opt/cloud-iot/backend/.venv/bin/python /tmp/krk/krk_backup.py \
         --out /var/backups/cloud-iot-erp

The backend keeps running. The backup API copies the database AS SQLITE SEES IT,
WAL content included, while cp would copy the main file without its -wal. Each
copy is then switched to journal_mode=DELETE so it is ONE self-contained file
(restore = that file, and nothing else).

Changes nothing on the live databases. Prints the current external_api_config
row (allowed_endpoints, webhook_url, allowed_events, active) — the api_key only
as "set / not set".
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from krk_common import PEDESTAL_DB, USERS_DB, die, require_service_user  # noqa: E402


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def backup(src: Path, dst: Path) -> dict:
    if dst.exists():
        die(f"{dst} već postoji — ne prepisujem")
    st = src.stat()
    s = sqlite3.connect(str(src), timeout=30)
    d = sqlite3.connect(str(dst))
    try:
        s.backup(d)                                   # online, consistent, WAL included
        d.execute("PRAGMA journal_mode=DELETE")       # the copy is one file
        ok = d.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        d.close()
        s.close()
    os.chmod(dst, 0o600)                              # holds password hashes
    if ok != "ok":
        die(f"integrity_check kopije {dst}: {ok}")
    return {"src": str(src), "copy": str(dst), "bytes": dst.stat().st_size,
            "sha256": sha256(dst), "integrity": ok,
            "orig_owner_uid": st.st_uid, "orig_group_gid": st.st_gid,
            "orig_mode": oct(stat.S_IMODE(st.st_mode))}


def show_config(copy: Path) -> dict:
    con = sqlite3.connect(f"file:{copy}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        r = con.execute("SELECT * FROM external_api_config WHERE id=1").fetchone()
    finally:
        con.close()
    if r is None:
        return {"row": None}
    return {
        "allowed_endpoints": json.loads(r["allowed_endpoints"] or "[]"),
        "webhook_url": r["webhook_url"],
        "allowed_events": json.loads(r["allowed_events"] or "[]"),
        "active": r["active"],
        "verified": r["verified"],
        "updated_at": r["updated_at"],
        "api_key": "set" if r["api_key"] else "not set",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    require_service_user()
    os.umask(0o077)
    out = Path(a.out)
    if not out.is_dir():
        die(f"{out} ne postoji — napravi ga (sudo install -d -o cloud-iot -g cloud-iot -m 700 {out})")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    res = [backup(PEDESTAL_DB, out / f"pedestal-{stamp}.db"),
           backup(USERS_DB, out / f"users-{stamp}.db")]
    manifest = out / f"manifest-{stamp}.json"
    cfg = show_config(Path(res[0]["copy"]))
    manifest.write_text(json.dumps({"stamp": stamp, "copies": res,
                                    "external_api_config": cfg}, indent=2))
    os.chmod(manifest, 0o600)

    print(f"KOPIJA {stamp}")
    for r in res:
        print(f"  {r['src']}\n    -> {r['copy']}  {r['bytes']} B  integrity={r['integrity']}"
              f"  sha256={r['sha256'][:16]}…  (orig {r['orig_mode']} uid={r['orig_owner_uid']})")
    print(f"  manifest: {manifest}")
    print("\nexternal_api_config (sada):")
    if cfg.get("row", 1) is None:
        print("  NEMA REDA id=1")
        return
    print(f"  active         = {cfg['active']}")
    print(f"  webhook_url    = {cfg['webhook_url']!r}")
    print(f"  allowed_events = {cfg['allowed_events']}")
    print(f"  verified       = {cfg['verified']}   updated_at = {cfg['updated_at']}")
    print(f"  api_key        = {cfg['api_key']}")
    print(f"  allowed_endpoints ({len(cfg['allowed_endpoints'])}):")
    for e in cfg["allowed_endpoints"]:
        print(f"    {e.get('id'):32s} {e.get('mode')}")


if __name__ == "__main__":
    main()
