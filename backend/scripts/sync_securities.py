"""Sync securities master data for one or all exchanges (P1 CLI).

Usage (from F:\\GlobalAIInvestor):
  .venv\\Scripts\\python.exe backend\\scripts\\sync_securities.py SSE
  .venv\\Scripts\\python.exe backend\\scripts\\sync_securities.py ALL
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os  # noqa: E402

os.environ.setdefault("GAI_ROOT", str(ROOT))

from backend.app.datasources.securities_lists import fetch_bse, fetch_sse, fetch_szse  # noqa: E402
from backend.app.db.migrate import migrate  # noqa: E402
from backend.app.securities.service import stats, upsert_securities  # noqa: E402
from backend.app.main import DB_PATH, get_db  # noqa: E402


def run(exchange: str) -> None:
    with get_db() as conn:
        migrate(conn)
    if exchange == "SSE":
        records = fetch_sse()
    elif exchange == "SZSE":
        records = fetch_szse()
    elif exchange == "BSE":
        records = fetch_bse()
    else:
        raise SystemExit(f"unknown exchange: {exchange}")
    with get_db() as conn:
        count = upsert_securities(conn, records)
        summary = stats(conn)
    print(f"{exchange}: fetched={len(records)} upserted={count}")
    print(f"stats: {summary}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("exchange", choices=["SSE", "SZSE", "BSE", "ALL"])
    args = parser.parse_args()
    targets = ["SSE", "SZSE", "BSE"] if args.exchange == "ALL" else [args.exchange]
    for target in targets:
        run(target)


if __name__ == "__main__":
    main()
