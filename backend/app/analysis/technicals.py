"""Technical indicators from local daily klines (extracted idea from reference project).

Pure computation; no external API. Used by AI team review and trade plans.
"""

from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd


def load_bars(conn: sqlite3.Connection, code: str, limit: int = 120) -> list[dict]:
    rows = conn.execute(
        "SELECT trade_date, open, high, low, close, volume FROM kline_daily WHERE code=? "
        "ORDER BY trade_date DESC LIMIT ?",
        (code, max(30, min(limit, 500))),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


def compute_indicators(bars: list[dict]) -> dict:
    if len(bars) < 30:
        return {"ok": False, "reason": "INSUFFICIENT_BARS", "bars": len(bars)}
    df = pd.DataFrame(bars).copy()
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["close"])
    close, high, low, vol = df["close"], df["high"], df["low"], df["volume"]

    for window in (5, 10, 20, 60):
        df[f"ma{window}"] = close.rolling(window).mean()
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi"] = np.where(loss == 0, np.where(gain > 0, 100.0, 50.0), 100 - 100 / (1 + rs))
    ema12, ema26 = close.ewm(span=12, adjust=False).mean(), close.ewm(span=26, adjust=False).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]
    mid = close.rolling(20).mean()
    std = close.rolling(20).std()
    df["bb_mid"], df["bb_upper"], df["bb_lower"] = mid, mid + 2 * std, mid - 2 * std
    low9, high9 = low.rolling(9).min(), high.rolling(9).max()
    rsv = (close - low9) / (high9 - low9).replace(0, np.nan) * 100
    df["k"] = rsv.ewm(com=2, adjust=False).mean()
    df["d"] = df["k"].ewm(com=2, adjust=False).mean()
    df["vol_ma5"] = vol.rolling(5).mean()
    df["volume_ratio"] = vol / df["vol_ma5"].replace(0, np.nan)
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()

    last = df.iloc[-1]
    price = float(last["close"])
    ma5, ma20, ma60 = last.get("ma5"), last.get("ma20"), last.get("ma60")
    trend = "NEUTRAL"
    if pd.notna(ma5) and pd.notna(ma20):
        trend = "BULLISH" if price > ma5 > ma20 else "BEARISH" if price < ma5 < ma20 else "NEUTRAL"
    rsi = float(last["rsi"]) if pd.notna(last["rsi"]) else None
    rsi_state = "OVERBOUGHT" if rsi and rsi >= 70 else "OVERSOLD" if rsi and rsi <= 30 else "NEUTRAL"
    return {
        "ok": True,
        "bars": len(df),
        "price": round(price, 2),
        "ma5": round(float(ma5), 2) if pd.notna(ma5) else None,
        "ma10": round(float(last["ma10"]), 2) if pd.notna(last["ma10"]) else None,
        "ma20": round(float(ma20), 2) if pd.notna(ma20) else None,
        "ma60": round(float(ma60), 2) if pd.notna(ma60) else None,
        "rsi14": round(rsi, 2) if rsi is not None else None,
        "rsi_state": rsi_state,
        "macd": round(float(last["macd"]), 4) if pd.notna(last["macd"]) else None,
        "macd_signal": round(float(last["macd_signal"]), 4) if pd.notna(last["macd_signal"]) else None,
        "macd_hist": round(float(last["macd_hist"]), 4) if pd.notna(last["macd_hist"]) else None,
        "macd_state": "BULLISH" if pd.notna(last["macd_hist"]) and last["macd_hist"] > 0 else "BEARISH",
        "bb_upper": round(float(last["bb_upper"]), 2) if pd.notna(last["bb_upper"]) else None,
        "bb_mid": round(float(last["bb_mid"]), 2) if pd.notna(last["bb_mid"]) else None,
        "bb_lower": round(float(last["bb_lower"]), 2) if pd.notna(last["bb_lower"]) else None,
        "bb_position": (
            "ABOVE_UPPER" if last["bb_upper"] and price > last["bb_upper"]
            else "BELOW_LOWER" if last["bb_lower"] and price < last["bb_lower"] else "INSIDE"
        ),
        "k": round(float(last["k"]), 2) if pd.notna(last["k"]) else None,
        "d": round(float(last["d"]), 2) if pd.notna(last["d"]) else None,
        "kdj_state": "OVERBOUGHT" if pd.notna(last["k"]) and last["k"] > 80 else "OVERSOLD" if pd.notna(last["k"]) and last["k"] < 20 else "NEUTRAL",
        "volume_ratio": round(float(last["volume_ratio"]), 2) if pd.notna(last["volume_ratio"]) else None,
        "atr14": round(float(last["atr"]), 2) if pd.notna(last["atr"]) else None,
        "trend": trend,
        "as_of": df.iloc[-1]["trade_date"],
    }

