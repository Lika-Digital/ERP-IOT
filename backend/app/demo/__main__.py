"""python -m app.demo seed | remove — the demo marina in this ERP's database (D28)."""
import argparse
import json
import os
import sys

from ..database import SessionLocal
from . import seed as demo


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m app.demo")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seed", help="create the demo marina (refuses if it exists)")
    s.add_argument("--port", type=int, default=int(os.environ.get("DEMO_SIM_PORT", 18080)))
    s.add_argument("--seed", type=int, default=int(os.environ.get("DEMO_SIM_SEED", 28)))
    s.add_argument("--days", type=int, default=demo.HISTORY_DAYS)
    sub.add_parser("remove", help="delete the demo marina and everything under it")
    a = p.parse_args(argv)
    db = SessionLocal()
    try:
        if a.cmd == "seed":
            try:
                out = demo.seed(db, port=a.port, seed_value=a.seed, days=a.days,
                                password=os.environ.get("DEMO_SIM_PASSWORD", "demo-sim-local"))
            except demo.DemoExists as exc:
                print(str(exc), file=sys.stderr)
                return 1
            print(json.dumps(out))
            return 0
        print(json.dumps({"removed": demo.remove(db)}))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
