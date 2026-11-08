from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.rules.loader import load_library  # noqa: E402


@pytest.fixture(scope="session")
def library():
    return load_library()
