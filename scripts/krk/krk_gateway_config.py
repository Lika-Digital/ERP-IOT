"""3 · Gateway configuration for the ERP read-only test: diff, and change ONLY with --apply.

    # diff only
    sudo -u cloud-iot /opt/cloud-iot/backend/.venv/bin/python /tmp/krk/krk_gateway_config.py

    # apply
    sudo -u cloud-iot /opt/cloud-iot/backend/.venv/bin/python /tmp/krk/krk_gateway_config.py \
         --apply --backup /var/backups/cloud-iot-erp/pedestal-<stamp>.db

Target: the 17 endpoints below, all "monitor". Removed without asking: camera.*,
breakers.socket_reset_ext, load.auto_stop_ack_ext, berths.push_image_ext (your
list). ANY OTHER endpoint enabled today is not touched by default — it is
listed as "ČEKA ODLUKU" and --apply refuses until you decide each one:
    --keep ID           keep as it is (refused if it is bidirectional)
    --keep-monitor ID   keep, but as monitor
    --drop ID           remove
webhook_url, allowed_events: written back unchanged. active must be 1 now and is 1 after.

Written through the cabinet's own handlers (routers/external_api_admin.py,
aa1f74f): update_config (its validation: unknown id -> refused, bidirectional
on a read-only endpoint -> refused) then activate_config, because update_config
deliberately sets active=0 after any change (:176). Between the two commits —
milliseconds — the gateway answers 403 "not active". update_config also sets
verified=0: that is the app's own rule for any change; the flag gates nothing
(only the admin screen shows it). "Verify" is NOT run (it writes
verification_results, and it is broken — D17 finding).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from krk_common import (assert_app_points_at_live_dbs, die, enter_backend,  # noqa: E402
                        require_backup, require_service_user)

TARGET = [
    "pedestals.health", "pedestals.list", "pedestals.status_ext", "berths.list",
    "sessions.active", "sessions.pending", "alarms.active",
    "load.pedestal_get_ext", "load.socket_get_ext", "load.pedestal_alarms_ext",
    "breakers.pedestal_list_ext", "breakers.socket_get_ext", "water.status_ext",
    "sockets.config_list", "valves.config_list", "analytics.daily", "analytics.summary",
]
FORBIDDEN_EXACT = {"breakers.socket_reset_ext", "load.auto_stop_ack_ext", "berths.push_image_ext"}


def forbidden(eid: str) -> bool:
    return eid.startswith("camera.") or eid in FORBIDDEN_EXACT


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--backup")
    ap.add_argument("--keep", action="append", default=[])
    ap.add_argument("--keep-monitor", action="append", default=[])
    ap.add_argument("--drop", action="append", default=[])
    a = ap.parse_args()
    require_service_user()
    enter_backend()

    from app.database import SessionLocal, import_all_models
    import_all_models()
    assert_app_points_at_live_dbs()
    from app.models.external_api import ExternalApiConfig
    from app.routers.external_api_admin import (EndpointEntry, UpdateConfigRequest,
                                                activate_config, update_config)
    from app.services.api_catalog import ENDPOINT_CATALOG

    catalog = {e["id"]: e for e in ENDPOINT_CATALOG}
    missing = [t for t in TARGET if t not in catalog]
    if missing:
        die(f"ovi ključevi ne postoje u katalogu ove verzije: {missing}")
    if len(TARGET) != 17 or len(set(TARGET)) != 17:
        die("popis cilja nije 17 različitih ključeva")
    if any(catalog[t].get("allow_bidirectional") for t in TARGET):
        die("netko od 17 je u katalogu dvosmjeran — ne očekujem to, stani")

    decided = {**{i: "keep" for i in a.keep}, **{i: "keep-monitor" for i in a.keep_monitor},
               **{i: "drop" for i in a.drop}}
    if len(decided) != len(a.keep) + len(a.keep_monitor) + len(a.drop):
        die("isti ključ u više odluka")

    db = SessionLocal()
    try:
        cfg = db.get(ExternalApiConfig, 1)
        if cfg is None:
            die("nema reda external_api_config id=1 — ne stvaram ga; javi")
        cur_list = json.loads(cfg.allowed_endpoints or "[]")
        cur = {e["id"]: e.get("mode") for e in cur_list}
        events = json.loads(cfg.allowed_events or "[]")
        hook = cfg.webhook_url

        blockers = []
        if hook:
            blockers.append(f"webhook_url nije prazan ({hook!r}) — cilj kaže da ostaje prazan; "
                            "ne diram ga, odluči")
        if cfg.active != 1:
            blockers.append(f"active = {cfg.active}, cilj kaže da ostaje 1; odluči")
        for i in decided:
            if i in TARGET or i not in cur or forbidden(i):
                blockers.append(f"odluka za {i} nema smisla (nije 'ostalo uključeno' danas)")

        new: dict[str, str] = {t: "monitor" for t in TARGET}
        rows, pending = [], []
        for t in TARGET:
            old = cur.get(t)
            rows.append((t, old or "—", "monitor",
                         "isto" if old == "monitor" else ("DODAJ" if old is None else "U MONITOR")))
        for i, mode in cur.items():
            if i in new:
                continue
            if forbidden(i):
                rows.append((i, mode, "—", "UKLONI (tvoj popis)"))
            elif decided.get(i) == "drop":
                rows.append((i, mode, "—", "UKLONI (--drop)"))
            elif decided.get(i) == "keep-monitor":
                new[i] = "monitor"
                rows.append((i, mode, "monitor", "ZADRŽI kao monitor"))
            elif decided.get(i) == "keep":
                if mode != "monitor":
                    blockers.append(f"--keep {i}: danas je {mode!r}; pravilo je da ništa nije "
                                    "dvosmjerno — koristi --keep-monitor ili --drop")
                new[i] = mode
                rows.append((i, mode, mode, "ZADRŽI (--keep)"))
            else:
                new[i] = mode
                pending.append(i)
                tag = " (NIJE U KATALOGU)" if i not in catalog else ""
                rows.append((i, mode, mode, "ČEKA ODLUKU" + tag))

        print("allowed_endpoints: staro -> novo")
        for i, o, n, what in rows:
            print(f"  {i:32s} {str(o):14s} -> {str(n):14s} {what}")
        print(f"\n  ukupno: danas {len(cur)}, poslije {len(new)}")
        print(f"  webhook_url    : {hook!r} -> {hook!r} (ne mijenja se)")
        print(f"  allowed_events : {len(events)} -> isto (ne mijenja se)")
        print(f"  active         : {cfg.active} -> 1")
        print(f"  verified       : {cfg.verified} -> 0 (pravilo aplikacije za svaku izmjenu)")
        if pending:
            print("\nČEKA ODLUKU — danas uključeno, nije na popisu od 17 (možda treba MarinaMasteru):")
            for i in pending:
                print(f"  {i}  ({cur[i]})  -> --keep {i} | --keep-monitor {i} | --drop {i}")
        for b in blockers:
            print(f"\nBLOKADA: {b}")

        changed = new != cur
        if not a.apply:
            print("\nBez --apply: ništa nije promijenjeno." + ("" if changed else " (nema razlike)"))
            return
        if pending or blockers:
            die("--apply odbijen: riješi ČEKA ODLUKU / BLOKADA iznad", 5)
        if not changed:
            print("\nNema razlike — ne pišem ništa.")
            return
        require_backup(a.backup, "external_api_config")

        order = TARGET + [i for i in new if i not in TARGET]
        body = UpdateConfigRequest(
            allowed_endpoints=[EndpointEntry(id=i, mode=new[i]) for i in order],
            webhook_url=hook, allowed_events=events)
        update_config(body=body, db=db, _=None)
        activate_config(db=db, _=None)

        db.expire_all()
        cfg = db.get(ExternalApiConfig, 1)
        after = {e["id"]: e["mode"] for e in json.loads(cfg.allowed_endpoints)}
        ok = (after == new and cfg.active == 1 and cfg.webhook_url == hook
              and json.loads(cfg.allowed_events or "[]") == events
              and not any(m == "bidirectional" for m in after.values())
              and not any(forbidden(i) for i in after))
        print(f"\nPRIMIJENJENO: {len(after)} endpointa, active={cfg.active}, "
              f"webhook_url={cfg.webhook_url!r}, events={len(events)}  provjera: "
              + ("OK" if ok else "NE SLAŽE SE — javi odmah"))
        if not ok:
            raise SystemExit(4)
    finally:
        db.close()


if __name__ == "__main__":
    main()
