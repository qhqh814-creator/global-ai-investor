"""Rule library loader and selector.

Library layout:
  backend/app/rules/library/<exchange>/<version>.json

Each JSON file is one RuleVersion (one market, several boards). Date-based
selection is the only path to a rule set.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .models import Board, Exchange, ListingPhase, RiskFlag, RuleSet, RuleVersion

LIBRARY_DIR = Path(__file__).resolve().parent / "library"


class RuleNotFound(LookupError):
    """Raised when no effective rule set matches the request."""


class RuleLibrary:
    def __init__(self, versions: list[RuleVersion]):
        self._versions = sorted(versions, key=lambda v: v.effective_from)
        self._validate_windows()

    @property
    def versions(self) -> list[RuleVersion]:
        return list(self._versions)

    def _validate_windows(self) -> None:
        """Detect overlapping effective windows for the same board/risk/phase."""
        for i, a in enumerate(self._versions):
            for b in self._versions[i + 1 :]:
                if a.exchange != b.exchange:
                    continue
                a_end = a.effective_to or date.max
                b_end = b.effective_to or date.max
                if a.effective_from <= b_end and b.effective_from <= a_end:
                    # Same market overlapping in time: board keys must be disjoint
                    # only if both define the same (board, risk, phase).
                    for board_a, rules_a in a.boards.items():
                        rules_b = b.boards.get(board_a)
                        if not rules_b:
                            continue
                        keys_a = {(s.risk_flag, s.listing_phase) for s in rules_a.sets}
                        keys_b = {(s.risk_flag, s.listing_phase) for s in rules_b.sets}
                        if keys_a & keys_b:
                            raise ValueError(
                                f"overlapping rule versions {a.version_code} and {b.version_code} "
                                f"for {a.exchange}/{board_a} {sorted(keys_a & keys_b)}"
                            )

    def select(
        self,
        exchange: Exchange,
        board: Board | str,
        risk_flag: RiskFlag,
        listing_phase: ListingPhase,
        on_date: date,
    ) -> tuple[RuleVersion, RuleSet]:
        candidates = [
            v for v in self._versions if v.exchange == exchange and v.effective_on(on_date) and board in v.boards
        ]
        if not candidates:
            raise RuleNotFound(f"no rule version for {exchange}/{board} on {on_date.isoformat()}")

        # Newest effective version wins.
        version = max(candidates, key=lambda v: v.effective_from)
        sets = version.boards[str(board)].sets

        by_key = {(s.risk_flag, s.listing_phase): s for s in sets}

        # risk_flag exact match; fall back to NORMAL only for non-risk-specific boards.
        risk_candidates = [k for k in by_key if k[0] == risk_flag]
        if not risk_candidates:
            risk_candidates = [k for k in by_key if k[0] == "NORMAL"]
        if not risk_candidates:
            raise RuleNotFound(f"no risk rule for {exchange}/{board} risk={risk_flag}")

        # listing phase exact, then SEASONED.
        exact = [k for k in risk_candidates if k[1] == listing_phase]
        if exact:
            return version, by_key[exact[0]]
        seasoned = [k for k in risk_candidates if k[1] == "SEASONED"]
        if seasoned:
            return version, by_key[seasoned[0]]
        raise RuleNotFound(f"no listing-phase rule for {exchange}/{board} phase={listing_phase}")


def load_version_file(path: Path) -> RuleVersion:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return RuleVersion.model_validate(data)


def load_library(directory: Path | None = None) -> RuleLibrary:
    root = directory or LIBRARY_DIR
    files = sorted(root.glob("*/*.json"))
    if not files:
        raise FileNotFoundError(f"rule library is empty: {root}")
    versions = [load_version_file(p) for p in files]
    return RuleLibrary(versions)


_default_library: RuleLibrary | None = None


def get_library() -> RuleLibrary:
    global _default_library
    if _default_library is None:
        _default_library = load_library()
    return _default_library
