from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
from dateutil.relativedelta import relativedelta

from .symbol_utils import NoMarketDataError
from .tushare_data import (
    TushareUnavailableError,
    _ensure_tushare_client,
    _tushare_date,
    _tushare_symbol,
)


_INCOME_FIELDS = (
    "ts_code,ann_date,f_ann_date,end_date,report_type,basic_eps,diluted_eps,"
    "total_revenue,revenue,operate_profit,total_profit,n_income,n_income_attr_p,ebit,ebitda"
)
_BALANCE_FIELDS = (
    "ts_code,ann_date,f_ann_date,end_date,report_type,total_share,money_cap,accounts_receiv,"
    "inventories,total_cur_assets,total_assets,total_cur_liab,total_ncl,total_liab,"
    "total_hldr_eqy_exc_min_int,fix_assets,cip"
)
_CASHFLOW_FIELDS = (
    "ts_code,ann_date,f_ann_date,end_date,report_type,net_profit,c_fr_sale_sg,"
    "n_cashflow_act,n_cashflow_inv_act,n_cash_flows_fnc_act,c_pay_acq_const_fiolta,"
    "c_cash_equ_end_period,free_cashflow"
)
_INDICATOR_FIELDS = (
    "ts_code,ann_date,end_date,eps,bps,roe,roe_dt,roa,grossprofit_margin,netprofit_margin,"
    "debt_to_assets,current_ratio,quick_ratio,assets_turn,inv_turn,ar_turn,ocf_to_or,"
    "tr_yoy,op_yoy,netprofit_yoy,dt_netprofit_yoy"
)
_DAILY_BASIC_FIELDS = (
    "ts_code,trade_date,close,turnover_rate,volume_ratio,pe,pe_ttm,pb,ps_ttm,dv_ratio,dv_ttm,"
    "total_share,float_share,total_mv,circ_mv"
)


def _date_or_today(value: str | None) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d") if value else datetime.now()


def _query(pro: Any, method: str, **kwargs) -> pd.DataFrame:
    try:
        data = getattr(pro, method)(**kwargs)
    except Exception as exc:
        raise TushareUnavailableError(f"Tushare {method} failed: {exc}") from exc
    if data is None:
        return pd.DataFrame()
    return data.copy()


def _as_of_financial_rows(
    data: pd.DataFrame,
    analysis_date: str | None,
    freq: str = "quarterly",
    limit: int = 12,
) -> pd.DataFrame:
    if data.empty or "end_date" not in data.columns:
        return pd.DataFrame()

    cutoff = _date_or_today(analysis_date)
    rows = data.copy()
    for column in ("end_date", "ann_date", "f_ann_date"):
        if column in rows.columns:
            rows[column] = pd.to_datetime(rows[column], format="%Y%m%d", errors="coerce")

    visible_date = rows.get("f_ann_date")
    if visible_date is None:
        visible_date = rows.get("ann_date")
    elif "ann_date" in rows.columns:
        visible_date = visible_date.fillna(rows["ann_date"])
    if visible_date is not None:
        rows = rows[visible_date <= cutoff]
    rows = rows[rows["end_date"] <= cutoff]

    if freq.lower() == "annual":
        rows = rows[rows["end_date"].dt.strftime("%m%d") == "1231"]

    sort_columns = [column for column in ("end_date", "f_ann_date", "ann_date") if column in rows.columns]
    rows = rows.sort_values(sort_columns)
    rows = rows.drop_duplicates(subset=["end_date"], keep="last")
    return rows.sort_values("end_date", ascending=False).head(limit).reset_index(drop=True)


def _load_financial_rows(
    symbol: str,
    analysis_date: str | None,
    method: str,
    fields: str,
    freq: str = "quarterly",
    limit: int = 12,
) -> pd.DataFrame:
    ts_code = _tushare_symbol(symbol)
    end_dt = _date_or_today(analysis_date)
    start_dt = end_dt - relativedelta(years=6)
    pro = _ensure_tushare_client()
    data = _query(
        pro,
        method,
        ts_code=ts_code,
        start_date=start_dt.strftime("%Y%m%d"),
        end_date=end_dt.strftime("%Y%m%d"),
        fields=fields,
    )
    rows = _as_of_financial_rows(data, analysis_date, freq=freq, limit=limit)
    if rows.empty:
        raise NoMarketDataError(symbol, ts_code, f"Tushare {method} returned no visible report rows")
    return rows


def _statement_text(
    title: str,
    symbol: str,
    analysis_date: str | None,
    rows: pd.DataFrame,
    columns: list[tuple[str, str]],
) -> str:
    selected = [source for source, _ in columns if source in rows.columns]
    output = rows[selected].copy()
    output = output.rename(columns=dict(columns))
    for column in output.columns:
        if pd.api.types.is_datetime64_any_dtype(output[column]):
            output[column] = output[column].dt.strftime("%Y-%m-%d")
    return (
        f"# {title}: {symbol.upper()}\n"
        f"# Source: Tushare; visible as of {analysis_date or datetime.now().strftime('%Y-%m-%d')}\n"
        "# Financial statement amounts are in CNY unless the field name states otherwise.\n\n"
        + output.to_csv(index=False)
    )


def get_income_statement(symbol: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    rows = _load_financial_rows(symbol, curr_date, "income", _INCOME_FIELDS, freq=freq)
    return _statement_text(
        "Tushare Income Statement",
        symbol,
        curr_date,
        rows,
        [
            ("end_date", "ReportPeriod"),
            ("ann_date", "AnnouncementDate"),
            ("total_revenue", "TotalRevenue"),
            ("revenue", "Revenue"),
            ("operate_profit", "OperatingProfit"),
            ("total_profit", "TotalProfit"),
            ("n_income_attr_p", "NetProfitParent"),
            ("basic_eps", "BasicEPS"),
            ("ebit", "EBIT"),
            ("ebitda", "EBITDA"),
        ],
    )


def get_balance_sheet(symbol: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    rows = _load_financial_rows(symbol, curr_date, "balancesheet", _BALANCE_FIELDS, freq=freq)
    return _statement_text(
        "Tushare Balance Sheet",
        symbol,
        curr_date,
        rows,
        [
            ("end_date", "ReportPeriod"),
            ("ann_date", "AnnouncementDate"),
            ("money_cap", "Cash"),
            ("accounts_receiv", "AccountsReceivable"),
            ("inventories", "Inventory"),
            ("total_cur_assets", "CurrentAssets"),
            ("total_assets", "TotalAssets"),
            ("total_cur_liab", "CurrentLiabilities"),
            ("total_ncl", "NonCurrentLiabilities"),
            ("total_liab", "TotalLiabilities"),
            ("total_hldr_eqy_exc_min_int", "EquityParent"),
            ("fix_assets", "FixedAssets"),
        ],
    )


def get_cashflow(symbol: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    rows = _load_financial_rows(symbol, curr_date, "cashflow", _CASHFLOW_FIELDS, freq=freq)
    return _statement_text(
        "Tushare Cash Flow Statement",
        symbol,
        curr_date,
        rows,
        [
            ("end_date", "ReportPeriod"),
            ("ann_date", "AnnouncementDate"),
            ("net_profit", "NetProfit"),
            ("c_fr_sale_sg", "CashFromSales"),
            ("n_cashflow_act", "OperatingCashFlow"),
            ("n_cashflow_inv_act", "InvestingCashFlow"),
            ("n_cash_flows_fnc_act", "FinancingCashFlow"),
            ("c_pay_acq_const_fiolta", "CapitalExpenditure"),
            ("free_cashflow", "FreeCashFlow"),
            ("c_cash_equ_end_period", "EndingCashEquivalent"),
        ],
    )


def _latest_daily_basic(symbol: str, analysis_date: str | None, pro: Any) -> pd.Series | None:
    ts_code = _tushare_symbol(symbol)
    end_dt = _date_or_today(analysis_date)
    start_dt = end_dt - relativedelta(days=45)
    data = _query(
        pro,
        "daily_basic",
        ts_code=ts_code,
        start_date=start_dt.strftime("%Y%m%d"),
        end_date=end_dt.strftime("%Y%m%d"),
        fields=_DAILY_BASIC_FIELDS,
    )
    if data.empty or "trade_date" not in data.columns:
        return None
    data["trade_date"] = pd.to_datetime(data["trade_date"], format="%Y%m%d", errors="coerce")
    data = data[data["trade_date"] <= end_dt].sort_values("trade_date", ascending=False)
    return None if data.empty else data.iloc[0]


def _safe_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(number) else number


def _row_value(row: pd.Series | None, *columns: str) -> float | None:
    if row is None:
        return None
    for column in columns:
        if column in row.index:
            number = _safe_number(row[column])
            if number is not None:
                return number
    return None


def _safe_dataset(loader, errors: list[str]) -> pd.DataFrame:
    try:
        return loader()
    except (NoMarketDataError, TushareUnavailableError) as exc:
        errors.append(str(exc))
        return pd.DataFrame()


def build_fundamental_snapshot(symbol: str, analysis_date: str | None = None) -> dict[str, Any]:
    """Return a compact, JSON-safe A-share financial snapshot for the dashboard."""
    ts_code = _tushare_symbol(symbol)
    analysis_date = analysis_date or datetime.now().strftime("%Y-%m-%d")
    pro = _ensure_tushare_client()
    errors: list[str] = []

    income = _safe_dataset(
        lambda: _load_financial_rows(symbol, analysis_date, "income", _INCOME_FIELDS, limit=12), errors
    )
    balance = _safe_dataset(
        lambda: _load_financial_rows(symbol, analysis_date, "balancesheet", _BALANCE_FIELDS, limit=12), errors
    )
    cashflow = _safe_dataset(
        lambda: _load_financial_rows(symbol, analysis_date, "cashflow", _CASHFLOW_FIELDS, limit=12), errors
    )
    indicators = _safe_dataset(
        lambda: _load_financial_rows(symbol, analysis_date, "fina_indicator", _INDICATOR_FIELDS, limit=12),
        errors,
    )

    try:
        basic = _query(pro, "stock_basic", ts_code=ts_code, fields="ts_code,name,area,industry,market,list_date")
    except TushareUnavailableError as exc:
        errors.append(str(exc))
        basic = pd.DataFrame()
    try:
        valuation = _latest_daily_basic(symbol, analysis_date, pro)
    except TushareUnavailableError as exc:
        errors.append(str(exc))
        valuation = None

    income_by_period = {row["end_date"]: row for _, row in income.iterrows()} if not income.empty else {}
    balance_by_period = {row["end_date"]: row for _, row in balance.iterrows()} if not balance.empty else {}
    cash_by_period = {row["end_date"]: row for _, row in cashflow.iterrows()} if not cashflow.empty else {}
    indicator_by_period = {row["end_date"]: row for _, row in indicators.iterrows()} if not indicators.empty else {}
    periods = sorted(set(income_by_period) | set(balance_by_period) | set(cash_by_period) | set(indicator_by_period))

    trends = []
    for period in periods[-8:]:
        inc = income_by_period.get(period)
        bal = balance_by_period.get(period)
        cash = cash_by_period.get(period)
        ind = indicator_by_period.get(period)
        total_assets = _row_value(bal, "total_assets")
        total_liab = _row_value(bal, "total_liab")
        debt_ratio = _row_value(ind, "debt_to_assets")
        if debt_ratio is None and total_assets and total_liab is not None:
            debt_ratio = total_liab / total_assets * 100
        trends.append(
            {
                "period": period.strftime("%Y-%m-%d"),
                "revenue": _row_value(inc, "total_revenue", "revenue"),
                "netProfit": _row_value(inc, "n_income_attr_p", "n_income"),
                "operatingCashFlow": _row_value(cash, "n_cashflow_act"),
                "roe": _row_value(ind, "roe", "roe_dt"),
                "debtRatio": debt_ratio,
            }
        )

    latest_income = income.iloc[0] if not income.empty else None
    latest_balance = balance.iloc[0] if not balance.empty else None
    latest_cash = cashflow.iloc[0] if not cashflow.empty else None
    latest_indicator = indicators.iloc[0] if not indicators.empty else None
    total_assets = _row_value(latest_balance, "total_assets")
    total_liab = _row_value(latest_balance, "total_liab")
    debt_ratio = _row_value(latest_indicator, "debt_to_assets")
    if debt_ratio is None and total_assets and total_liab is not None:
        debt_ratio = total_liab / total_assets * 100

    metrics = {
        "revenue": _row_value(latest_income, "total_revenue", "revenue"),
        "netProfit": _row_value(latest_income, "n_income_attr_p", "n_income"),
        "operatingCashFlow": _row_value(latest_cash, "n_cashflow_act"),
        "roe": _row_value(latest_indicator, "roe", "roe_dt"),
        "grossMargin": _row_value(latest_indicator, "grossprofit_margin"),
        "netMargin": _row_value(latest_indicator, "netprofit_margin"),
        "debtRatio": debt_ratio,
        "currentRatio": _row_value(latest_indicator, "current_ratio"),
        "revenueYoY": _row_value(latest_indicator, "tr_yoy"),
        "netProfitYoY": _row_value(latest_indicator, "netprofit_yoy", "dt_netprofit_yoy"),
        "peTtm": _row_value(valuation, "pe_ttm", "pe"),
        "pb": _row_value(valuation, "pb"),
        "dividendYield": _row_value(valuation, "dv_ttm", "dv_ratio"),
        "marketValue": _row_value(valuation, "total_mv"),
    }

    summary = []
    if metrics["revenueYoY"] is not None:
        direction = "增长" if metrics["revenueYoY"] >= 0 else "下降"
        summary.append(f"最新报告期营收同比{direction} {abs(metrics['revenueYoY']):.1f}%。")
    if metrics["netProfitYoY"] is not None:
        direction = "增长" if metrics["netProfitYoY"] >= 0 else "下降"
        summary.append(f"归母净利润同比{direction} {abs(metrics['netProfitYoY']):.1f}%。")
    if metrics["operatingCashFlow"] is not None and metrics["netProfit"] is not None:
        quality = "覆盖净利润" if metrics["operatingCashFlow"] >= metrics["netProfit"] else "低于净利润"
        summary.append(f"经营现金流{quality}，用于判断利润兑现质量。")
    if metrics["debtRatio"] is not None:
        level = "偏高" if metrics["debtRatio"] >= 70 else "中等" if metrics["debtRatio"] >= 50 else "较低"
        summary.append(f"资产负债率 {metrics['debtRatio']:.1f}%，杠杆水平{level}。")

    company_row = basic.iloc[0] if not basic.empty else None
    latest_periods = [row["end_date"] for row in (latest_income, latest_balance, latest_cash, latest_indicator) if row is not None]
    latest_period = max(latest_periods).strftime("%Y-%m-%d") if latest_periods else None
    valuation_date = None
    if valuation is not None and "trade_date" in valuation.index and pd.notna(valuation["trade_date"]):
        valuation_date = valuation["trade_date"].strftime("%Y-%m-%d")

    return {
        "ticker": ts_code,
        "analysisDate": analysis_date,
        "source": "Tushare",
        "latestPeriod": latest_period,
        "valuationDate": valuation_date,
        "company": {
            "name": None if company_row is None else company_row.get("name"),
            "industry": None if company_row is None else company_row.get("industry"),
            "area": None if company_row is None else company_row.get("area"),
            "market": None if company_row is None else company_row.get("market"),
        },
        "metrics": metrics,
        "trends": trends,
        "summary": summary,
        "errors": errors,
    }


def get_fundamentals(symbol: str, curr_date: str | None = None) -> str:
    snapshot = build_fundamental_snapshot(symbol, curr_date)
    company = snapshot["company"]
    metrics = snapshot["metrics"]

    def value(name: str, suffix: str = "") -> str:
        item = metrics.get(name)
        return "N/A" if item is None else f"{item:.2f}{suffix}"

    lines = [
        f"# Tushare Company Fundamentals: {snapshot['ticker']}",
        f"# Visible as of: {snapshot['analysisDate']}",
        "",
        f"- Company: {company.get('name') or 'N/A'}",
        f"- Industry: {company.get('industry') or 'N/A'}",
        f"- Area / Market: {company.get('area') or 'N/A'} / {company.get('market') or 'N/A'}",
        f"- Latest financial period: {snapshot.get('latestPeriod') or 'N/A'}",
        f"- Revenue: {value('revenue')} CNY",
        f"- Net profit attributable to parent: {value('netProfit')} CNY",
        f"- Revenue YoY: {value('revenueYoY', '%')}",
        f"- Net profit YoY: {value('netProfitYoY', '%')}",
        f"- ROE: {value('roe', '%')}",
        f"- Gross margin: {value('grossMargin', '%')}",
        f"- Net margin: {value('netMargin', '%')}",
        f"- Debt to assets: {value('debtRatio', '%')}",
        f"- Operating cash flow: {value('operatingCashFlow')} CNY",
        f"- PE (TTM): {value('peTtm')}",
        f"- PB: {value('pb')}",
        "",
        "## Evidence-based summary",
        "",
    ]
    lines.extend(f"- {item}" for item in snapshot["summary"])
    if snapshot["errors"]:
        lines.extend(["", "## Partial data warnings", ""])
        lines.extend(f"- {error}" for error in snapshot["errors"])
    return "\n".join(lines).rstrip() + "\n"
