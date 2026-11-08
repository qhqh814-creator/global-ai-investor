"""Sync announcements (cninfo) and RSS news (P2).

Usage (from F:\\GlobalAIInvestor):
  .venv\\Scripts\\python.exe backend\\scripts\\sync_content.py [days] [max_pages]
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os  # noqa: E402

os.environ.setdefault("GAI_ROOT", str(ROOT))

from backend.app.content.service import list_announcements, list_news, sync_announcements, sync_news  # noqa: E402
from backend.app.db.migrate import migrate  # noqa: E402
from backend.app.main import get_db  # noqa: E402


def main() -> None:
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    max_pages = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    with get_db() as conn:
        migrate(conn)
        ann = sync_announcements(conn, days=days, max_pages=max_pages)
        print("announcements:", ann)
        news = sync_news(conn)
        print("news:", news)
        print("latest announcements:")
        for item in list_announcements(conn, limit=3):
            print(" ", item["sec_code"], item["title"][:40], item["published_at"])
        print("latest news:")
        for item in list_news(conn, limit=3):
            print(" ", item["source_id"], item["title"][:40], item["published_at"])


if __name__ == "__main__":
    main()
