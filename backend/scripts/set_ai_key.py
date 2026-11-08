"""Store a local AI API key with DPAPI encryption (no key is printed).

Usage:
  $env:DEEPSEEK_API_KEY='sk-...'
  .venv\\Scripts\\python.exe backend\\scripts\\set_ai_key.py deepseek
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("GAI_ROOT", str(ROOT))

from backend.app.ai.secrets import get_secret, set_secret  # noqa: E402

PROVIDERS = {"deepseek": "DEEPSEEK_API_KEY"}


def main() -> None:
    provider = sys.argv[1] if len(sys.argv) > 1 else "deepseek"
    env_name = PROVIDERS.get(provider)
    if not env_name:
        raise SystemExit(f"unknown provider: {provider}")
    key = os.environ.get(env_name) or (sys.argv[2] if len(sys.argv) > 2 else "")
    if not key:
        raise SystemExit(f"set {env_name} environment variable first")
    set_secret(f"{provider}_api_key", key)
    stored = get_secret(f"{provider}_api_key")
    print(f"{provider} key stored (len={len(stored or '')}, prefix={((stored or '')[:6])}…)")
    if not stored:
        raise SystemExit("failed to read back secret")


if __name__ == "__main__":
    main()
