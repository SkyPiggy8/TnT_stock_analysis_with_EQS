from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _ratio_score(series: pd.Series, threshold: float) -> pd.Series:
    return (pd.to_numeric(series, errors="coerce").clip(lower=0) / threshold * 50).clip(0, 100).fillna(0)


def _percentile_score(series: pd.Series, threshold: float) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    return ((values - 0.5) / max(threshold - 0.5, 0.01) * 100).clip(0, 100).fillna(0)


def score_stocks(stocks: pd.DataFrame, sector_scores: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Apply the fixed balanced score and return strongest rows first."""

    if stocks.empty:
        return stocks.copy()
    result = stocks.copy()
    money = config["signals"]["moneyflow"]
    block = config["signals"]["block_trade"]
    technical = config["signals"]["technical"]
    long = int(money["long_window"])
    z_threshold = float(money["zscore_threshold"])
    p_threshold = float(money["percentile_threshold"])

    result["moneyflow_score"] = pd.concat(
        [
            _ratio_score(result["net_flow_ratio"], float(money["net_flow_ratio_threshold"])),
            _ratio_score(result[f"net_flow_zscore_{long}"], z_threshold),
            _percentile_score(result[f"net_flow_percentile_{long}"], p_threshold),
        ],
        axis=1,
    ).mean(axis=1)
    result["big_elg_score"] = pd.concat(
        [
            _ratio_score(result["big_elg_flow_ratio"], float(money["big_elg_flow_ratio_threshold"])),
            _ratio_score(result[f"big_elg_flow_zscore_{long}"], z_threshold),
            _percentile_score(result[f"big_elg_flow_percentile_{long}"], p_threshold),
        ],
        axis=1,
    ).mean(axis=1)
    result["block_trade_score"] = pd.concat(
        [
            _ratio_score(result["block_vwap_premium"], float(block["premium_threshold"])),
            _ratio_score(result["block_amount_ratio"], float(block["amount_ratio_threshold"])),
        ],
        axis=1,
    ).mean(axis=1)
    result["liquidity_score"] = _ratio_score(
        result["amount_ratio_20"], float(technical["volume_ratio_threshold"])
    )
    ma_columns = [f"close_above_ma{int(window)}" for window in technical["ma_windows"]]
    ma_score = result[ma_columns].fillna(False).astype(float).mean(axis=1) * 70
    position_score = pd.to_numeric(result["close_position_60"], errors="coerce").clip(0, 1) * 30
    result["technical_score"] = (ma_score + position_score).clip(0, 100)

    sector_map = sector_scores[["sector_name", "sector_score"]] if not sector_scores.empty else pd.DataFrame(columns=["sector_name", "sector_score"])
    result = result.merge(
        sector_map,
        left_on="sector_level_1",
        right_on="sector_name",
        how="left",
    ).drop(columns=["sector_name"], errors="ignore")
    result["sector_score"] = result["sector_score"].fillna(0)
    weights = config["scoring"]
    result["stock_score"] = (
        float(weights["moneyflow_weight"]) * result["moneyflow_score"]
        + float(weights["big_elg_weight"]) * result["big_elg_score"]
        + float(weights["block_trade_weight"]) * result["block_trade_score"]
        + float(weights["liquidity_weight"]) * result["liquidity_score"]
        + float(weights["technical_weight"]) * result["technical_score"]
        + float(weights["sector_weight"]) * result["sector_score"]
    ).clip(0, 100)
    codes = result["ts_code"].astype(str).str.split(".").str[0]
    limit_down_threshold = np.where(codes.str.startswith(("30", "68")), -19.5, -9.5)
    result["risk_flags"] = np.where(
        pd.to_numeric(result["pct_chg"], errors="coerce") <= limit_down_threshold,
        "NEAR_LIMIT_DOWN",
        "",
    )
    risk_multiplier = float(technical.get("limit_down_risk_multiplier", 0.25))
    result.loc[result["risk_flags"] != "", "stock_score"] *= risk_multiplier

    signal_columns = [column for column in result.columns if column.startswith("signal_")]
    result["signal_summary"] = result.apply(
        lambda row: ", ".join(column.removeprefix("signal_") for column in signal_columns if bool(row[column])) or "none",
        axis=1,
    )
    return result.sort_values(
        ["any_signal", "stock_score", "daily_amount_yuan"], ascending=[False, False, False]
    ).reset_index(drop=True)
