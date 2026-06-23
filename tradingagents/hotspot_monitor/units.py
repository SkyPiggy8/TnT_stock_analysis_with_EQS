from __future__ import annotations

import pandas as pd


THOUSAND_YUAN_TO_YUAN = 1_000.0
TEN_THOUSAND_YUAN_TO_YUAN = 10_000.0
TEN_THOUSAND_SHARES_TO_SHARES = 10_000.0


def _numeric(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    result = frame.copy()
    for column in columns:
        if column in result.columns:
            result[column] = pd.to_numeric(result[column], errors="coerce")
    return result


def normalize_daily(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert Tushare ``daily.amount`` from thousand yuan to yuan."""

    result = _numeric(frame, ["open", "high", "low", "close", "pct_chg", "vol", "amount"])
    if "amount" in result:
        result["daily_amount_yuan"] = result["amount"] * THOUSAND_YUAN_TO_YUAN
    return result


def normalize_daily_basic(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert Tushare market-value fields from ten-thousand yuan to yuan."""

    result = _numeric(
        frame,
        ["turnover_rate", "volume_ratio", "pe_ttm", "pb", "total_mv", "circ_mv"],
    )
    for source, target in (("total_mv", "total_mv_yuan"), ("circ_mv", "circ_mv_yuan")):
        if source in result:
            result[target] = result[source] * TEN_THOUSAND_YUAN_TO_YUAN
    return result


def normalize_moneyflow(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert all Tushare moneyflow amount fields from ten-thousand yuan."""

    amount_columns = [column for column in frame.columns if column.endswith("_amount")]
    result = _numeric(frame, amount_columns)
    for column in amount_columns:
        result[f"{column}_yuan"] = result[column] * TEN_THOUSAND_YUAN_TO_YUAN
    return result


def normalize_block_trade(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert block-trade volume (10k shares) and amount (10k yuan)."""

    result = _numeric(frame, ["price", "vol", "amount"])
    if "vol" in result:
        result["block_vol_shares"] = result["vol"] * TEN_THOUSAND_SHARES_TO_SHARES
    if "amount" in result:
        result["block_amount_yuan"] = result["amount"] * TEN_THOUSAND_YUAN_TO_YUAN
    return result
