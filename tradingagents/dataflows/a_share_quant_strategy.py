from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd
from dateutil.relativedelta import relativedelta

from .symbol_utils import NoMarketDataError
from .tushare_data import (
    TushareUnavailableError,
    _ensure_tushare_client,
    _load_tushare_ohlcv,
    _tushare_date,
    _tushare_symbol,
)


@dataclass(frozen=True)
class MoneyflowSignalConfig:
    lookback_calendar_days: int = 180
    prev_amount_window: int = 10
    signal_threshold: float = 0.05
    take_profit_pct: float = 0.20
    stop_loss_pct: float = 0.15
    monitor_days: int = 30


MATERIAL_CHANGE_KEYWORDS = (
    "重大",
    "重组",
    "并购",
    "定增",
    "监管",
    "立案",
    "处罚",
    "退市",
    "ST",
    "业绩预告",
    "亏损",
    "暴雷",
    "停牌",
    "政策变化",
    "基本面恶化",
)


def _load_tushare_moneyflow(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    ts_code = _tushare_symbol(symbol)
    pro = _ensure_tushare_client()
    fields = (
        "ts_code,trade_date,buy_lg_amount,sell_lg_amount,"
        "buy_elg_amount,sell_elg_amount,net_mf_amount"
    )
    try:
        data = pro.moneyflow(
            ts_code=ts_code,
            start_date=_tushare_date(start_date),
            end_date=_tushare_date(end_date),
            fields=fields,
        )
    except Exception as exc:
        raise TushareUnavailableError(f"Tushare moneyflow failed: {exc}") from exc

    if data is None or data.empty:
        raise NoMarketDataError(symbol, ts_code, f"no moneyflow rows between {start_date} and {end_date}")

    data = data.rename(
        columns={
            "trade_date": "Date",
            "buy_lg_amount": "BuyLargeAmount10k",
            "sell_lg_amount": "SellLargeAmount10k",
            "buy_elg_amount": "BuyExtraLargeAmount10k",
            "sell_elg_amount": "SellExtraLargeAmount10k",
            "net_mf_amount": "NetInflowAmount10k",
        }
    )
    data["Date"] = pd.to_datetime(data["Date"], format="%Y%m%d", errors="coerce")
    numeric_cols = [
        "BuyLargeAmount10k",
        "SellLargeAmount10k",
        "BuyExtraLargeAmount10k",
        "SellExtraLargeAmount10k",
        "NetInflowAmount10k",
    ]
    for col in numeric_cols:
        if col in data.columns:
            data[col] = pd.to_numeric(data[col], errors="coerce")

    if "NetInflowAmount10k" not in data.columns:
        buy_cols = [c for c in ("BuyLargeAmount10k", "BuyExtraLargeAmount10k") if c in data.columns]
        sell_cols = [c for c in ("SellLargeAmount10k", "SellExtraLargeAmount10k") if c in data.columns]
        if buy_cols and sell_cols:
            data["NetInflowAmount10k"] = data[buy_cols].sum(axis=1) - data[sell_cols].sum(axis=1)
        else:
            raise TushareUnavailableError("Tushare moneyflow response missing net_mf_amount")

    data = data.dropna(subset=["Date", "NetInflowAmount10k"]).sort_values("Date")
    if data.empty:
        raise NoMarketDataError(symbol, ts_code, f"no usable moneyflow rows between {start_date} and {end_date}")
    return data


def _material_change_gate(final_state: dict | None) -> tuple[str, list[str]]:
    if not final_state:
        return "未接入政策面/基本面文本，仅按资金流和价格触发；下单前需要人工确认基本面没有重大变化。", []

    text = "\n".join(
        str(final_state.get(key, ""))
        for key in ("news_report", "fundamentals_report", "sentiment_report")
    )
    hits = [kw for kw in MATERIAL_CHANGE_KEYWORDS if kw in text]
    if hits:
        return (
            "报告文本中出现可能代表政策面/基本面变化的关键词，资金流买入信号需要降级并人工复核。",
            hits,
        )
    return "未在新闻/基本面/情绪报告文本中发现明显重大变化关键词，资金流信号可以按正常权重评估。", []


def _signal_status(latest_signal: pd.Series, latest_row: pd.Series, cfg: MoneyflowSignalConfig) -> tuple[str, str]:
    entry = float(latest_signal["Close"])
    latest_close = float(latest_row["Close"])
    take_profit = entry * (1 + cfg.take_profit_pct)
    stop_loss = entry * (1 - cfg.stop_loss_pct)
    signal_date = latest_signal["Date"]
    latest_date = latest_row["Date"]
    days_elapsed = int((latest_date - signal_date).days)

    if latest_close >= take_profit:
        return "SELL_TAKE_PROFIT", f"最新收盘价已达到或超过止盈线 {take_profit:.2f}。"
    if latest_close <= stop_loss:
        return "REDUCE_OR_EXIT", f"最新收盘价已跌破风控线 {stop_loss:.2f}。"
    if days_elapsed > cfg.monitor_days:
        return "EXPIRED", f"距离信号日已超过 {cfg.monitor_days} 个自然日，信号过期。"
    return "ACTIVE_BUY_OR_HOLD", f"信号仍在 {cfg.monitor_days} 日监控窗口内，未触发止盈或止损。"


def build_quant_strategy_report(
    symbol: str,
    analysis_date: str,
    final_state: dict | None = None,
    cfg: MoneyflowSignalConfig | None = None,
) -> str:
    """Build a standalone A-share moneyflow quant strategy report."""
    cfg = cfg or MoneyflowSignalConfig()
    end_dt = datetime.strptime(analysis_date, "%Y-%m-%d")
    start_dt = end_dt - relativedelta(days=cfg.lookback_calendar_days)
    start_date = start_dt.strftime("%Y-%m-%d")

    try:
        ts_code = _tushare_symbol(symbol)
        ohlcv = _load_tushare_ohlcv(symbol, start_date, analysis_date)
        moneyflow = _load_tushare_moneyflow(symbol, start_date, analysis_date)
    except (NoMarketDataError, TushareUnavailableError, ValueError) as exc:
        return _format_unavailable_report(symbol, analysis_date, exc)

    merged = pd.merge(ohlcv, moneyflow, on="Date", how="inner").sort_values("Date")
    if len(merged) <= cfg.prev_amount_window:
        return _format_unavailable_report(
            symbol,
            analysis_date,
            NoMarketDataError(symbol, symbol, "not enough joined OHLCV + moneyflow rows"),
        )

    # Tushare daily amount is commonly returned in thousand CNY, while moneyflow
    # amounts are in ten-thousand CNY. Convert turnover to ten-thousand CNY.
    merged["TurnoverAmount10k"] = pd.to_numeric(merged["Amount"], errors="coerce") / 10.0
    merged["Prev10AvgTurnover10k"] = merged["TurnoverAmount10k"].rolling(cfg.prev_amount_window).mean().shift(1)
    merged["InflowToPrev10Turnover"] = merged["NetInflowAmount10k"] / merged["Prev10AvgTurnover10k"]
    merged["TurnoverExpansion"] = merged["TurnoverAmount10k"] / merged["Prev10AvgTurnover10k"]
    merged["MA20"] = merged["Close"].rolling(20).mean()
    merged["ClosePctChange"] = merged["Close"].pct_change()

    eligible = merged[
        (merged["NetInflowAmount10k"] > 0)
        & (merged["InflowToPrev10Turnover"] >= cfg.signal_threshold)
    ].copy()

    policy_gate, policy_hits = _material_change_gate(final_state)
    latest = merged.iloc[-1]
    recent = merged.tail(15)

    lines = [
        f"# A-share Moneyflow Quant Strategy Report: {symbol}",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Analysis date: {analysis_date}",
        f"Tushare code: {ts_code}",
        "",
        "## Strategy Rule",
        "",
        "- Day 0 buy signal: net inflow >= 5% of the previous 10 trading days' average turnover.",
        "- Entry reference: Day 0 close.",
        "- Take profit: latest/live price >= Day 0 close * 1.20.",
        "- Risk exit: latest/live price <= Day 0 close * 0.85.",
        "- The signal should be used only when policy and fundamentals have no material change.",
        "",
        "## Current Signal",
        "",
    ]

    if eligible.empty:
        lines.extend(
            [
                "Signal: NO_BUY_SIGNAL",
                "",
                "No trading day in the available lookback window met the 5% net-inflow trigger.",
            ]
        )
    else:
        latest_signal = eligible.iloc[-1]
        status, status_reason = _signal_status(latest_signal, latest, cfg)
        take_profit = float(latest_signal["Close"]) * (1 + cfg.take_profit_pct)
        stop_loss = float(latest_signal["Close"]) * (1 - cfg.stop_loss_pct)
        lines.extend(
            [
                f"Signal: {status}",
                f"Reason: {status_reason}",
                "",
                f"- Day 0: {latest_signal['Date'].strftime('%Y-%m-%d')}",
                f"- Day 0 close: {latest_signal['Close']:.2f}",
                f"- Net inflow: {latest_signal['NetInflowAmount10k']:.2f} 万元",
                f"- Previous 10-day average turnover: {latest_signal['Prev10AvgTurnover10k']:.2f} 万元",
                f"- Net inflow / previous 10-day average turnover: {latest_signal['InflowToPrev10Turnover']:.2%}",
                f"- Turnover expansion vs previous 10-day average: {latest_signal['TurnoverExpansion']:.2f}x",
                f"- Take-profit level: {take_profit:.2f}",
                f"- Risk-exit level: {stop_loss:.2f}",
                f"- Latest close: {latest['Close']:.2f} ({latest['Date'].strftime('%Y-%m-%d')})",
            ]
        )

    lines.extend(
        [
            "",
            "## Policy/Fundamental Stability Gate",
            "",
            policy_gate,
        ]
    )
    if policy_hits:
        lines.append(f"Matched keywords: {', '.join(policy_hits)}")

    lines.extend(
        [
            "",
            "## Secondary A-share Quant Checks",
            "",
            _format_secondary_checks(latest),
            "",
            "## Recent 15 Trading Days",
            "",
            "| Date | Close | Net inflow (万元) | Prev 10-day avg turnover (万元) | Inflow ratio | Turnover expansion | Signal |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for _, row in recent.iterrows():
        is_signal = (
            pd.notna(row.get("InflowToPrev10Turnover"))
            and row["NetInflowAmount10k"] > 0
            and row["InflowToPrev10Turnover"] >= cfg.signal_threshold
        )
        lines.append(
            "| {date} | {close:.2f} | {net:.2f} | {avg:.2f} | {ratio:.2%} | {exp:.2f}x | {signal} |".format(
                date=row["Date"].strftime("%Y-%m-%d"),
                close=float(row["Close"]),
                net=float(row["NetInflowAmount10k"]),
                avg=float(row["Prev10AvgTurnover10k"]) if pd.notna(row["Prev10AvgTurnover10k"]) else 0.0,
                ratio=float(row["InflowToPrev10Turnover"]) if pd.notna(row["InflowToPrev10Turnover"]) else 0.0,
                exp=float(row["TurnoverExpansion"]) if pd.notna(row["TurnoverExpansion"]) else 0.0,
                signal="BUY_TRIGGER" if is_signal else "",
            )
        )

    lines.extend(
        [
            "",
            "## Monitoring Instructions",
            "",
            "Use this file as the strategy baseline. For realtime monitoring, update the latest price and latest net inflow, then apply:",
            "",
            "1. If no active signal exists, wait until a trading day closes with net inflow >= 5% of the previous 10-day average turnover.",
            "2. Once active, use Day 0 close as the reference price.",
            "3. Sell/take profit when live or close price is 20% above Day 0 close.",
            "4. Reduce or close when live or close price is 15% below Day 0 close.",
            "5. Suppress or downgrade the signal if fresh policy/fundamental news materially changes the original thesis.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _format_secondary_checks(latest: pd.Series) -> str:
    checks = []
    turnover_expansion = latest.get("TurnoverExpansion")
    if pd.notna(turnover_expansion):
        checks.append(
            f"- Liquidity confirmation: latest turnover is {float(turnover_expansion):.2f}x the previous 10-day average."
        )
    ma20 = latest.get("MA20")
    if pd.notna(ma20):
        trend = "above" if latest["Close"] >= ma20 else "below"
        checks.append(f"- Trend filter: latest close is {trend} MA20 ({float(ma20):.2f}).")
    pct = latest.get("ClosePctChange")
    if pd.notna(pct):
        if abs(float(pct)) >= 0.08:
            checks.append("- Chase-risk filter: latest one-day move is large; avoid chasing if the signal has already been priced in.")
        else:
            checks.append("- Chase-risk filter: latest one-day move is not an extreme limit-style move.")
    return "\n".join(checks) if checks else "- Not enough recent data for secondary checks."


def _format_unavailable_report(symbol: str, analysis_date: str, error: Exception) -> str:
    return (
        f"# A-share Moneyflow Quant Strategy Report: {symbol}\n\n"
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Analysis date: {analysis_date}\n\n"
        "Signal: DATA_UNAVAILABLE\n\n"
        f"Could not generate the moneyflow strategy report: {type(error).__name__}: {error}\n\n"
        "Check TUSHARE_TOKEN, Tushare moneyflow permission, and network access. "
        "The moneyflow interface may require higher Tushare points than basic daily OHLCV data.\n"
    )
