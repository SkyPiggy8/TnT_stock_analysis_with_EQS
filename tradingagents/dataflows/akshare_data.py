from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime

import pandas as pd
from dateutil.relativedelta import relativedelta

from .config import get_config
from .symbol_utils import NoMarketDataError


class AkShareUnavailableError(Exception):
    """Raised when AKShare is not installed or its upstream data call fails."""


_A_SHARE_SUFFIXES = (".SZ", ".SS", ".SH", ".BJ")
_PROXY_ENV_VARS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
)


@contextmanager
def _akshare_proxy_env():
    if get_config().get("akshare_trust_env", False):
        yield
        return

    saved = {name: os.environ.get(name) for name in _PROXY_ENV_VARS}
    for name in _PROXY_ENV_VARS:
        os.environ.pop(name, None)
    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _akshare_symbol(symbol: str) -> str:
    """Convert Yahoo-style A-share symbols to AKShare's six-digit code."""
    raw = symbol.strip().upper()
    if raw.endswith(_A_SHARE_SUFFIXES):
        raw = raw[:-3]
    if raw.isdigit() and len(raw) == 6:
        return raw
    raise NoMarketDataError(
        symbol,
        symbol,
        "AKShare adapter currently supports six-digit China A-share symbols",
    )


def _akshare_date(date_value: str) -> str:
    return datetime.strptime(date_value, "%Y-%m-%d").strftime("%Y%m%d")


def _load_akshare_ohlcv(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    code = _akshare_symbol(symbol)
    try:
        import akshare as ak
    except ImportError as exc:
        raise AkShareUnavailableError(
            "AKShare is not installed. Install it with `pip install akshare --upgrade`."
        ) from exc

    adjust = ""
    try:
        with _akshare_proxy_env():
            data = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=_akshare_date(start_date),
                end_date=_akshare_date(end_date),
                adjust=adjust,
            )
    except Exception as exc:
        raise AkShareUnavailableError(f"AKShare stock_zh_a_hist failed: {exc}") from exc

    if data is None or data.empty:
        raise NoMarketDataError(symbol, code, f"no rows between {start_date} and {end_date}")

    rename_map = {
        "日期": "Date",
        "开盘": "Open",
        "收盘": "Close",
        "最高": "High",
        "最低": "Low",
        "成交量": "Volume",
        "成交额": "Amount",
        "换手率": "Turnover",
    }
    data = data.rename(columns=rename_map)
    required = ["Date", "Open", "High", "Low", "Close", "Volume"]
    missing = [col for col in required if col not in data.columns]
    if missing:
        raise AkShareUnavailableError(
            f"AKShare response missing required columns: {', '.join(missing)}"
        )

    keep = [col for col in ["Date", "Open", "High", "Low", "Close", "Volume", "Amount", "Turnover"] if col in data.columns]
    data = data[keep].copy()
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    for col in [c for c in keep if c != "Date"]:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data = data.dropna(subset=["Date", "Close"]).sort_values("Date")

    if data.empty:
        raise NoMarketDataError(symbol, code, f"no usable rows between {start_date} and {end_date}")
    return data


def get_stock(symbol: str, start_date: str, end_date: str) -> str:
    """Return China A-share OHLCV data from AKShare as CSV text."""
    data = _load_akshare_ohlcv(symbol, start_date, end_date)
    code = _akshare_symbol(symbol)
    output = data.copy()
    output["Date"] = output["Date"].dt.strftime("%Y-%m-%d")
    header = f"# Stock data for {symbol.upper()} from AKShare ({code})\n"
    header += f"# Total records: {len(output)}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + output.to_csv(index=False)


_INDICATOR_DESCRIPTIONS = {
    "close_50_sma": "50 SMA: A medium-term trend indicator.",
    "close_200_sma": "200 SMA: A long-term trend benchmark.",
    "close_10_ema": "10 EMA: A responsive short-term average.",
    "macd": "MACD: Computes momentum via differences of EMAs.",
    "macds": "MACD Signal: An EMA smoothing of the MACD line.",
    "macdh": "MACD Histogram: Shows the gap between the MACD line and its signal.",
    "rsi": "RSI: Measures momentum to flag overbought/oversold conditions.",
    "boll": "Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands.",
    "boll_ub": "Bollinger Upper Band: Typically above the middle line.",
    "boll_lb": "Bollinger Lower Band: Typically below the middle line.",
    "atr": "ATR: Averages true range to measure volatility.",
    "vwma": "VWMA: A moving average weighted by volume.",
    "mfi": "MFI: Uses price and volume to measure buying and selling pressure.",
}


def get_indicator(symbol: str, indicator: str, curr_date: str, look_back_days: int) -> str:
    """Calculate a stockstats indicator from AKShare OHLCV data."""
    if indicator not in _INDICATOR_DESCRIPTIONS:
        raise ValueError(
            f"Indicator {indicator} is not supported. Please choose from: {list(_INDICATOR_DESCRIPTIONS.keys())}"
        )

    from stockstats import wrap

    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = curr_dt - relativedelta(days=max(look_back_days, 260))
    data = _load_akshare_ohlcv(
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
