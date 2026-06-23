from __future__ import annotations

from pathlib import Path

import pandas as pd


def build_sector_mapping(
    stock_basic: pd.DataFrame,
    sector_members: pd.DataFrame | None,
    fallback_csv: str | Path | None = None,
) -> pd.DataFrame:
    """Build a one-row-per-stock sector mapping with deterministic fallbacks."""

    parts: list[pd.DataFrame] = []
    if sector_members is not None and not sector_members.empty:
        expected = ["ts_code", "l1_name", "l2_name"]
        if all(column in sector_members.columns for column in expected):
            sw = sector_members[expected].dropna(subset=["ts_code"]).copy()
            sw = sw.rename(columns={"l1_name": "sector_level_1", "l2_name": "sector_level_2"})
            parts.append(sw.drop_duplicates("ts_code", keep="first"))

    if fallback_csv:
        path = Path(fallback_csv)
        if path.exists():
            local = pd.read_csv(path, dtype=str)
            if "ts_code" in local.columns:
                keep = [
                    column
                    for column in ("ts_code", "sector_level_1", "sector_level_2", "concept_tags")
                    if column in local.columns
                ]
                parts.insert(0, local[keep].drop_duplicates("ts_code", keep="first"))

    base = stock_basic[["ts_code", "industry"]].copy()
    base["sector_level_1"] = base["industry"].fillna("未分类")
    base["sector_level_2"] = base["industry"].fillna("未分类")
    base = base.drop(columns=["industry"])
    for mapping in reversed(parts):
        base = base.merge(mapping, on="ts_code", how="left", suffixes=("", "_mapped"))
        for column in ("sector_level_1", "sector_level_2"):
            mapped = f"{column}_mapped"
            if mapped in base:
                base[column] = base[mapped].fillna(base[column])
                base = base.drop(columns=[mapped])
        if "concept_tags" in mapping and "concept_tags" not in base:
            base["concept_tags"] = ""
    return base.drop_duplicates("ts_code", keep="first")


def score_sectors(
    stocks: pd.DataFrame,
    flow_threshold: float,
    volume_threshold: float,
    min_stock_count: int = 5,
    min_triggered_stock_count: int = 2,
) -> pd.DataFrame:
    """Aggregate triggered stocks into the documented sector-resonance score."""

    if stocks.empty:
        return pd.DataFrame()
    frame = stocks.copy()
    frame["triggered"] = frame["any_signal"].astype(bool)
    frame["block_premium_flag"] = frame["signal_block_premium"].astype(bool)
    grouped = frame.groupby("sector_level_1", dropna=False)
    result = grouped.agg(
        stock_count=("ts_code", "nunique"),
        triggered_stock_count=("triggered", "sum"),
        avg_net_flow_ratio=("net_flow_ratio", "mean"),
        avg_big_elg_flow_ratio=("big_elg_flow_ratio", "mean"),
        avg_pct_chg=("pct_chg", "mean"),
        avg_amount_ratio_20=("amount_ratio_20", "mean"),
        block_premium_count=("block_premium_flag", "sum"),
    ).reset_index().rename(columns={"sector_level_1": "sector_name"})
    result["triggered_ratio"] = result["triggered_stock_count"] / result["stock_count"].clip(lower=1)
    result = result[
        (result["stock_count"] >= min_stock_count)
        & (result["triggered_stock_count"] >= min_triggered_stock_count)
    ].copy()
    result["sector_score"] = (
        0.30 * (result["triggered_ratio"].clip(0, 1) * 100)
        + 0.25 * (result["avg_net_flow_ratio"].clip(lower=0) / flow_threshold * 50).clip(0, 100)
        + 0.20 * (result["avg_pct_chg"].clip(lower=0) / 5.0 * 100).clip(0, 100)
        + 0.15 * (result["avg_amount_ratio_20"].clip(lower=0) / volume_threshold * 50).clip(0, 100)
        + 0.10 * (result["block_premium_count"] / result["stock_count"].clip(lower=1) * 100)
    ).clip(0, 100)
    return result.sort_values(["sector_score", "triggered_stock_count"], ascending=False).reset_index(drop=True)
