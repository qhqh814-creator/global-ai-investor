"""PyInstaller entry point for the packaged FastAPI sidecar.

Reads GAI_PORT / GAI_TOKEN / GAI_ROOT from the Electron main process.
"""

from __future__ import annotations

import os

import uvicorn

from app.main import app  # noqa: E402  (frozen bundle: backend/ is the package root)


def main() -> None:
    port = int(os.environ.get("GAI_PORT", "8765"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
