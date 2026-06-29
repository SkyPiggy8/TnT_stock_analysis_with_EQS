from __future__ import annotations

import logging
import json
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from .backtest import run_basic_backtest, write_backtest_reports
from .client import TushareBatchClient
from .config import load_hotspot_config
from .reports import generate_daily_reports
from .scoring import score_stocks
from .sectors import build_sector_mapping, score_sectors
from .signals import calculate_stock_signals
from .store import HotspotStore
from .units import normalize_daily, normalize_daily_basic
from .universe import filter_universe


LOGGER = logging.getLogger(__name__)
ProgressCallback = Callable[[str, int, int, str], None]


def _date_key(value: str | datetime) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y%m%d")
    raw = str(value).strip().replace("-", "").replace("/", "")
    return datetime.strptime(raw, "%Y%m%d").strftime("%Y%m%d")


def _records(frame: pd.DataFrame, limit: int | None = None) -> list[dict[str, Any]]:
    view = frame.head(limit) if limit else frame
    return json.loads(view.to_json(orient="records", date_format="iso")) if not view.empty else []


class HotspotMonitor:
    """Orchestrate batch data collection, scoring, reports and backtests."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        client: TushareBatchClient | None = None,
        store: HotspotStore | None = None,
    ):
        self.config = config or load_hotspot_config()
        self.client = client or TushareBatchClient(self.config)
        self.store = store or HotspotStore(self.config)

    def _progress(self, callback: ProgressCallback | None, stage: str, current: int, total: int, message: str) -> None:
        LOGGER.info("[%s] %s/%s %s", stage, current, total, message)
        if callback:
            callback(stage, current, total, message)

    def _calendar(self, start_date: str, end_date: str) -> list[str]:
        frame = self.client.trade_calendar(start_date, end_date)
        if frame.empty or not {"cal_date", "is_open"}.issubset(frame.columns):
            raise RuntimeError("Tushare trade_cal returned no usable calendar")
        return sorted(frame.loc[pd.to_numeric(frame["is_open"], errors="coerce") == 1, "cal_date"].astype(str).tolist())

    def resolve_trade_date(self, requested: str | None = None) -> str:
        target = _date_key(requested or datetime.now())
        end = datetime.strptime(target, "%Y%m%d")
        start = (end - timedelta(days=20)).strftime("%Y%m%d")
        open_dates = [date for date in self._calendar(start, target) if date <= target]
        if not open_dates:
            raise RuntimeError(f"No open trading date found on or before {target}")
        return open_dates[-1]

    def trading_dates(
        self,
        start_date: str | datetime,
        end_date: str | datetime,
    ) -> list[str]:
        """Return exchange-open dates for calendar selection."""

        start, end = _date_key(start_date), _date_key(end_date)
        if start > end:
            raise ValueError("start_date must not be after end_date")
        return self._calendar(start, end)

    def _history_dates(self, trade_date: str, count: int | None = None) -> list[str]:
        history_days = int(count or self.config["storage"]["history_days"])
        end = datetime.strptime(trade_date, "%Y%m%d")
        start = (end - timedelta(days=max(history_days * 2 + 60, 365))).strftime("%Y%m%d")
        dates = [date for date in self._calendar(start, trade_date) if date <= trade_date]
        return dates[-history_days:]

    def _fetch_date(self, trade_date: str, *, include_block: bool, force: bool = False) -> None:
        use_cache = bool(self.config["storage"].get("use_cache", True)) and not force
        calls = {
            "daily": self.client.daily,
            "daily_basic": self.client.daily_basic,
            "moneyflow": self.client.moneyflow,
        }
        if include_block:
            calls["block_trade"] = self.client.block_trade
        for interface, fn in calls.items():
            if use_cache and self.store.has_raw(interface, trade_date):
                cached = self.store.read_raw(interface, trade_date)
                # A market-wide empty daily file usually means the scan ran
                # before Tushare published end-of-day data.  Never treat it as
                # a durable cache hit. Empty block_trade is normally valid,
                # except when today's file was cached before the close.
                raw_path = self.store.raw_path(interface, trade_date)
                cached_before_close = (
                    interface == "block_trade"
                    and cached.empty
                    and trade_date == datetime.now().strftime("%Y%m%d")
                    and datetime.fromtimestamp(raw_path.stat().st_mtime).hour < 16
                    and datetime.now().hour >= 16
                )
                empty_market_cache = (
                    interface in {"daily", "daily_basic", "moneyflow"} and cached.empty
                )
                if not empty_market_cache and not cached_before_close:
                    continue
            frame = fn(trade_date)
            if interface in {"daily", "daily_basic"} and frame.empty:
                raise RuntimeError(
                    f"Tushare {interface} returned no rows for {trade_date}; "
                    "end-of-day data may not be published yet"
                )
            self.store.write_raw(interface, trade_date, frame)

    def _metadata(self, trade_date: str, force: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
        for interface, fn in (
            ("stock_basic", self.client.stock_basic),
            ("sector_members", self.client.sector_members),
        ):
            if force or not self.store.has_raw(interface, trade_date):
                self.store.write_raw(interface, trade_date, fn())
        stocks = self.store.read_raw("stock_basic", trade_date)
        members = self.store.read_raw("sector_members", trade_date)
        fallback = Path(self.config["project_root"]) / "config" / "sector_mapping.csv"
        sectors = build_sector_mapping(stocks, members, fallback)
        return stocks, sectors

    def update_history(
        self,
        start_date: str,
        end_date: str,
        *,
        force: bool = False,
        include_blocks: bool = True,
        progress: ProgressCallback | None = None,
    ) -> list[str]:
        start, end = _date_key(start_date), _date_key(end_date)
        dates = self._calendar(start, end)
        total = len(dates)
        for index, trade_date in enumerate(dates, 1):
            self._progress(progress, "history", index, total, f"缓存 {trade_date}")
            self._fetch_date(trade_date, include_block=include_blocks, force=force)
        if dates:
            self._metadata(dates[-1], force=force)
        return dates

    def _calculate(
        self,
        trade_date: str,
        history_dates: list[str],
        stock_basic: pd.DataFrame,
        sectors: pd.DataFrame,
    ) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
        daily = self.store.read_many("daily", history_dates)
        basic = self.store.read_many("daily_basic", history_dates)
        money = self.store.read_many("moneyflow", history_dates)
        blocks = self.store.read_raw("block_trade", trade_date)
        signals = calculate_stock_signals(daily, basic, money, blocks, trade_date, self.config)
        target_daily = normalize_daily(daily[daily["trade_date"].astype(str) == trade_date])
        target_basic = normalize_daily_basic(basic[basic["trade_date"].astype(str) == trade_date])
        universe, universe_stats = filter_universe(
            stock_basic, target_daily, target_basic, trade_date, self.config
        )
        metadata = universe[["ts_code", "name", "market", "industry"]].drop_duplicates("ts_code")
        signals = signals[signals["ts_code"].isin(universe["ts_code"])].merge(
            metadata, on="ts_code", how="left", validate="one_to_one"
        )
        signals = signals.merge(sectors, on="ts_code", how="left", validate="one_to_one")
        signals["sector_level_1"] = signals["sector_level_1"].fillna(signals["industry"]).fillna("未分类")
        signals["sector_level_2"] = signals["sector_level_2"].fillna(signals["sector_level_1"])
        money_cfg = self.config["signals"]["moneyflow"]
        volume_threshold = float(self.config["signals"]["technical"]["volume_ratio_threshold"])
        sector_scores = score_sectors(
            signals,
            float(money_cfg["net_flow_ratio_threshold"]),
            volume_threshold,
            int(self.config["signals"]["sector"].get("min_stock_count", 5)),
            int(self.config["signals"]["sector"].get("min_triggered_stock_count", 2)),
        )
        scored = score_stocks(signals, sector_scores, self.config)
        coverage = float(scored["net_mf_amount_yuan"].notna().mean()) if len(scored) else 0.0
        summary = {
            **universe_stats,
            "tradeDate": trade_date,
            "triggeredStocks": int(scored["any_signal"].sum()) if len(scored) else 0,
            "moneyflowCoverage": coverage,
            "blockTradeStocks": int((scored["block_trade_count"] > 0).sum()) if len(scored) else 0,
            "qualityWarningStocks": int((scored["data_quality_flags"] != "").sum()) if len(scored) else 0,
        }
        return scored, sector_scores, summary

    def scan(
        self,
        trade_date: str | None = None,
        *,
        force: bool = False,
        refresh_target: bool = False,
        export_markdown: bool = True,
        export_excel: bool = True,
        progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        effective = self.resolve_trade_date(trade_date)
        self.store.record_run(effective, "running")
        try:
            dates = self._history_dates(effective)
            total = len(dates)
            for index, date in enumerate(dates, 1):
                self._progress(progress, "download", index, total, f"准备 {date}")
                self._fetch_date(
                    date,
                    include_block=date == effective,
                    force=force or (refresh_target and date == effective),
                )
            stock_basic, sectors = self._metadata(effective, force=force)
            self._progress(progress, "calculate", 1, 1, "计算全市场信号与行业共振")
            stocks, sector_scores, summary = self._calculate(effective, dates, stock_basic, sectors)
            self.store.save_frame("daily_signals", effective, stocks)
            self.store.save_frame("sector_scores", effective, sector_scores)
            quality = stocks.loc[
                stocks["data_quality_flags"].astype(str) != "",
                ["ts_code", "data_quality_flags"],
            ]
            self.store.save_frame("data_quality_flags", effective, quality)
            report_paths = generate_daily_reports(effective, summary, stocks, sector_scores, self.config)
            if not export_markdown:
                Path(report_paths["markdown"]).unlink(missing_ok=True)
                report_paths.pop("markdown", None)
            if not export_excel:
                Path(report_paths["excel"]).unlink(missing_ok=True)
                report_paths.pop("excel", None)
            summary["reportPaths"] = report_paths
            self.store.record_run(effective, "complete", summary=summary)
            return self.load_result(effective)
        except Exception as exc:
            self.store.record_run(effective, "failed", error=f"{type(exc).__name__}: {exc}")
            raise

    def load_result(self, trade_date: str | None = None) -> dict[str, Any]:
        dates = self.store.available_dates()
        effective = _date_key(trade_date) if trade_date else (dates[0] if dates else "")
        if not effective:
            return {"tradeDate": "", "summary": {}, "sectors": [], "stocks": [], "blockTrades": [], "moneyflowTop": []}
        stocks = self.store.load_frame("daily_signals", effective)
        sectors = self.store.load_frame("sector_scores", effective)
        top_n = int(self.config["scoring"]["stock_top_n"])
        triggered = stocks[stocks["any_signal"].astype(bool)] if not stocks.empty else stocks
        blocks = stocks[stocks["block_trade_count"] > 0].sort_values("block_vwap_premium", ascending=False) if not stocks.empty else stocks
        money = stocks.sort_values("net_flow_ratio", ascending=False) if not stocks.empty else stocks
        return {
            "tradeDate": effective,
            "summary": self.store.load_summary(effective),
            "sectors": _records(sectors, int(self.config["scoring"]["sector_top_n"])),
            "stocks": _records(triggered, top_n),
            "blockTrades": _records(blocks, top_n),
            "moneyflowTop": _records(money, top_n),
        }

    def backtest(
        self,
        start_date: str,
        end_date: str,
        *,
        holding_days: list[int] | None = None,
        progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        start, end = _date_key(start_date), _date_key(end_date)
        history_start = (datetime.strptime(start, "%Y%m%d") - timedelta(days=365)).strftime("%Y%m%d")
        all_dates = self.update_history(history_start, end, include_blocks=True, progress=progress)
        target_dates = [date for date in all_dates if start <= date <= end]
        stock_basic, sectors = self._metadata(end)
        signal_frames = []
        history_count = int(self.config["storage"]["history_days"])
        for index, date in enumerate(target_dates, 1):
            self._progress(progress, "backtest", index, len(target_dates), f"计算 {date} 信号")
            position = all_dates.index(date)
            lookback = all_dates[max(0, position - history_count + 1):position + 1]
            stocks, _, _ = self._calculate(date, lookback, stock_basic, sectors)
            signal_frames.append(stocks[stocks["any_signal"].astype(bool)])
        signals = pd.concat(signal_frames, ignore_index=True) if signal_frames else pd.DataFrame()
        daily = self.store.read_many("daily", all_dates)
        days = holding_days or [int(value) for value in self.config["backtest"]["holding_days"]]
        trades, metrics = run_basic_backtest(signals, daily, days)
        if not metrics.empty:
            self.store.save_frame("backtest_metrics", end, metrics)
        paths = write_backtest_reports(
            start,
            end,
            trades,
            metrics,
            Path(self.config["storage"]["report_dir"]),
        )
        return {"startDate": start, "endDate": end, "metrics": _records(metrics), "tradeCount": len(trades), "reportPaths": paths}


def run_daily_scan(trade_date: str | None = None, config_path: str | Path | None = None) -> dict[str, Any]:
    return HotspotMonitor(load_hotspot_config(config_path)).scan(trade_date)
