from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .units import normalize_block_trade, normalize_daily, normalize_daily_basic, normalize_moneyflow


def _validate_unique(frame: pd.DataFrame, keys: list[str], name: str) -> None:
    if frame.empty:
        return
    duplicates = frame.duplicated(keys, keep=False)
    if duplicates.any():
        sample = frame.loc[duplicates, keys].head(3).to_dict("records")
        raise ValueError(f"{name} contains duplicate keys {keys}: {sample}")


def _prior_rolling(series: pd.Series, window: int, operation: str) -> pd.Series:
    shifted = series.shift(1)
    rolling = shifted.rolling(window, min_periods=max(5, window // 3))
    if operation == "mean":
        return rolling.mean()
    if operation == "std":
        return rolling.std(ddof=0)
    if operation == "max":
        return rolling.max()
    raise ValueError(operation)


def _prior_percentile(series: pd.Series, window: int) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    output = np.full(len(values), np.nan)
    minimum = max(5, window // 3)
    for index, current in enumerate(values):
        previous = values[max(0, index - window):index]
        previous = previous[np.isfinite(previous)]
        if np.isfinite(current) and len(previous) >= minimum:
            output[index] = float(np.mean(previous <= current))
    return pd.Series(output, index=series.index)


def aggregate_block_trades(block_trade: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    """Aggregate multiple block trades for each stock and trading day."""

    if block_trade is None or block_trade.empty:
        return pd.DataFrame(columns=["ts_code", "trade_date"])
    block = normalize_block_trade(block_trade)
    required = {"ts_code", "trade_date", "price", "block_vol_shares", "block_amount_yuan"}
    missing = required - set(block.columns)
    if missing:
        raise ValueError(f"block_trade missing columns: {sorted(missing)}")
    block["weighted_price"] = block["price"] * block["block_vol_shares"]
    for column in ("buyer", "seller"):
        if column not in block:
            block[column] = ""

    def joined(values: pd.Series) -> str:
        return "；".join(dict.fromkeys(str(value).strip() for value in values.dropna() if str(value).strip()))

    aggregated = block.groupby(["ts_code", "trade_date"], as_index=False).agg(
        block_trade_count=("price", "size"),
        block_total_amount_yuan=("block_amount_yuan", "sum"),
        block_total_vol=("block_vol_shares", "sum"),
        weighted_price=("weighted_price", "sum"),
        block_max_price=("price", "max"),
        block_min_price=("price", "min"),
        buyer_list=("buyer", joined),
        seller_list=("seller", joined),
    )
    aggregated["block_vwap_price"] = aggregated["weighted_price"] / aggregated["block_total_vol"].replace(0, np.nan)
    aggregated = aggregated.drop(columns=["weighted_price"])
    close = normalize_daily(daily)[["ts_code", "trade_date", "close", "daily_amount_yuan"]]
    close = close.drop_duplicates(["ts_code", "trade_date"])
    aggregated = aggregated.merge(close, on=["ts_code", "trade_date"], how="left", validate="one_to_one")
    aggregated["block_vwap_premium"] = aggregated["block_vwap_price"] / aggregated["close"] - 1
    aggregated["block_amount_ratio"] = aggregated["block_total_amount_yuan"] / aggregated["daily_amount_yuan"].replace(0, np.nan)
    return aggregated


def calculate_stock_signals(
    daily: pd.DataFrame,
    daily_basic: pd.DataFrame,
    moneyflow: pd.DataFrame,
    block_trade: pd.DataFrame,
    trade_date: str,
    config: dict[str, Any],
) -> pd.DataFrame:
    """Calculate historical features and return the requested trading-day rows."""

    daily_n = normalize_daily(daily)
    basic_n = normalize_daily_basic(daily_basic)
    money_n = normalize_moneyflow(moneyflow)
    keys = ["ts_code", "trade_date"]
    _validate_unique(daily_n, keys, "daily")
    _validate_unique(basic_n, keys, "daily_basic")
    _validate_unique(money_n, keys, "moneyflow")

    frame = daily_n.merge(basic_n, on=keys, how="left", validate="one_to_one", suffixes=("", "_basic"))
    if money_n.empty:
        for column in (
            "net_mf_amount_yuan", "buy_lg_amount_yuan", "sell_lg_amount_yuan",
            "buy_elg_amount_yuan", "sell_elg_amount_yuan",
        ):
            frame[column] = np.nan
    else:
        frame = frame.merge(money_n, on=keys, how="left", validate="one_to_one")
    frame["trade_date"] = frame["trade_date"].astype(str)
    frame = frame.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    frame["data_quality_flags"] = np.where(frame["net_mf_amount_yuan"].isna(), "MISSING_MONEYFLOW", "")

    for column in (
        "net_mf_amount_yuan",
        "buy_lg_amount_yuan",
        "sell_lg_amount_yuan",
        "buy_elg_amount_yuan",
        "sell_elg_amount_yuan",
    ):
        if column not in frame:
            frame[column] = np.nan
    frame["big_elg_net_amount_yuan"] = (
        frame["buy_lg_amount_yuan"]
        + frame["buy_elg_amount_yuan"]
        - frame["sell_lg_amount_yuan"]
        - frame["sell_elg_amount_yuan"]
    )
    frame["net_flow_ratio"] = frame["net_mf_amount_yuan"] / frame["daily_amount_yuan"].replace(0, np.nan)
    frame["big_elg_flow_ratio"] = frame["big_elg_net_amount_yuan"] / frame["daily_amount_yuan"].replace(0, np.nan)

    money_cfg = config["signals"]["moneyflow"]
    short = int(money_cfg["short_window"])
    long = int(money_cfg["long_window"])
    technical = config["signals"]["technical"]
    groups = frame.groupby("ts_code", group_keys=False)
    for column, prefix in (("net_flow_ratio", "net_flow"), ("big_elg_flow_ratio", "big_elg_flow")):
        for window in (short, long):
            mean = groups[column].transform(lambda series, w=window: _prior_rolling(series, w, "mean"))
            std = groups[column].transform(lambda series, w=window: _prior_rolling(series, w, "std"))
            frame[f"{prefix}_zscore_{window}"] = (frame[column] - mean) / std.replace(0, np.nan)
        frame[f"{prefix}_percentile_{long}"] = groups[column].transform(
            lambda series: _prior_percentile(series, long)
        )

    volume_window = int(technical["volume_window"])
    previous_amount = groups["daily_amount_yuan"].transform(
        lambda series: _prior_rolling(series, volume_window, "mean")
    )
    frame["amount_ratio_20"] = frame["daily_amount_yuan"] / previous_amount.replace(0, np.nan)
    for window in technical["ma_windows"]:
        frame[f"ma{window}"] = groups["close"].transform(
            lambda series, w=int(window): series.rolling(w, min_periods=w).mean()
        )
        frame[f"close_above_ma{window}"] = frame["close"] >= frame[f"ma{window}"]
    rolling_high = groups["close"].transform(
        lambda series: series.rolling(long, min_periods=min(20, long)).max()
    )
    frame["close_position_60"] = frame["close"] / rolling_high.replace(0, np.nan)

    current = frame[frame["trade_date"] == trade_date].copy()
    blocks = aggregate_block_trades(block_trade, daily_n[daily_n["trade_date"].astype(str) == trade_date])
    if not blocks.empty:
        current = current.merge(blocks, on=keys, how="left", validate="one_to_one", suffixes=("", "_block"))
    defaults = {
        "block_trade_count": 0,
        "block_total_amount_yuan": 0.0,
        "block_vwap_price": np.nan,
        "block_vwap_premium": np.nan,
        "block_amount_ratio": 0.0,
        "buyer_list": "",
        "seller_list": "",
    }
    for column, default in defaults.items():
        if column not in current:
            current[column] = default
        else:
            current[column] = current[column].fillna(default)

    block_cfg = config["signals"]["block_trade"]
    fixed = float(money_cfg["net_flow_ratio_threshold"])
    big_fixed = float(money_cfg["big_elg_flow_ratio_threshold"])
    z_threshold = float(money_cfg["zscore_threshold"])
    p_threshold = float(money_cfg["percentile_threshold"])
    current["signal_moneyflow_net"] = (
        (current["net_flow_ratio"] >= fixed)
        | (current[f"net_flow_zscore_{long}"] >= z_threshold)
        | (current[f"net_flow_percentile_{long}"] >= p_threshold)
    )
    current["signal_moneyflow_big_elg"] = (
        (current["big_elg_flow_ratio"] >= big_fixed)
        | (current[f"big_elg_flow_zscore_{long}"] >= z_threshold)
        | (current[f"big_elg_flow_percentile_{long}"] >= p_threshold)
    )
    current["signal_block_premium"] = (
        (current["block_vwap_premium"] >= float(block_cfg["premium_threshold"]))
        & (current["block_total_amount_yuan"] >= float(block_cfg["min_amount_yuan"]))
    )
    current["signal_block_amount"] = current["block_amount_ratio"] >= float(block_cfg["amount_ratio_threshold"])
    current["signal_volume_expand"] = current["amount_ratio_20"] >= float(technical["volume_ratio_threshold"])
    ma_columns = [f"close_above_ma{int(window)}" for window in technical["ma_windows"]]
    current["signal_ma_confirm"] = current[ma_columns].all(axis=1)
    capital_signal = current[
        ["signal_moneyflow_net", "signal_moneyflow_big_elg", "signal_block_premium", "signal_block_amount"]
    ].any(axis=1)
    confirmed_volume = current["signal_volume_expand"] & current["signal_ma_confirm"] & (current["pct_chg"] > 0)
    current["any_signal"] = capital_signal | confirmed_volume
    return current.reset_index(drop=True)
