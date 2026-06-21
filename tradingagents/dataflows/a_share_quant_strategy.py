from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import median

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
    lookback_calendar_days: int = 540
    prev_amount_window: int = 20
    flow_window: int = 3
    signal_threshold: float = 0.03
    min_positive_flow_days: int = 2
    min_turnover_expansion: float = 1.0
    trend_ma_window: int = 20
    max_chase_pct: float = 0.08
    atr_window: int = 14
    atr_stop_multiple: float = 2.0
    trailing_atr_multiple: float = 2.5
    minimum_stop_pct: float = 0.03
    maximum_stop_pct: float = 0.15
    reward_risk_ratio: float = 2.0
    monitor_days: int = 30
    slippage_bps: float = 10.0
    round_trip_cost_bps: float = 30.0
    limit_up_threshold: float = 0.095
    valuation_lookback_days: int = 1095
    margin_of_safety_pct: float = 0.10
    valuation_ratio_floor: float = 1 / 3
    valuation_ratio_ceiling: float = 3.0
    example_capital: float = 100_000.0
    risk_budget_pct: float = 0.01
    max_position_pct: float = 0.20


@dataclass(frozen=True)
class TradePlan:
    status: str
    reason: str
    signal_date: pd.Timestamp
    signal_close: float
    entry_date: pd.Timestamp | None
    entry_price: float | None
    take_profit: float | None
    initial_stop: float | None
    current_exit: float | None
    exit_date: pd.Timestamp | None = None
    exit_price: float | None = None


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


def _apply_forward_adjustment(
    symbol: str,
    prices: pd.DataFrame,
    start_date: str,
    end_date: str,
) -> tuple[pd.DataFrame, bool]:
    """Put historical OHLC on the latest-price basis using Tushare adj_factor.

    Adjustment is best-effort. Missing permissions or data must not make the
    whole signal unavailable; the report explicitly states when raw prices are
    used instead.
    """

    adjusted = prices.copy()
    try:
        pro = _ensure_tushare_client()
        factors = pro.adj_factor(
            ts_code=_tushare_symbol(symbol),
            start_date=_tushare_date(start_date),
            end_date=_tushare_date(end_date),
            fields="ts_code,trade_date,adj_factor",
        )
        if factors is None or factors.empty:
            return adjusted, False
        factors = factors.rename(columns={"trade_date": "Date", "adj_factor": "AdjFactor"})
        factors["Date"] = pd.to_datetime(factors["Date"], format="%Y%m%d", errors="coerce")
        factors["AdjFactor"] = pd.to_numeric(factors["AdjFactor"], errors="coerce")
        adjusted = pd.merge(adjusted, factors[["Date", "AdjFactor"]], on="Date", how="left")
        adjusted["AdjFactor"] = adjusted["AdjFactor"].ffill().bfill()
        latest_factor = adjusted["AdjFactor"].dropna().iloc[-1]
        if not latest_factor or pd.isna(latest_factor):
            return prices.copy(), False
        scale = adjusted["AdjFactor"] / float(latest_factor)
        for column in ("Open", "High", "Low", "Close"):
            adjusted[column] = adjusted[column] * scale
        return adjusted.drop(columns=["AdjFactor"]), True
    except Exception:
        return prices.copy(), False


def _load_relative_valuation(
    symbol: str,
    analysis_date: str,
    latest_close: float,
    cfg: MoneyflowSignalConfig,
) -> dict:
    """Estimate a relative fair value from the stock's own PE/PB history."""

    end_dt = datetime.strptime(analysis_date, "%Y-%m-%d")
    start_dt = end_dt - relativedelta(days=cfg.valuation_lookback_days)
    try:
        pro = _ensure_tushare_client()
        data = pro.daily_basic(
            ts_code=_tushare_symbol(symbol),
            start_date=start_dt.strftime("%Y%m%d"),
            end_date=end_dt.strftime("%Y%m%d"),
            fields="ts_code,trade_date,close,pe_ttm,pb",
        )
    except Exception as exc:
        return {"available": False, "reason": f"relative valuation unavailable: {type(exc).__name__}"}

    if data is None or data.empty:
        return {"available": False, "reason": "relative valuation unavailable: no daily_basic rows"}

    for column in ("close", "pe_ttm", "pb"):
        if column in data.columns:
            data[column] = pd.to_numeric(data[column], errors="coerce")
    if "trade_date" in data.columns:
        data["trade_date"] = pd.to_datetime(data["trade_date"], format="%Y%m%d", errors="coerce")
        data = data.sort_values("trade_date")

    latest = data.iloc[-1]
    candidates: list[float] = []
    details: list[str] = []
    for field, label in (("pe_ttm", "PE(TTM)"), ("pb", "PB")):
        if field not in data.columns:
            continue
        history = data.loc[data[field] > 0, field].dropna()
        current = latest.get(field)
        if len(history) < 60 or current is None or pd.isna(current) or float(current) <= 0:
            continue
        historical_median = float(history.median())
        relative_multiple = float(current) / historical_median
        if not cfg.valuation_ratio_floor <= relative_multiple <= cfg.valuation_ratio_ceiling:
            details.append(
                f"{label} {float(current):.2f} vs history median {historical_median:.2f} ignored: "
                f"current/median {relative_multiple:.2f}x is outside the "
                f"{cfg.valuation_ratio_floor:.2f}x-{cfg.valuation_ratio_ceiling:.2f}x reliability band"
            )
            continue
        fair_value = latest_close * historical_median / float(current)
        if fair_value > 0:
            candidates.append(fair_value)
            details.append(f"{label} {float(current):.2f} vs history median {historical_median:.2f}")

    if not candidates:
        return {
            "available": False,
            "reason": "relative valuation unavailable: no reliable PE/PB anchor",
            "details": details,
        }

    fair_value = float(median(candidates))
    entry_ceiling = fair_value * (1 - cfg.margin_of_safety_pct)
    return {
        "available": True,
        "fairValue": fair_value,
        "entryCeiling": entry_ceiling,
        "details": details,
        "method": "own historical PE/PB median with margin of safety",
    }


def _material_change_gate(final_state: dict | None) -> tuple[str, list[str]]:
    if not final_state:
        return "未接入政策面/基本面文本，价格区间只使用结构化估值和行情数据。", []

    text = "\n".join(
        str(final_state.get(key, ""))
        for key in ("news_report", "fundamentals_report", "sentiment_report")
    )
    hits = [kw for kw in MATERIAL_CHANGE_KEYWORDS if kw in text]
    if hits:
        return "发现重大变化关键词；暂停新增入场，并按最新可成交价格人工复核退场。", hits
    return "未在新闻、基本面和情绪报告中发现明显重大变化关键词。", []


def _prepare_indicators(merged: pd.DataFrame, cfg: MoneyflowSignalConfig) -> pd.DataFrame:
    data = merged.copy().sort_values("Date").reset_index(drop=True)
    data["TurnoverAmount10k"] = pd.to_numeric(data["Amount"], errors="coerce") / 10.0
    data["PrevAvgTurnover10k"] = (
        data["TurnoverAmount10k"].rolling(cfg.prev_amount_window).mean().shift(1)
    )
    data["FlowSum"] = data["NetInflowAmount10k"].rolling(cfg.flow_window).sum()
    data["PositiveFlowDays"] = (
        (data["NetInflowAmount10k"] > 0).astype(int).rolling(cfg.flow_window).sum()
    )
    data["FlowIntensity"] = data["FlowSum"] / (
        data["PrevAvgTurnover10k"] * cfg.flow_window
    )
    data["TurnoverExpansion"] = (
        data["TurnoverAmount10k"].rolling(cfg.flow_window).mean()
        / data["PrevAvgTurnover10k"]
    )
    data["MA20"] = data["Close"].rolling(cfg.trend_ma_window).mean()
    data["ClosePctChange"] = data["Close"].pct_change()

    previous_close = data["Close"].shift(1)
    true_range = pd.concat(
        [
            data["High"] - data["Low"],
            (data["High"] - previous_close).abs(),
            (data["Low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    data["ATR"] = true_range.rolling(cfg.atr_window).mean()
    data["BuyCondition"] = (
        (data["FlowIntensity"] >= cfg.signal_threshold)
        & (data["PositiveFlowDays"] >= cfg.min_positive_flow_days)
        & (data["TurnoverExpansion"] >= cfg.min_turnover_expansion)
        & (data["Close"] >= data["MA20"])
        & (data["ClosePctChange"].abs() < cfg.max_chase_pct)
    )
    data["BuyTrigger"] = data["BuyCondition"] & ~data["BuyCondition"].shift(1, fill_value=False)
    return data


def _trade_plan(data: pd.DataFrame, signal_index: int, cfg: MoneyflowSignalConfig) -> TradePlan:
    signal = data.iloc[signal_index]
    signal_date = signal["Date"]
    signal_close = float(signal["Close"])
    if signal_index + 1 >= len(data):
        return TradePlan(
            "PENDING_ENTRY",
            "资金流信号已确认，等待下一交易日可成交价格；不会按 Day 0 收盘价假设成交。",
            signal_date,
            signal_close,
            None,
            None,
            None,
            None,
            None,
        )

    entry_row = data.iloc[signal_index + 1]
    entry_open = float(entry_row["Open"])
    if entry_open >= signal_close * (1 + cfg.limit_up_threshold):
        return TradePlan(
            "ENTRY_BLOCKED_LIMIT_UP",
            "下一交易日开盘接近涨停，按不可成交处理，等待重新出现信号。",
            signal_date,
            signal_close,
            entry_row["Date"],
            None,
            None,
            None,
            None,
        )

    entry_price = entry_open * (1 + cfg.slippage_bps / 10_000)
    atr = float(signal["ATR"]) if pd.notna(signal["ATR"]) else entry_price * 0.05
    stop_distance = max(entry_price * cfg.minimum_stop_pct, atr * cfg.atr_stop_multiple)
    stop_distance = min(stop_distance, entry_price * cfg.maximum_stop_pct)
    initial_stop = entry_price - stop_distance
    take_profit = entry_price + stop_distance * cfg.reward_risk_ratio
    current_stop = initial_stop
    peak_close = entry_price
    latest = data.iloc[-1]

    for row_index in range(signal_index + 1, len(data)):
        row = data.iloc[row_index]
        row_open = float(row["Open"])
        row_low = float(row["Low"])
        row_high = float(row["High"])
        exit_slippage = 1 - cfg.slippage_bps / 10_000

        if int((row["Date"] - signal_date).days) > cfg.monitor_days:
            exit_price = row_open * (1 - cfg.slippage_bps / 10_000)
            return TradePlan(
                "EXPIRED",
                f"信号已超过 {cfg.monitor_days} 个自然日，在首个可交易日按开盘参考价提示退出。",
                signal_date,
                signal_close,
                entry_row["Date"],
                entry_price,
                take_profit,
                initial_stop,
                current_stop,
                row["Date"],
                exit_price,
            )

        # Conservative same-bar rule: if both boundaries are touched, assume
        # the protective stop happened first because intraday ordering is unknown.
        if row_open <= current_stop:
            exit_price = row_open * exit_slippage
            return TradePlan(
                "REDUCE_OR_EXIT",
                "价格跳空跌破动态风控线。",
                signal_date,
                signal_close,
                entry_row["Date"],
                entry_price,
                take_profit,
                initial_stop,
                current_stop,
                row["Date"],
                exit_price,
            )
        if row_low <= current_stop:
            exit_price = current_stop * exit_slippage
            return TradePlan(
                "REDUCE_OR_EXIT",
                "盘中价格触及动态风控线。",
                signal_date,
                signal_close,
                entry_row["Date"],
                entry_price,
                take_profit,
                initial_stop,
                current_stop,
                row["Date"],
                exit_price,
            )
        if row_open >= take_profit:
            exit_price = row_open * exit_slippage
            return TradePlan(
                "SELL_TAKE_PROFIT",
                "价格跳空达到收益风险比止盈线。",
                signal_date,
                signal_close,
                entry_row["Date"],
                entry_price,
                take_profit,
                initial_stop,
                current_stop,
                row["Date"],
                exit_price,
            )
        if row_high >= take_profit:
            exit_price = take_profit * exit_slippage
            return TradePlan(
                "SELL_TAKE_PROFIT",
                "盘中价格触及收益风险比止盈线。",
                signal_date,
                signal_close,
                entry_row["Date"],
                entry_price,
                take_profit,
                initial_stop,
                current_stop,
                row["Date"],
                exit_price,
            )

        peak_close = max(peak_close, float(row["Close"]))
        row_atr = float(row["ATR"]) if pd.notna(row["ATR"]) else atr
        current_stop = max(current_stop, peak_close - cfg.trailing_atr_multiple * row_atr)

    return TradePlan(
        "ACTIVE_HOLD_MONITOR",
        "已按下一交易日价格建立观察仓位，尚未触发止盈、动态风控或时间退出。",
        signal_date,
        signal_close,
        entry_row["Date"],
        entry_price,
        take_profit,
        initial_stop,
        current_stop,
    )


def _strategy_plans(data: pd.DataFrame, cfg: MoneyflowSignalConfig) -> list[TradePlan]:
    """Evaluate non-overlapping signals as a single-position state machine."""

    plans: list[TradePlan] = []
    next_allowed_index = 0
    date_to_index = {row["Date"]: index for index, row in data.iterrows()}
    for signal_index in data.index[data["BuyTrigger"]].tolist():
        if signal_index < next_allowed_index:
            continue
        plan = _trade_plan(data, signal_index, cfg)
        plans.append(plan)
        if plan.status == "ENTRY_BLOCKED_LIMIT_UP":
            next_allowed_index = signal_index + 1
            continue
        if plan.exit_date is None:
            break
        next_allowed_index = date_to_index.get(plan.exit_date, signal_index) + 1
    return plans


def _backtest_summary(
    plans: list[TradePlan],
    cfg: MoneyflowSignalConfig,
    data: pd.DataFrame,
) -> dict:
    completed = [plan for plan in plans if plan.entry_price and plan.exit_price]
    trades = []
    returns = []
    for plan in completed:
        net_return = plan.exit_price / plan.entry_price - 1 - cfg.round_trip_cost_bps / 10_000
        returns.append(net_return)
        trades.append(
            {
                "signalDate": plan.signal_date.strftime("%Y-%m-%d"),
                "entryDate": plan.entry_date.strftime("%Y-%m-%d") if plan.entry_date is not None else "",
                "exitDate": plan.exit_date.strftime("%Y-%m-%d") if plan.exit_date is not None else "",
                "entryPrice": float(plan.entry_price),
                "exitPrice": float(plan.exit_price),
                "return": net_return,
                "status": plan.status,
                "holdingDays": int((plan.exit_date - plan.entry_date).days)
                if plan.exit_date is not None and plan.entry_date is not None
                else 0,
            }
        )

    benchmark_return = None
    benchmark_rows = data.dropna(subset=["Close"])
    if len(benchmark_rows) >= 2:
        benchmark_return = (
            float(benchmark_rows.iloc[-1]["Close"]) / float(benchmark_rows.iloc[0]["Close"])
            - 1
            - cfg.round_trip_cost_bps / 10_000
        )

    if not returns:
        return {
            "trades": 0,
            "winRate": None,
            "averageReturn": None,
            "totalReturn": None,
            "benchmarkReturn": benchmark_return,
            "excessReturn": None,
            "maxDrawdown": None,
            "profitFactor": None,
            "averageHoldingDays": None,
            "evidenceGrade": "INSUFFICIENT_SAMPLE",
            "tradeDetails": [],
        }

    total_return = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for value in returns:
        total_return *= 1 + value
        peak = max(peak, total_return)
        max_drawdown = min(max_drawdown, total_return / peak - 1)
    compounded_return = total_return - 1
    gross_profit = sum(value for value in returns if value > 0)
    gross_loss = abs(sum(value for value in returns if value < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else None
    excess_return = compounded_return - benchmark_return if benchmark_return is not None else None

    if len(returns) < 5:
        evidence_grade = "INSUFFICIENT_SAMPLE"
    elif compounded_return > 0 and (excess_return is None or excess_return > 0) and max_drawdown >= -0.20:
        evidence_grade = "PROMISING_IN_SAMPLE"
    elif compounded_return > 0:
        evidence_grade = "POSITIVE_BUT_UNPROVEN"
    else:
        evidence_grade = "NOT_VALIDATED"

    return {
        "trades": len(returns),
        "winRate": sum(value > 0 for value in returns) / len(returns),
        "averageReturn": sum(returns) / len(returns),
        "totalReturn": compounded_return,
        "benchmarkReturn": benchmark_return,
        "excessReturn": excess_return,
        "maxDrawdown": max_drawdown,
        "profitFactor": profit_factor,
        "averageHoldingDays": sum(trade["holdingDays"] for trade in trades) / len(trades),
        "evidenceGrade": evidence_grade,
        "tradeDetails": trades,
    }


def _example_position_size(plan: TradePlan | None, cfg: MoneyflowSignalConfig) -> int | None:
    if not plan or not plan.entry_price or not plan.initial_stop:
        return None
    risk_per_share = plan.entry_price - plan.initial_stop
    if risk_per_share <= 0:
        return None
    risk_limited = cfg.example_capital * cfg.risk_budget_pct / risk_per_share
    capital_limited = cfg.example_capital * cfg.max_position_pct / plan.entry_price
    shares = int(min(risk_limited, capital_limited) // 100 * 100)
    return max(shares, 0)


def _entry_zone(
    latest: pd.Series,
    signal: pd.Series | None,
    valuation: dict,
    cfg: MoneyflowSignalConfig,
) -> tuple[float, float, str]:
    latest_close = float(latest["Close"])
    atr = float(latest["ATR"]) if pd.notna(latest.get("ATR")) else latest_close * 0.04
    technical_ceiling = latest_close
    if signal is not None:
        signal_atr = float(signal["ATR"]) if pd.notna(signal.get("ATR")) else atr
        technical_ceiling = float(signal["Close"]) + 0.5 * signal_atr

    if valuation.get("available"):
        upper = min(technical_ceiling, float(valuation["entryCeiling"]))
        basis = "历史 PE/PB 中位数、安全边际与 ATR/信号价格共同约束"
    else:
        upper = technical_ceiling
        basis = "估值数据不足，仅使用 ATR 与信号价格；需人工核对基本面"

    upper = max(upper, 0.01)
    lower = max(0.01, upper - max(0.5 * atr, upper * 0.02))
    return lower, upper, basis


def build_quant_strategy_report(
    symbol: str,
    analysis_date: str,
    final_state: dict | None = None,
    cfg: MoneyflowSignalConfig | None = None,
) -> str:
    """Build an A-share entry/exit timing report; never place real orders."""

    cfg = cfg or MoneyflowSignalConfig()
    end_dt = datetime.strptime(analysis_date, "%Y-%m-%d")
    start_dt = end_dt - relativedelta(days=cfg.lookback_calendar_days)
    start_date = start_dt.strftime("%Y-%m-%d")

    try:
        ts_code = _tushare_symbol(symbol)
        ohlcv = _load_tushare_ohlcv(symbol, start_date, analysis_date)
        ohlcv, prices_adjusted = _apply_forward_adjustment(symbol, ohlcv, start_date, analysis_date)
        moneyflow = _load_tushare_moneyflow(symbol, start_date, analysis_date)
    except (NoMarketDataError, TushareUnavailableError, ValueError) as exc:
        return _format_unavailable_report(symbol, analysis_date, exc)

    merged = pd.merge(ohlcv, moneyflow, on="Date", how="inner").sort_values("Date")
    minimum_rows = max(cfg.prev_amount_window, cfg.trend_ma_window, cfg.atr_window) + cfg.flow_window
    if len(merged) < minimum_rows:
        return _format_unavailable_report(
            symbol,
            analysis_date,
            NoMarketDataError(symbol, symbol, "not enough joined OHLCV + moneyflow rows"),
        )

    data = _prepare_indicators(merged, cfg)
    latest = data.iloc[-1]
    plans = _strategy_plans(data, cfg)
    plan = plans[-1] if plans else None
    signal_row = None
    if plan is not None:
        matching = data.index[data["Date"] == plan.signal_date].tolist()
        signal_row = data.iloc[matching[0]] if matching else None
    backtest = _backtest_summary(plans, cfg, data)
    example_shares = _example_position_size(plan, cfg)
    valuation = _load_relative_valuation(symbol, analysis_date, float(latest["Close"]), cfg)
    entry_low, entry_high, entry_basis = _entry_zone(latest, signal_row, valuation, cfg)
    policy_gate, policy_hits = _material_change_gate(final_state)

    signal = plan.status if plan else "NO_BUY_SIGNAL"
    reason = plan.reason if plan else "当前回看区间没有通过资金流、趋势、流动性和追高过滤的入场信号。"
    if signal == "PENDING_ENTRY" and float(latest["Close"]) > entry_high:
        signal = "WAIT_FOR_ENTRY_PRICE"
        reason = "资金流条件已出现，但当前价格高于基本面与 ATR 共同约束的建议买入上限，等待价格进入区间。"
    if policy_hits and signal in ("PENDING_ENTRY", "WAIT_FOR_ENTRY_PRICE", "ACTIVE_HOLD_MONITOR"):
        signal = "FUNDAMENTAL_REVIEW_REQUIRED"
        reason = "基本面或政策文本出现重大变化关键词；暂停新增入场，并人工复核现有观察仓位。"

    suggested_exit = None
    if plan:
        if plan.exit_price is not None:
            suggested_exit = plan.exit_price
        elif plan.current_exit is not None:
            suggested_exit = plan.current_exit

    lines = [
        f"# A-share Entry/Exit Timing Report: {symbol}",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Analysis date: {analysis_date}",
        f"Tushare code: {ts_code}",
        "",
        "> This strategy only provides entry/exit timing and reference prices. It does not connect to a broker or place live orders.",
        "",
        "## Current Decision",
        "",
        f"Signal: {signal}",
        f"Reason: {reason}",
        f"- Suggested entry zone: {entry_low:.2f} - {entry_high:.2f}",
        f"- Entry pricing basis: {entry_basis}",
        f"- Latest close: {float(latest['Close']):.2f} ({latest['Date'].strftime('%Y-%m-%d')})",
        f"- Latest 3-day net inflow: {float(latest['FlowSum']):.2f} 万元",
        f"- Latest 3-day flow intensity: {float(latest['FlowIntensity']):.2%}",
        f"- Latest flow date: {latest['Date'].strftime('%Y-%m-%d')}",
    ]

    if signal_row is not None:
        lines.extend(
            [
                f"- Day 0: {signal_row['Date'].strftime('%Y-%m-%d')}",
                f"- Day 0 close: {float(signal_row['Close']):.2f}",
                f"- Signal-window 3-day net inflow: {float(signal_row['FlowSum']):.2f} 万元",
                f"- Positive flow days: {int(signal_row['PositiveFlowDays'])}/{cfg.flow_window}",
                f"- Signal-window flow intensity: {float(signal_row['FlowIntensity']):.2%}",
                f"- Turnover expansion: {float(signal_row['TurnoverExpansion']):.2f}x",
            ]
        )
    if plan:
        lines.extend(
            [
                f"- Reference entry date: {plan.entry_date.strftime('%Y-%m-%d') if plan.entry_date is not None else 'PENDING'}",
                f"- Reference entry price: {plan.entry_price:.2f}" if plan.entry_price is not None else "- Reference entry price: PENDING_NEXT_TRADING_DAY",
                f"- Take-profit level: {plan.take_profit:.2f}" if plan.take_profit is not None else "- Take-profit level: PENDING_ENTRY",
                f"- Risk-exit level: {plan.initial_stop:.2f}" if plan.initial_stop is not None else "- Risk-exit level: PENDING_ENTRY",
                f"- Current exit trigger: {plan.current_exit:.2f}" if plan.current_exit is not None else "- Current exit trigger: PENDING_ENTRY",
                f"- Suggested exit price now: {suggested_exit:.2f}" if suggested_exit is not None else "- Suggested exit price now: NO_ACTIVE_POSITION",
            ]
        )
        if plan.exit_date is not None:
            lines.append(f"- Exit event date: {plan.exit_date.strftime('%Y-%m-%d')}")
        if example_shares is not None:
            lines.append(
                f"- Example position limit: {example_shares} shares per ¥{cfg.example_capital:,.0f} capital "
                f"at {cfg.risk_budget_pct:.0%} risk and {cfg.max_position_pct:.0%} position cap"
            )
    else:
        lines.extend(
            [
                "- Reference entry date: NO_ACTIVE_SIGNAL",
                "- Reference entry price: NO_ACTIVE_SIGNAL",
                "- Take-profit level: NO_ACTIVE_POSITION",
                "- Risk-exit level: NO_ACTIVE_POSITION",
                "- Current exit trigger: NO_ACTIVE_POSITION",
                "- Suggested exit price now: NO_ACTIVE_POSITION",
            ]
        )

    lines.extend(["", "## Fundamental Relative Valuation", ""])
    if valuation.get("available"):
        lines.extend(
            [
                f"- Relative fair value: {valuation['fairValue']:.2f}",
                f"- Fundamental entry ceiling after {cfg.margin_of_safety_pct:.0%} safety margin: {valuation['entryCeiling']:.2f}",
                f"- Method: {valuation['method']}",
            ]
        )
        lines.extend(f"- Evidence: {detail}" for detail in valuation["details"])
    else:
        lines.append(f"- {valuation.get('reason', 'relative valuation unavailable')}")

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

    lines.extend(["", "## Lookback Backtest Snapshot", ""])
    if backtest["trades"]:
        lines.extend(
            [
                f"- Completed non-overlapping trades: {backtest['trades']}",
                f"- Win rate: {backtest['winRate']:.2%}",
                f"- Average return after modeled costs: {backtest['averageReturn']:.2%}",
                f"- Compounded return after modeled costs: {backtest['totalReturn']:.2%}",
                f"- Buy-and-hold benchmark return: {backtest['benchmarkReturn']:.2%}" if backtest["benchmarkReturn"] is not None else "- Buy-and-hold benchmark return: N/A",
                f"- Excess return vs benchmark: {backtest['excessReturn']:.2%}" if backtest["excessReturn"] is not None else "- Excess return vs benchmark: N/A",
                f"- Trade-sequence max drawdown: {backtest['maxDrawdown']:.2%}",
                f"- Profit factor: {backtest['profitFactor']:.2f}" if backtest["profitFactor"] is not None else "- Profit factor: N/A (no losing trade)",
                f"- Average holding days: {backtest['averageHoldingDays']:.1f}",
                f"- Evidence grade: {backtest['evidenceGrade']}",
            ]
        )
    else:
        lines.extend(
            [
                "- No completed non-overlapping trade in the loaded lookback window.",
                f"- Buy-and-hold benchmark return: {backtest['benchmarkReturn']:.2%}" if backtest["benchmarkReturn"] is not None else "- Buy-and-hold benchmark return: N/A",
                f"- Evidence grade: {backtest['evidenceGrade']}",
            ]
        )
    lines.append("- This is an in-sample single-stock diagnostic, not portfolio-level or out-of-sample proof.")

    if backtest["tradeDetails"]:
        lines.extend(
            [
                "",
                "| Signal date | Entry date | Exit date | Entry | Exit | Net return | Holding days | Exit type |",
                "|---|---|---|---:|---:|---:|---:|---|",
            ]
        )
        for trade in backtest["tradeDetails"]:
            lines.append(
                "| {signalDate} | {entryDate} | {exitDate} | {entryPrice:.2f} | {exitPrice:.2f} | {return:.2%} | {holdingDays} | {status} |".format(
                    **trade
                )
            )

    lines.extend(
        [
            "",
            "## Strategy and Execution Rules",
            "",
            f"- Signal: {cfg.flow_window}-day net inflow intensity >= {cfg.signal_threshold:.1%}, with at least {cfg.min_positive_flow_days} positive-flow days.",
            f"- Confirmation: turnover expansion >= {cfg.min_turnover_expansion:.2f}x, close >= MA{cfg.trend_ma_window}, and one-day move < {cfg.max_chase_pct:.0%}.",
            "- Entry: next trading day open plus configured slippage; Day 0 close is never treated as an executable fill.",
            f"- Initial risk: {cfg.atr_stop_multiple:.1f} ATR, bounded to {cfg.minimum_stop_pct:.0%}-{cfg.maximum_stop_pct:.0%} of entry price.",
            f"- Take profit: {cfg.reward_risk_ratio:.1f}R; trailing risk line: peak close minus {cfg.trailing_atr_multiple:.1f} ATR.",
            f"- Time exit: {cfg.monitor_days} calendar days.",
            f"- Cost assumptions: {cfg.slippage_bps:.0f} bps one-way slippage and {cfg.round_trip_cost_bps:.0f} bps round-trip costs for time-exit estimate.",
            f"- Price adjustment: {'forward-adjusted with Tushare adj_factor' if prices_adjusted else 'raw prices; adj_factor unavailable, review corporate actions manually'}.",
            "- Same-bar ambiguity: if stop and target are both touched, the stop is assumed first.",
            "",
            "## Recent 15 Trading Days",
            "",
            "| Date | Close | Net inflow (万元) | Prev avg turnover (万元) | Flow intensity | Turnover expansion | Signal |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for _, row in data.tail(15).iterrows():
        lines.append(
            "| {date} | {close:.2f} | {net:.2f} | {avg:.2f} | {ratio:.2%} | {exp:.2f}x | {signal} |".format(
                date=row["Date"].strftime("%Y-%m-%d"),
                close=float(row["Close"]),
                net=float(row["NetInflowAmount10k"]),
                avg=float(row["PrevAvgTurnover10k"]) if pd.notna(row["PrevAvgTurnover10k"]) else 0.0,
                ratio=float(row["FlowIntensity"]) if pd.notna(row["FlowIntensity"]) else 0.0,
                exp=float(row["TurnoverExpansion"]) if pd.notna(row["TurnoverExpansion"]) else 0.0,
                signal="BUY_TRIGGER" if bool(row["BuyTrigger"]) else "",
            )
        )

    lines.extend(
        [
            "",
            "## Usage Boundary",
            "",
            "- The suggested entry zone is a research reference, not a guaranteed fair value or fill price.",
            "- The suggested exit price is the currently active rule boundary or recorded exit estimate, not a live sell order.",
            "- Recalculate after the trading day closes and verify announcements, liquidity, limit rules and actual quotes before acting.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _format_unavailable_report(symbol: str, analysis_date: str, error: Exception) -> str:
    return (
        f"# A-share Entry/Exit Timing Report: {symbol}\n\n"
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Analysis date: {analysis_date}\n\n"
        "Signal: DATA_UNAVAILABLE\n\n"
        f"Reason: Could not generate the strategy report: {type(error).__name__}: {error}\n\n"
        "- Suggested entry zone: DATA_UNAVAILABLE\n"
        "- Suggested exit price now: DATA_UNAVAILABLE\n\n"
        "This strategy only provides entry/exit timing. It never places live orders.\n"
    )
