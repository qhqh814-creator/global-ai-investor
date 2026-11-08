"""Backfill securities master from the latest quote snapshot (fallback).

Usage (from F:\\GlobalAIInvestor):
  .venv\\Scripts\\python.exe backend\\scripts\\backfill_securities.py SZSE
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os  # noqa: E402

os.environ.setdefault("GAI_ROOT", str(ROOT))

from backend.app.db.migrate import migrate  # noqa: E402
from backend.app.main import get_db  # noqa: E402
from backend.app.securities.fallback import ensure_data_source, populate_from_quotes  # noqa: E402
from backend.app.securities.service import stats  # noqa: E402


def main() -> None:
    exchange = sys.argv[1] if len(sys.argv) > 1 else "SZSE"
    with get_db() as conn:
        migrate(conn)
        ensure_data_source(conn)
        result = populate_from_quotes(conn, exchange)
        print(result)
        print(stats(conn))


if __name__ == "__main__":
    main()
