"""Analyze selected announcement/news IDs with a local/cloud model.

Usage:
  .venv\\Scripts\\python.exe backend\\scripts\\analyze_selected.py 1284:announcement 1237:announcement qwen3:8b
"""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import os
os.environ.setdefault("GAI_ROOT", str(ROOT))
from backend.app.ai import make_client
from backend.app.ai.service import analyze_selected
from backend.app.db.migrate import migrate
from backend.app.main import get_db

def target(conn, target_type, target_id):
    if target_type == "announcement":
        r = conn.execute("SELECT id, sec_code, title, NULL AS summary, url AS url, published_at FROM announcements WHERE id=?", (target_id,)).fetchone()
        return {"target_type": "announcement", "id": r["id"], "title": r["title"], "summary": r["summary"], "url": r["url"], "published_at": r["published_at"]}
    r = conn.execute("SELECT id, title, summary, url, published_at FROM news_items WHERE id=?", (target_id,)).fetchone()
    return {"target_type": "news", "id": r["id"], "title": r["title"], "summary": r["summary"], "url": r["url"], "published_at": r["published_at"]}

def main():
    args = sys.argv[1:]
    if not args:
        raise SystemExit("usage: analyze_selected.py <id:type> ... <model>")
    provider, model = "ollama", "qwen3:8b"
    pairs = list(args)
    if pairs and pairs[-1].startswith("deepseek:"):
        provider, model = "deepseek", pairs.pop().split(":", 1)[1]
    elif pairs and pairs[-1].startswith("ollama:"):
        provider, model = "ollama", pairs.pop().split(":", 1)[1]
    elif pairs:
        model = pairs.pop()
    client = make_client(provider, model)
    with get_db() as conn:
        migrate(conn)
        selected = []
        for pair in pairs:
            tid, ttype = pair.split(":")
            selected.append(target(conn, ttype, int(tid)))
        print("provider", provider, "model", model, "targets", len(selected))
        print(analyze_selected(conn, client, selected, model_id=f"{provider}:{model}"))

if __name__ == "__main__":
    main()

