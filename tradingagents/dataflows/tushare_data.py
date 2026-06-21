from __future__ import annotations

import os
from datetime import datetime

import pandas as pd
from dateutil.relativedelta import relativedelta

from .akshare_data import _INDICATOR_DESCRIPTIONS
from .symbol_utils import NoMarketDataError


class TushareUnavailableError(Exception):
    """Raised when Tushare is not installed, not configured, or unreachable."""


_A_SHARE_SUFFIXES = (".SZ", ".SS", ".SH", ".BJ")


def _tushare_token() -> str:
    token = os.environ.get("TUSHARE_TOKEN") or os.environ.get("TUSHARE_API_TOKEN")
    if not token:
        raise TushareUnavailableError(
            "TUSHARE_TOKEN is not set. Add TUSHARE_TOKEN=your_token to .env."
        )
    return token.strip().strip("'\"")


def _tushare_symbol(symbol: str) -> str:
    """Convert Yahoo-style or bare A-share symbols to Tushare ts_code."""
    raw = symbol.strip().upper()
    if raw.endswith(".SS"):
        raw = raw[:-3] + ".SH"
    if raw.endswith((".SZ", ".SH", ".BJ")) and raw[:6].isdigit():
        return raw
    if raw.isdigit() and len(raw) == 6:
        if raw.startswith(("6", "5")):
            return f"{raw}.SH"
        if raw.startswith(("0", "2", "3")):
            return f"{raw}.SZ"
        if raw.startswith(("4", "8", "9")):
            return f"{raw}.BJ"
    raise NoMarketDataError(
        symbol,
        symbol,
        "Tushare adapter currently supports six-digit China A-share symbols",
    )


def _tushare_date(date_value: str) -> str:
    return datetime.strptime(date_value, "%Y-%m-%d").strftime("%Y%m%d")


def _ensure_tushare_client():
    try:
        import tushare as ts
    except ImportError as exc:
        raise TushareUnavailableError(
            "Tushare is not installed. Install it with `pip install tushare`."
        ) from exc

    token = _tushare_token()
    try:
        return ts.pro_api(token)
    except TypeError:
        ts.set_token(token)
        return ts.pro_api()
    except Exception as exc:
        raise TushareUnavailableError(f"Tushare pro_api initialization failed: {exc}") from exc


def _load_tushare_ohlcv(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    ts_code = _tushare_symbol(symbol)
    pro = _ensure_tushare_client()
    try:
        data = pro.daily(
            ts_code=ts_code,
            start_date=_tushare_date(start_date),
            end_date=_tushare_date(end_date),
            fields="ts_code,trade_date,open,high,low,close,vol,amount",
        )
    except Exception as exc:
        raise TushareUnavailableError(f"Tushare daily failed: {exc}") from exc

    if data is None or data.empty:
        raise NoMarketDataError(symbol, ts_code, f"no rows between {start_date} and {end_date}")

    rename_map = {
        "trade_date": "Date",
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "vol": "Volume",
        "amount": "Amount",
    }
    data = data.rename(columns=rename_map)
    required = ["Date", "Open", "High", "Low", "Close", "Volume"]
    missing = [col for col in required if col not in data.columns]
    if missing:
        raise TushareUnavailableError(
            f"Tushare response missing required columns: {', '.join(missing)}"
        )

    keep = [col for col in ["Date", "Open", "High", "Low", "Close", "Volume", "Amount"] if col in data.columns]
    data = data[keep].copy()
    data["Date"] = pd.to_datetime(data["Date"], format="%Y%m%d", errors="coerce")
    for col in [c for c in keep if c != "Date"]:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data = data.dropna(subset=["Date", "Close"]).sort_values("Date")

    if data.empty:
        raise NoMarketDataError(symbol, ts_code, f"no usable rows between {start_date} and {end_date}")
    return data


def get_stock(symbol: str, start_date: str, end_date: str) -> str:
    """Return China A-share OHLCV data from Tushare as CSV text."""
    data = _load_tushare_ohlcv(symbol, start_date, end_date)
    ts_code = _tushare_symbol(symbol)
    output = data.copy()
    output["Date"] = output["Date"].dt.strftime("%Y-%m-%d")
    header = f"# Stock data for {symbol.upper()} from Tushare ({ts_code})\n"
    header += f"# Total records: {len(output)}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + output.to_csv(index=False)


def get_indicator(symbol: str, indicator: str, curr_date: str, look_back_days: int) -> str:
    """Calculate a stockstats indicator from Tushare OHLCV data."""
    if indicator not in _INDICATOR_DESCRIPTIONS:
        raise ValueError(
            f"Indicator {indicator} is not supported. Please choose from: {list(_INDICATOR_DESCRIPTIONS.keys())}"
        )

    from stockstats import wrap

    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = curr_dt - relativedelta(days=max(look_back_days, 260))
    data = _load_tushare_ohlcv(
        symbol,
        start_dt.strftime("%Y-%m-%d"),
        curr_dt.strftime("%Y-%m-%d"),
    )
    df = wrap(data)
    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
    df[indicator]

    before = curr_dt - relativedelta(days=look_back_days)
    rows = []
    current = curr_dt
    values = df.set_index("Date")[indicator]
    while current >= before:
        date_str = current.strftime("%Y-%m-%d")
        value = values.get(date_str, "N/A: Not a trading day (weekend or holiday)")
        if pd.isna(value):
            value = "N/A"
        rows.append(f"{date_str}: {value}")
        current -= relativedelta(days=1)

    return (
        f"## {indicator} values from {before.strftime('%Y-%m-%d')} to {curr_date}:\n\n"
        + "\n".join(rows)
        + "\n\n"
        + _INDICATOR_DESCRIPTIONS[indicator]
    )
