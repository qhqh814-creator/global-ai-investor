from __future__ import annotations

import sqlite3

from backend.app.db.migrate import migrate
from backend.app.securities.models import parse_bse_rows, parse_sse_rows, parse_szse_rows
from backend.app.securities.service import list_securities, stats, upsert_securities

SSE_ROWS = [
    {
        "SEC_NAME_CN": "浦发银行",
        "COMPANY_ABBR": "浦发银行",
        "COMPANY_ABBR_EN": "SPD BANK",
        "A_STOCK_CODE": "600000",
        "STOCK_TYPE": "1",
        "LIST_BOARD": "1",
        "LIST_DATE": "19991110",
        "CSRC_CODE_DESC": "金融业",
    },
    {
        "SEC_NAME_CN": "华兴源创",
        "COMPANY_ABBR": "华兴源创",
        "COMPANY_ABBR_EN": "HYC",
        "A_STOCK_CODE": "688001",
        "STOCK_TYPE": "8",
        "LIST_BOARD": "2",
        "LIST_DATE": "20190722",
        "CSRC_CODE_DESC": "专用设备制造业",
    },
    {
        "SEC_NAME_CN": "某某B",
        "COMPANY_ABBR": "某某B",
        "COMPANY_ABBR_EN": "XXB",
        "A_STOCK_CODE": "-",
        "STOCK_TYPE": "2",
        "LIST_BOARD": "1",
        "LIST_DATE": "19920101",
        "CSRC_CODE_DESC": "其他",
    },
]

SZSE_ROWS = [
    {
        "bk": "主板",
        "agdm": "000001",
        "agjc": "<a href='http://www.szse.cn/certificate/individual/index.html?code=000001' target='_blank'><u>平安银行</u></a>",
        "agssrq": "1991-04-03",
        "agzgb": "194.05",
        "agltgb": "194.05",
        "sshymc": "J 金融业",
    },
    {
        "bk": "创业板",
        "agdm": "300001",
        "agjc": "<a><u>特锐德</u></a>",
        "agssrq": "2009-10-30",
        "agzgb": "10.57",
        "agltgb": "10.00",
        "sshymc": "C 制造业",
    },
]

BSE_ROWS = [
    {"f12": "920085", "f14": "N森峰", "f13": 0, "f100": "自动化设备"},
    {"f12": "830799", "f14": "艾融软件", "f13": 0, "f100": "软件开发"},
]


def test_sse_parser_filters_b_shares_and_maps_board():
    records = parse_sse_rows(SSE_ROWS)
    assert len(records) == 2
    by_code = {r.code: r for r in records}
    assert by_code["600000"].board == "MAIN"
    assert by_code["600000"].name_zh == "浦发银行"
    assert by_code["600000"].listing_date.isoformat() == "1999-11-10"
    assert by_code["688001"].board == "STAR"


def test_szse_parser_html_and_units():
    records = parse_szse_rows(SZSE_ROWS)
    assert len(records) == 2
    main = records[0]
    assert main.code == "000001"
    assert main.name_zh == "平安银行"
    assert main.board == "MAIN"
    assert main.total_shares == 19_405_000_000
    assert main.float_shares == 19_405_000_000
    assert records[1].board == "CHINEXT"
    assert records[1].name_zh == "特锐德"


def test_bse_parser():
    records = parse_bse_rows(BSE_ROWS)
    assert len(records) == 2
    assert records[0].exchange == "BSE"
    assert records[0].board == "BSE"
    assert records[0].code == "920085"


def make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    migrate(conn)
    return conn


def test_upsert_and_stats():
    conn = make_db()
    records = parse_sse_rows(SSE_ROWS) + parse_szse_rows(SZSE_ROWS) + parse_bse_rows(BSE_ROWS)
    assert upsert_securities(conn, records) == 6
    summary = stats(conn)
    assert summary["total"] == 6
    assert {"exchange": "SSE", "board": "MAIN", "n": 1} in summary["by_exchange_board"]

    # idempotent upsert keeps total stable and preserves listing_date
    again = parse_sse_rows([SSE_ROWS[0]])
    upsert_securities(conn, again)
    assert stats(conn)["total"] == 6
    row = conn.execute("SELECT listing_date FROM securities WHERE code='600000'").fetchone()
    assert row["listing_date"] == "1999-11-10"


def test_list_filter():
    conn = make_db()
    upsert_securities(conn, parse_sse_rows(SSE_ROWS) + parse_szse_rows(SZSE_ROWS))
    items = list_securities(conn, exchange="SZSE", board="CHINEXT")
    assert len(items) == 1 and items[0]["code"] == "300001"
    assert len(list_securities(conn, exchange="SSE")) == 2

def test_fallback_populates_from_quotes():
    conn = make_db()
    conn.execute(
        """
        INSERT INTO stock_quotes(code, name, exchange, board, last, change_pct, prev_close, amount,
            quote_time, source_id, quote_kind, is_realtime, license_status, commercial_ok, fetched_at)
        VALUES ('000001', '平安银行', 'SZSE', 'MAIN', 10.0, 1.0, 9.9, 1e8, '2026-11-06T15:00:00+08:00',
                'eastmoney_quote', 'snapshot_unknown', 0, 'unlicensed_third_party', 0, '2026-11-06T15:01:00+08:00')
        """
    )
    conn.commit()
    from backend.app.securities.fallback import ensure_data_source, populate_from_quotes

    ensure_data_source(conn)
    result = populate_from_quotes(conn, "SZSE")
    assert result["upserted"] == 1
    row = conn.execute("SELECT source_id, name_zh FROM securities WHERE code='000001'").fetchone()
    assert row["source_id"] == "eastmoney_quote"
    src = conn.execute("SELECT license_status, commercial_ok FROM data_sources WHERE source_id='eastmoney_quote'").fetchone()
    assert src["license_status"] == "unlicensed_third_party"
    assert src["commercial_ok"] == 0
