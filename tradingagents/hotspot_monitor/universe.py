from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd


def filter_universe(
    stock_basic: pd.DataFrame,
    daily_snapshot: pd.DataFrame,
    basic_snapshot: pd.DataFrame,
    trade_date: str,
    config: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Return the configured liquid Shanghai/Shenzhen research universe."""

    rules = config["universe"]
    stocks = stock_basic.copy()
    initial = len(stocks)
    stocks["ts_code"] = stocks["ts_code"].astype(str).str.upper()
    stocks["name"] = stocks.get("name", "").fillna("").astype(str)
    stocks["market"] = stocks.get("market", "").fillna("").astype(str)

    if rules.get("exclude_bse", True):
        stocks = stocks[~stocks["ts_code"].str.endswith(".BJ")]
    if rules.get("exclude_st", True):
        stocks = stocks[~stocks["name"].str.upper().str.contains(r"ST|PT", regex=True)]
    include_markets = set(rules.get("include_markets") or [])
    if include_markets:
        stocks = stocks[stocks["market"].isin(include_markets)]

    analysis_dt = pd.Timestamp(datetime.strptime(trade_date, "%Y%m%d"))
    list_dates = pd.to_datetime(stocks.get("list_date"), format="%Y%m%d", errors="coerce")
    stocks = stocks[(analysis_dt - list_dates).dt.days >= int(rules.get("min_listing_days", 60))]

    current_daily = daily_snapshot[["ts_code", "daily_amount_yuan"]].drop_duplicates("ts_code")
    current_basic = basic_snapshot[["ts_code", "circ_mv_yuan"]].drop_duplicates("ts_code")
    stocks = stocks.merge(current_daily, on="ts_code", how="inner", validate="one_to_one")
    stocks = stocks.merge(current_basic, on="ts_code", how="left", validate="one_to_one")
    before_liquidity = len(stocks)
    stocks = stocks[
        (stocks["daily_amount_yuan"] >= float(rules.get("min_daily_amount_yuan", 0)))
        & (stocks["circ_mv_yuan"] >= float(rules.get("min_circ_mv_yuan", 0)))
    ]
    return stocks.reset_index(drop=True), {
        "listedStocks": initial,
        "beforeLiquidity": before_liquidity,
        "eligibleStocks": len(stocks),
    }
