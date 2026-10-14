"""`python -m app.agent` — the security agent process (deploy/erp-agent.service).

    AGENT_DATABASE_URL   required; on the VPS the role erp_agent over the Unix
                         socket, peer auth, no password:
                         postgresql+psycopg2://erp_agent@/erp_iot?host=/var/run/postgresql

    --once               one pass, then exit (tests, a manual run)
    --every SECONDS      a pass every SECONDS (the unit uses 300)
    --window-hours N     the sliding window each pass reads (default 24)

There is no default URL on purpose: the backend's DATABASE_URL belongs to a role
that writes everything, and the agent must never fall back to it.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import timedelta

from sqlalchemy import create_engine

from .run import run_once


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.agent")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true")
    mode.add_argument("--every", type=int, metavar="SECONDS")
    ap.add_argument("--window-hours", type=float, default=24.0)
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    url = os.environ.get("AGENT_DATABASE_URL", "").strip()
    if not url:
        print("AGENT_DATABASE_URL is not set — the agent has its own role and no default "
              "(spec §13.1)", file=sys.stderr)
        return 2
    window = timedelta(hours=args.window_hours)
    engine = create_engine(url, pool_pre_ping=True)
    log = logging.getLogger("erp-agent")
    try:
        while True:
            with engine.connect() as c:
                summary = run_once(c, window=window)
            log.info("pass %s", json.dumps(summary, sort_keys=True))
            if args.once:
                return 0
            time.sleep(max(args.every, 30))
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
