from __future__ import annotations

import logging
import os
import random
import time
from collections.abc import Callable
from typing import Any

import pandas as pd

from tradingagents.dataflows.tushare_data import _ensure_tushare_client


LOGGER = logging.getLogger(__name__)

DAILY_FIELDS = "ts_code,trade_date,open,high,low,close,pct_chg,vol,amount"
DAILY_BASIC_FIELDS = "ts_code,trade_date,turnover_rate,volume_ratio,pe_ttm,pb,total_mv,circ_mv"
MONEYFLOW_FIELDS = (
    "ts_code,trade_date,buy_lg_amount,sell_lg_amount,"
    "buy_elg_amount,sell_elg_amount,net_mf_amount"
)


class TushareBatchClient:
    """Small retrying wrapper that only performs market-wide batch calls."""

    def __init__(self, config: dict[str, Any], pro: Any | None = None):
        fetch = config["fetch"]
        if not bool(fetch.get("trust_env_proxy", False)):
            for env_name in ("NO_PROXY", "no_proxy"):
                current = [item.strip() for item in os.environ.get(env_name, "").split(",") if item.strip()]
                if "api.tushare.pro" not in current:
                    current.append("api.tushare.pro")
                os.environ[env_name] = ",".join(current)
        self.pro = pro or _ensure_tushare_client()
        self.max_retries = int(fetch.get("max_retries", 3))
        self.backoff = float(fetch.get("retry_backoff_seconds", 1.0))
        self.inter_request_seconds = float(fetch.get("inter_request_seconds", 0.12))

    def _call(self, name: str, fn: Callable[[], pd.DataFrame]) -> pd.DataFrame:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                frame = fn()
                time.sleep(self.inter_request_seconds)
                if frame is None:
                    return pd.DataFrame()
                LOGGER.info("Tushare %s returned %s rows", name, len(frame))
                return frame
            except Exception as exc:  # noqa: BLE001 - vendor boundary
                last_error = exc
                LOGGER.warning("Tushare %s attempt %s failed: %s", name, attempt, exc)
                if attempt < self.max_retries:
                    time.sleep(self.backoff * (2 ** (attempt - 1)) + random.random() * 0.2)
        raise RuntimeError(f"Tushare {name} failed after {self.max_retries} attempts: {last_error}")

    def trade_calendar(self, start_date: str, end_date: str) -> pd.DataFrame:
        return self._call(
            "trade_cal",
            lambda: self.pro.trade_cal(
                exchange="SSE",
                start_date=start_date,
                end_date=end_date,
                fields="exchange,cal_date,is_open,pretrade_date",
            ),
        )

    def stock_basic(self) -> pd.DataFrame:
        return self._call(
            "stock_basic",
            lambda: self.pro.stock_basic(
                exchange="",
                list_status="L",
                fields="ts_code,symbol,name,area,industry,market,list_date",
            ),
        )

    def daily(self, trade_date: str) -> pd.DataFrame:
        return self._call("daily", lambda: self.pro.daily(trade_date=trade_date, fields=DAILY_FIELDS))

    def daily_basic(self, trade_date: str) -> pd.DataFrame:
        return self._call(
            "daily_basic",
            lambda: self.pro.daily_basic(trade_date=trade_date, fields=DAILY_BASIC_FIELDS),
        )

    def moneyflow(self, trade_date: str) -> pd.DataFrame:
        return self._call(
            "moneyflow",
            lambda: self.pro.moneyflow(trade_date=trade_date, fields=MONEYFLOW_FIELDS),
        )

    def block_trade(self, trade_date: str) -> pd.DataFrame:
        return self._call("block_trade", lambda: self.pro.block_trade(trade_date=trade_date))

    def sector_classification(self) -> pd.DataFrame:
        return self._call(
            "index_classify", lambda: self.pro.index_classify(level="L1", src="SW2021")
        )

    def sector_members(self) -> pd.DataFrame:
        return self._call("index_member_all", lambda: self.pro.index_member_all(is_new="Y"))
