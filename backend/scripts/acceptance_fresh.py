"""End-to-end acceptance pipeline on a FRESH data root (P6 acceptance).

Run with GAI_ROOT pointing to a new empty directory:
  $env:GAI_ROOT='F:\\GlobalAIInvestor\\acceptance-data'
  .venv\\Scripts\\python.exe backend\\scripts\\acceptance_fresh.py

Steps: bootstrap -> quotes -> securities (SSE/BSE official, SZSE snapshot
fallback) -> news/announcements -> klines -> signals/screening -> backtest ->
paper buy -> prediction -> dashboard summary.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os  # noqa: E402

os.environ.setdefault("GAI_ROOT", str(ROOT))

from backend.app.backtest.service import run_backtest  # noqa: E402
from backend.app.content.service import sync_announcements, sync_news  # noqa: E402
from backend.app.datasources.securities_lists import fetch_bse, fetch_sse  # noqa: E402
from backend.app.klines.service import sync_daily  # noqa: E402
from backend.app.main import bootstrap, get_db  # noqa: E402
from backend.app.paper.service import get_account, place_order  # noqa: E402
from backend.app.predictions.service import create_prediction  # noqa: E402
from backend.app.quotes.service import get_dashboard, sync_quotes  # noqa: E402
from backend.app.screening.service import run_screening  # noqa: E402
from backend.app.securities import upsert_securities  # noqa: E402
from backend.app.securities.fallback import ensure_data_source, populate_from_quotes  # noqa: E402
from backend.app.securities.service import stats as sec_stats  # noqa: E402
from backend.app.signals.service import run_signals  # noqa: E402


def main() -> None:
    print("GAI_ROOT =", os.environ.get("GAI_ROOT"))
    bootstrap()
    with get_db() as conn:
        quotes = sync_quotes(conn)
        print("quotes:", {k: v for k, v in quotes.items() if k != "breadth"})
        print("breadth:", quotes.get("breadth"))

        sse = upsert_securities(conn, fetch_sse())
        bse = upsert_securities(conn, fetch_bse())
        print("securities official: SSE", sse, "BSE", bse)

        ensure_data_source(conn)
        fb = populate_from_quotes(conn, "SZSE")
        print("SZSE fallback:", fb)
        print("securities stats:", sec_stats(conn))

        print("news:", sync_news(conn))
        print("announcements:", sync_announcements(conn, days=1, max_pages=10))

        klines = sync_daily(conn, [("600000", "SSE"), ("000001", "SZSE"), ("300001", "SZSE")],
                            date(2025, 6, 1), date.today() - timedelta(days=1))
        print("klines:", klines)

        print("signals:", run_signals(conn))
        print("screening:", run_screening(conn, {"max_results": 20}))

        bt = run_backtest(conn, ["600000", "000001", "300001"], "2026-01-01", "2026-11-07",
                          entry_pct=5.0, hold_days=3)
        print("backtest:", bt["status"], bt.get("metrics", {}).get("total_return"), bt.get("metrics", {}).get("trades_count"))

        buy = place_order(conn, "600000", "BUY", 100)
        print("paper buy:", buy["status"], buy.get("price"), "account:", get_account(conn)["total_asset"])
        print("prediction:", create_prediction(conn, "600000", "UP", horizon_days=5, model_id="acceptance"))

        dash = get_dashboard(conn)
        available = [c for c in dash["cards"] if c["status"] == "available"]
        print(f"dashboard cards: {len(dash['cards'])} available={len(available)}")
        for card in dash["cards"]:
            print(f"  {card['key']}: {card['status']} {card['value'] or ''}")


if __name__ == "__main__":
    main()
