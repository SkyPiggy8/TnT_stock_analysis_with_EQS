from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def _limit_threshold(ts_code: str) -> float:
    code = str(ts_code).split(".")[0]
    return 0.195 if code.startswith(("30", "68")) else 0.095


def run_basic_backtest(
    signals: pd.DataFrame,
    daily: pd.DataFrame,
    holding_days: list[int],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Backtest close-confirmed signals with next-session open execution."""

    if signals.empty or daily.empty:
        return pd.DataFrame(), pd.DataFrame()
    prices = daily.copy().sort_values(["ts_code", "trade_date"])
    prices["trade_date"] = prices["trade_date"].astype(str)
    market_dates = sorted(prices["trade_date"].unique().tolist())
    market_date_index = {date: index for index, date in enumerate(market_dates)}
    grouped = {
        ticker: group.set_index("trade_date", drop=False)
        for ticker, group in prices.groupby("ts_code")
    }
    records: list[dict[str, Any]] = []
    for _, signal in signals[signals["any_signal"].astype(bool)].iterrows():
        ticker = signal["ts_code"]
        history = grouped.get(ticker)
        if history is None:
            continue
        signal_date = str(signal["trade_date"])
        signal_index = market_date_index.get(signal_date)
        if signal_index is None or signal_index + 1 >= len(market_dates) or signal_date not in history.index:
            continue
        entry_date = market_dates[signal_index + 1]
        signal_close = float(history.loc[signal_date]["close"])
        entry = history.loc[entry_date] if entry_date in history.index else None
        entry_open = float(entry["open"]) if entry is not None else np.nan
        entry_warning = "SUSPENDED_ENTRY" if entry is None else ""
        threshold = _limit_threshold(ticker)
        if entry is not None and entry_open >= signal_close * (1 + threshold):
            entry_warning = "LIMIT_UP_ENTRY"
        record = {
            "trade_date": signal_date,
            "ts_code": ticker,
            "sector_level_1": signal.get("sector_level_1", "未分类"),
            "circ_mv_yuan": signal.get("circ_mv_yuan", np.nan),
            "stock_score": signal.get("stock_score", np.nan),
            "entry_date": entry_date,
            "entry_price": entry_open,
            "entry_warning": entry_warning,
            "warning": entry_warning,
        }
        for days in holding_days:
            exit_index = signal_index + int(days)
            if exit_index >= len(market_dates):
                record[f"return_{days}d"] = np.nan
                record[f"exit_date_{days}d"] = ""
                record[f"exit_warning_{days}d"] = "NO_FUTURE_DATA"
                continue
            exit_date = market_dates[exit_index]
            record[f"exit_date_{days}d"] = exit_date
            if entry is None or exit_date not in history.index:
                record[f"return_{days}d"] = np.nan
                record[f"exit_warning_{days}d"] = "SUSPENDED_EXIT"
                continue
            exit_row = history.loc[exit_date]
            previous_date = market_dates[exit_index - 1]
            previous_close = (
                float(history.loc[previous_date]["close"])
                if previous_date in history.index
                else np.nan
            )
            exit_close = float(exit_row["close"])
            record[f"return_{days}d"] = exit_close / entry_open - 1
            record[f"exit_warning_{days}d"] = (
                "LIMIT_DOWN_EXIT"
                if np.isfinite(previous_close) and exit_close <= previous_close * (1 - threshold)
                else ""
            )
        records.append(record)
    trades = pd.DataFrame(records)
    if trades.empty:
        return trades, pd.DataFrame()
    cap = pd.to_numeric(trades["circ_mv_yuan"], errors="coerce")
    trades["market_cap_group"] = pd.cut(
        cap,
        bins=[-np.inf, 5e9, 2e10, np.inf],
        labels=["<50亿", "50-200亿", ">=200亿"],
    ).astype("string").fillna("未知")
    metrics: list[dict[str, Any]] = []

    def append_metrics(group: pd.DataFrame, group_type: str, group_value: str) -> None:
        for days in holding_days:
            valid = group[
                (group["entry_warning"] == "")
                & (group[f"exit_warning_{days}d"] == "")
            ]
            returns = valid[f"return_{days}d"].dropna()
            metrics.append(
                {
                    "group_type": group_type,
                    "group_value": group_value,
                    "holding_days": days,
                    "trigger_count": len(returns),
                    "average_return": returns.mean() if len(returns) else np.nan,
                    "win_rate": (returns > 0).mean() if len(returns) else np.nan,
                    "max_loss": returns.min() if len(returns) else np.nan,
                }
            )

    append_metrics(trades, "all", "全部")
    for sector, group in trades.groupby("sector_level_1", dropna=False):
        append_metrics(group, "sector", str(sector))
    for cap_group, group in trades.groupby("market_cap_group", observed=True):
        append_metrics(group, "market_cap", str(cap_group))
    return trades, pd.DataFrame(metrics)


def write_backtest_reports(
    start_date: str,
    end_date: str,
    trades: pd.DataFrame,
    metrics: pd.DataFrame,
    report_root: Path,
) -> dict[str, str]:
    target = report_root / "backtests" / f"{start_date}_{end_date}"
    target.mkdir(parents=True, exist_ok=True)
    md = target / "backtest_report.md"
    lines = [
        f"# 热点雷达基础回测 {start_date} - {end_date}", "",
        "> 信号在收盘后确认，统一按下一交易日开盘价模拟；这是样本内研究结果。", "",
        "| 持有交易日 | 可执行信号数 | 平均收益 | 胜率 | 最差收益 |",
        "|---:|---:|---:|---:|---:|",
    ]
    overall = metrics[metrics["group_type"] == "all"] if "group_type" in metrics else metrics
    for _, row in overall.iterrows():
        lines.append(
            f"| {int(row['holding_days'])} | {int(row['trigger_count'])} | "
            f"{row['average_return']:.2%} | {row['win_rate']:.2%} | {row['max_loss']:.2%} |"
        )
    md.write_text("\n".join(lines), encoding="utf-8")
    xlsx = target / "backtest_report.xlsx"
    with pd.ExcelWriter(xlsx, engine="openpyxl") as writer:
        metrics.to_excel(writer, sheet_name="metrics", index=False)
        trades.to_excel(writer, sheet_name="trades", index=False)
    return {"markdown": str(md), "excel": str(xlsx)}
