"""Run AI analysis on pending news/announcements (P3).

Usage (from F:\\GlobalAIInvestor):
  .venv\\Scripts\\python.exe backend\\scripts\\analyze_ai.py [limit] [provider] [model]

Examples:
  .venv\\Scripts\\python.exe backend\\scripts\\analyze_ai.py 2 ollama qwen3:0.6b
  .venv\\Scripts\\python.exe backend\\scripts\\analyze_ai.py 10 deepseek deepseek-chat
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os  # noqa: E402

os.environ.setdefault("GAI_ROOT", str(ROOT))

from backend.app.ai import analyze_pending, list_alerts, list_analysis, make_client  # noqa: E402
from backend.app.db.migrate import migrate  # noqa: E402
from backend.app.main import get_db  # noqa: E402


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    provider = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("GAI_AI_PROVIDER", "ollama")
    model = sys.argv[3] if len(sys.argv) > 3 else None
    client = make_client(provider, model)
    print("provider:", provider, "model:", model or "(default)", "available:", client.available())
    with get_db() as conn:
        migrate(conn)
        result = analyze_pending(conn, client, limit=limit, model_id=model)
        print("result:", result)
        print("analysis rows:", len(list_analysis(conn, limit=5)))
        print("alerts:", len(list_alerts(conn, limit=5)))


if __name__ == "__main__":
    main()
