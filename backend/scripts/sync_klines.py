"""Sync daily K-lines for a code list (P5 demo/backtest data).

Usage (from F:\\GlobalAIInvestor):
  .venv\\Scripts\\python.exe backend\\scripts\\sync_klines.py 2025-06-01 2026-11-07 600000:SSE 000001:SZSE 300001:SZSE 688001:SSE 920085:BSE
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os  # noqa: E402

os.environ.setdefault("GAI_ROOT", str(ROOT))

from backend.app.db.migrate import migrate  # noqa: E402
from backend.app.klines.service import sync_daily  # noqa: E402
from backend.app.main import get_db  # noqa: E402


def main() -> None:
    start = date.fromisoformat(sys.argv[1])
    end = date.fromisoformat(sys.argv[2])
    pairs = []
    for token in sys.argv[3:]:
        code, exchange = token.split(":")
        pairs.append((code, exchange))
    with get_db() as conn:
        migrate(conn)
        result = sync_daily(conn, pairs, start, end)
    print(result)


if __name__ == "__main__":
    main()
