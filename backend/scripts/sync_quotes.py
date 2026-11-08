"""Sync index + full-market snapshots and compute dashboard aggregates (P2).

Usage (from F:\\GlobalAIInvestor):
  .venv\\Scripts\\python.exe backend\\scripts\\sync_quotes.py
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
from backend.app.quotes.service import get_dashboard, sync_quotes  # noqa: E402


def main() -> None:
    with get_db() as conn:
        migrate(conn)
        summary = sync_quotes(conn)
        print("sync summary:", {k: v for k, v in summary.items() if k != "breadth"})
        if summary.get("breadth"):
            print("breadth:", summary["breadth"])
        dash = get_dashboard(conn)
        for card in dash["cards"]:
            print(f"  {card['key']}: {card['status']} {card['value'] or ''}")


if __name__ == "__main__":
    main()
