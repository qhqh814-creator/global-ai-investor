"""Build the versioned A-share rule library (data files, P1).

This script only SEEDS the JSON rule files; runtime reads the JSON files via
app.rules.loader. Values marked "待核" must be confirmed against the official
rule texts in P1 verification gate (docs/06 section 6).

Official sources (retrieved 2026-11-08):
- SSE 2026: https://www.sse.com.cn/lawandrules/sselawsrules2025/trade/universal/c/c_20260424_10816492.shtml
- SZSE 2026: https://www.szse.cn/lawrules/rule/stock/trade/t20260424_620190.html
- BSE 2026: https://www.bse.cn/jygl_list/200028217.html
- BSE 34: https://www.bse.cn/jygl_list/200029142.html
"""

from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "app" / "rules" / "library"

SSE_URL = "https://www.sse.com.cn/lawandrules/sselawsrules2025/trade/universal/c/c_20260424_10816492.shtml"
SZSE_URL = "https://www.szse.cn/lawrules/rule/stock/trade/t20260424_620190.html"
BSE_URL = "https://www.bse.cn/jygl_list/200028217.html"
BSE34_URL = "https://www.bse.cn/jygl_list/200029142.html"


def sessions(after_hours: bool, after_min: int = 100, after_step: int = 100, pending: bool = False) -> dict:
    if pending:
        ah = {"enabled": False, "status": "PENDING", "order": [], "trade": [], "price": "CLOSE"}
    elif after_hours:
        ah = {
            "enabled": True,
            "status": "EFFECTIVE",
            "order": [["09:30", "11:30"], ["13:00", "15:30"]],
            "trade": ["15:05", "15:30"],
            "price": "CLOSE",
            "min_qty": after_min,
            "step": after_step,
            "max_qty": 1_000_000,
        }
    else:
        ah = {"enabled": False, "status": "EFFECTIVE", "order": [], "trade": [], "price": "CLOSE"}
    return {
        "open_auction": ["09:15", "09:25"],
        "open_auction_cancel_cutoff": "09:20",
        "continuous": [["09:30", "11:30"], ["13:00", "14:57"]],
        "close_auction": ["14:57", "15:00"],
        "close_auction_cancel_allowed": False,
        "after_hours": ah,
    }


def fees(stamp: float, handling: float) -> dict:
    return {
        "stamp_duty": stamp,
        "transfer_fee": 0.00001,
        "handling_fee": handling,
        "regulatory_fee": 0.00002,
        "commission_min": 5.0,
    }


def pct(up: float, down: float) -> dict:
    return {"type": "PCT", "up_pct": up, "down_pct": down}


def first_day_special() -> dict:
    return {
        "type": "FIRST_DAY_SPECIAL",
        "first_day_up_pct": 0.44,
        "first_day_down_pct": 0.36,
        "first_day_auction_min_ratio": 0.80,
        "first_day_auction_max_ratio": 1.20,
        "first_day_continuous_min_ratio": 0.64,
        "first_day_continuous_max_ratio": 1.44,
        "base_price_type": "ISSUE_PRICE",
    }


def no_limit() -> dict:
    return {"type": "NONE"}


def order(min_qty: int, step: int, multiple: bool, max_qty: int, max_market: int | None, odd: int) -> dict:
    return {
        "min_qty": min_qty,
        "step": step,
        "multiple_required": multiple,
        "max_qty": max_qty,
        "max_qty_market": max_market,
        "odd_lot_threshold": odd,
        "odd_lot_must_one_order": True,
    }


def cage(kind: str) -> dict:
    if kind == "hs":
        return {"enabled": True, "pct": 0.02, "abs_offset": 0.10, "compare": "WIDER"}
    if kind == "star":
        # 0.1 元宽免是否存在：待核
        return {"enabled": True, "pct": 0.02, "abs_offset": None, "compare": "WIDER"}
    return {"enabled": True, "pct": 0.05, "abs_ticks": 10, "compare": "WIDER"}


def rule_set(
    risk: str,
    phase: str,
    limit: dict,
    order_params: dict,
    cage_params: dict,
    sess: dict,
    fee_params: dict,
    cap: int | None = None,
    notes: list[str] | None = None,
) -> dict:
    return {
        "risk_flag": risk,
        "listing_phase": phase,
        "price_limit": limit,
        "order": order_params,
        "tick_size": 0.01,
        "price_cage": cage_params,
        "fees": fee_params,
        "sessions": sess,
        "settlement": "T+1",
        "risk_warning_buy_daily_cap": cap,
        "notes": notes or [],
    }


def main_board_sets(
    st_pct: float,
    sess_main: dict,
    fee_params: dict,
    st_cap: int | None = None,
) -> list[dict]:
    cap = 500_000 if st_cap is None else st_cap
    return [
        rule_set("NORMAL", "SEASONED", pct(0.10, 0.10), order(100, 100, True, 1_000_000, None, 100), cage("hs"), sess_main, fee_params),
        rule_set("NORMAL", "IPO_DAY1", first_day_special(), order(100, 100, True, 1_000_000, None, 100), cage("hs"), sess_main, fee_params),
        rule_set("NORMAL", "IPO_DAY2_5", pct(0.10, 0.10), order(100, 100, True, 1_000_000, None, 100), cage("hs"), sess_main, fee_params),
        rule_set("ST", "SEASONED", pct(st_pct, st_pct), order(100, 100, True, 1_000_000, None, 100), cage("hs"), sess_main, fee_params, cap),
        rule_set("DELISTING", "IPO_DAY1", no_limit(), order(100, 100, True, 1_000_000, None, 100), cage("hs"), sess_main, fee_params),
        rule_set("DELISTING", "SEASONED", pct(0.10, 0.10), order(100, 100, True, 1_000_000, None, 100), cage("hs"), sess_main, fee_params),
    ]


def star_sets(sess: dict, fee_params: dict) -> list[dict]:
    p = order(200, 1, False, 100_000, 50_000, 200)
    return [
        rule_set("NORMAL", "SEASONED", pct(0.20, 0.20), p, cage("star"), sess, fee_params),
        rule_set("NORMAL", "IPO_DAY1", no_limit(), p, cage("star"), sess, fee_params),
        rule_set("NORMAL", "IPO_DAY2_5", no_limit(), p, cage("star"), sess, fee_params),
        rule_set("ST", "SEASONED", pct(0.20, 0.20), p, cage("star"), sess, fee_params,
                 notes=["科创板风险警示股票不进入风险警示板，不适用50万股限制"]),
        rule_set("DELISTING", "IPO_DAY1", no_limit(), p, cage("star"), sess, fee_params),
        rule_set("DELISTING", "SEASONED", pct(0.20, 0.20), p, cage("star"), sess, fee_params,
                 notes=["退市整理期次日起20%：推断，待核"]),
    ]


def chinext_sets(sess: dict, fee_params: dict) -> list[dict]:
    p = order(100, 100, True, 300_000, 15_000, 100)
    return [
        rule_set("NORMAL", "SEASONED", pct(0.20, 0.20), p, cage("hs"), sess, fee_params),
        rule_set("NORMAL", "IPO_DAY1", no_limit(), p, cage("hs"), sess, fee_params),
        rule_set("NORMAL", "IPO_DAY2_5", no_limit(), p, cage("hs"), sess, fee_params),
        rule_set("ST", "SEASONED", pct(0.20, 0.20), p, cage("hs"), sess, fee_params, 500_000),
        rule_set("DELISTING", "IPO_DAY1", no_limit(), p, cage("hs"), sess, fee_params),
        rule_set("DELISTING", "SEASONED", pct(0.20, 0.20), p, cage("hs"), sess, fee_params),
    ]


def bse_sets(sess: dict, fee_params: dict, st_cap: int | None = None) -> list[dict]:
    p = order(100, 1, False, 1_000_000, None, 100)
    return [
        rule_set("NORMAL", "SEASONED", pct(0.30, 0.30), p, cage("bse"), sess, fee_params),
        rule_set("NORMAL", "IPO_DAY1", no_limit(), p, cage("bse"), sess, fee_params),
        rule_set("NORMAL", "IPO_DAY2_5", pct(0.30, 0.30), p, cage("bse"), sess, fee_params),
        rule_set("ST", "SEASONED", pct(0.30, 0.30), p, cage("bse"), sess, fee_params, st_cap,
                 notes=["风险警示股票涨跌幅30%：第4.5条未另设比例，待核"]),
        rule_set("DELISTING", "IPO_DAY1", no_limit(), p, cage("bse"), sess, fee_params),
        rule_set("DELISTING", "SEASONED", pct(0.30, 0.30), p, cage("bse"), sess, fee_params),
    ]


def version(
    code: str,
    exchange: str,
    doc_no: str,
    publish: str,
    start: str,
    end: str | None,
    url: str,
    supersedes: str | None,
    boards: dict[str, list[dict]],
    clauses: list[dict] | None = None,
) -> dict:
    return {
        "version_code": code,
        "exchange": exchange,
        "doc_no": doc_no,
        "publish_date": publish,
        "effective_from": start,
        "effective_to": end,
        "source_url": url,
        "supersedes": supersedes,
        "clauses": clauses or [],
        "boards": {name: {"sets": sets} for name, sets in boards.items()},
    }


def build() -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []

    # ---------------- SSE ----------------
    sse_fees_2023_early = fees(0.001, 0.0000487)
    sse_fees_2023_late = fees(0.0005, 0.0000341)
    sse_sess_2023 = sessions(after_hours=False)
    sse_star_sess_2023 = sessions(after_hours=True, after_min=200, after_step=1)
    sse_sess_2026 = sessions(after_hours=True, after_min=100, after_step=100)
    sse_star_sess_2026 = sessions(after_hours=True, after_min=200, after_step=1)

    out.append(("sse/2023.02.17.json", version(
        "SSE-2023.02.17", "SSE", "上证发〔2023〕32号", "2023-02-17", "2023-02-17", "2023-08-27", SSE_URL, None,
        {"MAIN": main_board_sets(0.05, sse_sess_2023, sse_fees_2023_early),
         "STAR": star_sets(sse_star_sess_2023, sse_fees_2023_early)},
    )))
    out.append(("sse/2023.08.28.json", version(
        "SSE-2023.08.28", "SSE", "上证发〔2023〕32号", "2023-02-17", "2023-08-28", "2026-07-05", SSE_URL, "SSE-2023.02.17",
        {"MAIN": main_board_sets(0.05, sse_sess_2023, sse_fees_2023_late),
         "STAR": star_sets(sse_star_sess_2023, sse_fees_2023_late)},
    )))
    out.append(("sse/2026.07.06.json", version(
        "SSE-2026.07.06", "SSE", "上证发〔2026〕41号", "2026-04-24", "2026-07-06", None, SSE_URL, "SSE-2023.08.28",
        {"MAIN": main_board_sets(0.10, sse_sess_2026, sse_fees_2023_late),
         "STAR": star_sets(sse_star_sess_2026, sse_fees_2023_late)},
        clauses=[{"clause_no": "3.7", "title": "盘后固定价格交易扩至全部A股及ETF", "status": "EFFECTIVE",
                  "note": "2026-07-06 起"}],
    )))

    # ---------------- SZSE ----------------
    szse_fees_early = fees(0.001, 0.0000487)
    szse_fees_late = fees(0.0005, 0.0000341)
    szse_sess_2023 = sessions(after_hours=False)
    szse_cn_sess_2023 = sessions(after_hours=True, after_min=100, after_step=100)
    szse_sess_2026 = sessions(after_hours=True, after_min=100, after_step=100)
    szse_cn_sess_2026 = sessions(after_hours=True, after_min=100, after_step=100)

    out.append(("szse/2023.02.17.json", version(
        "SZSE-2023.02.17", "SZSE", "深证上〔2023〕98号", "2023-02-17", "2023-02-17", "2023-08-27", SZSE_URL, None,
        {"MAIN": main_board_sets(0.05, szse_sess_2023, szse_fees_early),
         "CHINEXT": chinext_sets(szse_cn_sess_2023, szse_fees_early)},
    )))
    out.append(("szse/2023.08.28.json", version(
        "SZSE-2023.08.28", "SZSE", "深证上〔2023〕98号", "2023-02-17", "2023-08-28", "2026-07-05", SZSE_URL, "SZSE-2023.02.17",
        {"MAIN": main_board_sets(0.05, szse_sess_2023, szse_fees_late),
         "CHINEXT": chinext_sets(szse_cn_sess_2023, szse_fees_late)},
    )))
    out.append(("szse/2026.07.06.json", version(
        "SZSE-2026.07.06", "SZSE", "深证上〔2026〕551号", "2026-04-24", "2026-07-06", None, SZSE_URL, "SZSE-2023.08.28",
        {"MAIN": main_board_sets(0.10, szse_sess_2026, szse_fees_late),
         "CHINEXT": chinext_sets(szse_cn_sess_2026, szse_fees_late)},
        clauses=[{"clause_no": "3.7", "title": "盘后固定价格交易扩至全部A股及ETF", "status": "EFFECTIVE",
                  "note": "2026-07-06 起"}],
    )))

    # ---------------- BSE ----------------
    bse_fees_2021 = fees(0.001, 0.00025)  # 经手费 0.025%：待核（2023-08-28 前）
    bse_fees_2023 = fees(0.0005, 0.000125)
    bse_sess = sessions(after_hours=False)  # 盘后固定价格规则未实施
    bse_sess_pending = sessions(after_hours=False, pending=True)

    out.append(("bse/2021.11.15.json", version(
        "BSE-2021.11.15", "BSE", "北证公告〔2021〕15号", "2021-11-02", "2021-11-15", "2023-08-27", BSE_URL, None,
        {"BSE": bse_sets(bse_sess, bse_fees_2021)},
    )))
    out.append(("bse/2023.08.28.json", version(
        "BSE-2023.08.28", "BSE", "北证公告〔2021〕15号", "2021-11-02", "2023-08-28", "2026-07-05", BSE_URL, "BSE-2021.11.15",
        {"BSE": bse_sets(bse_sess, bse_fees_2023)},
    )))
    out.append(("bse/2026.07.06.json", version(
        "BSE-2026.07.06", "BSE", "北证公告〔2026〕17号", "2026-04-24", "2026-07-06", "2026-08-30", BSE_URL, "BSE-2023.08.28",
        {"BSE": bse_sets(bse_sess_pending, bse_fees_2023)},
        clauses=[
            {"clause_no": "3.7.1-3.7.10", "title": "盘后固定价格交易", "status": "PENDING", "note": "实施时间由北交所另行通知"},
            {"clause_no": "4.5.1-4.5.4", "title": "风险警示/退市整理股票交易", "status": "PENDING", "note": "北证公告〔2026〕34号：2026-08-31 实施"},
        ],
    )))
    out.append(("bse/2026.08.31.json", version(
        "BSE-2026.08.31", "BSE", "北证公告〔2026〕17号", "2026-04-24", "2026-08-31", None, BSE34_URL, "BSE-2026.07.06",
        {"BSE": bse_sets(bse_sess_pending, bse_fees_2023, st_cap=200_000)},
        clauses=[
            {"clause_no": "3.7.1-3.7.10", "title": "盘后固定价格交易", "status": "PENDING", "note": "实施时间由北交所另行通知"},
            {"clause_no": "4.5.1-4.5.4", "title": "风险警示/退市整理股票交易", "status": "EFFECTIVE", "note": "2026-08-31 起：单日买入单只风险警示股票≤20万股"},
        ],
    )))
    return out


def main() -> None:
    for rel, data in build():
        path = BASE / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {rel}")


if __name__ == "__main__":
    main()
