from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def _fmt_pct(value: Any) -> str:
    try:
        return f"{float(value):.2%}"
    except (TypeError, ValueError):
        return "-"


def _fmt_yi(value: Any) -> str:
    try:
        return f"{float(value) / 100_000_000:.2f}亿"
    except (TypeError, ValueError):
        return "-"


def _markdown_table(frame: pd.DataFrame, columns: list[tuple[str, str]], limit: int | None = None) -> str:
    view = frame.head(limit) if limit else frame
    headers = [label for _, label in columns]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for _, row in view.iterrows():
        values = []
        for column, _ in columns:
            value = row.get(column, "")
            if column.endswith("_ratio") or "premium" in column:
                value = _fmt_pct(value)
            elif column.endswith("_yuan"):
                value = _fmt_yi(value)
            elif column in {"stock_score", "sector_score"}:
                value = f"{float(value):.1f}" if pd.notna(value) else "-"
            values.append(str(value).replace("|", "/"))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def generate_daily_reports(
    trade_date: str,
    summary: dict[str, Any],
    stocks: pd.DataFrame,
    sectors: pd.DataFrame,
    config: dict[str, Any],
) -> dict[str, str]:
    report_dir = Path(config["storage"]["report_dir"]) / trade_date
    report_dir.mkdir(parents=True, exist_ok=True)
    top_n = int(config["scoring"]["stock_top_n"])
    sector_n = int(config["scoring"]["sector_top_n"])
    triggered = stocks[stocks["any_signal"].astype(bool)].copy()
    blocks = stocks[stocks["block_trade_count"] > 0].sort_values("block_vwap_premium", ascending=False)
    money = stocks.sort_values("net_flow_ratio", ascending=False)

    stock_columns = [
        ("ts_code", "代码"), ("name", "名称"), ("sector_level_1", "行业"),
        ("close", "收盘"), ("pct_chg", "涨跌幅%"), ("stock_score", "评分"),
        ("net_flow_ratio", "净流入比"), ("big_elg_flow_ratio", "大单比"),
        ("block_vwap_premium", "大宗溢价"), ("amount_ratio_20", "成交额放大"),
        ("signal_summary", "触发信号"),
    ]
    sector_columns = [
        ("sector_name", "行业"), ("sector_score", "评分"),
        ("triggered_stock_count", "触发数"), ("stock_count", "股票数"),
        ("avg_net_flow_ratio", "平均净流入比"), ("avg_amount_ratio_20", "成交额放大"),
        ("block_premium_count", "大宗溢价数"),
    ]
    block_columns = [
        ("ts_code", "代码"), ("name", "名称"), ("close", "收盘"),
        ("block_vwap_price", "大宗VWAP"), ("block_vwap_premium", "溢价"),
        ("block_total_amount_yuan", "大宗金额"), ("block_amount_ratio", "成交额占比"),
        ("buyer_list", "买方营业部"), ("seller_list", "卖方营业部"),
    ]
    lines = [
        f"# A股日终热点雷达 - {trade_date}", "",
        "> 仅用于收盘后研究筛选，不连接券商，不构成投资建议。", "",
        "## 一、市场概览", "",
        f"- 股票池数量：{summary['eligibleStocks']}",
        f"- 触发任一信号：{summary['triggeredStocks']}",
        f"- 资金流覆盖率：{summary['moneyflowCoverage']:.2%}",
        f"- 存在大宗交易：{summary['blockTradeStocks']}", "",
        "## 二、板块强度排名", "",
        _markdown_table(sectors, sector_columns, sector_n), "",
        "## 三、个股综合评分 Top 30", "",
        _markdown_table(triggered, stock_columns, top_n), "",
        "## 四、大宗交易溢价榜", "",
        _markdown_table(blocks, block_columns, top_n), "",
        "## 五、资金流榜", "",
        _markdown_table(money, stock_columns, top_n), "",
        "## 六、风险提示", "",
        "- 大宗交易溢价可能来自协议转让、关联交易或股份安排，不代表必然上涨。",
        "- 资金流指标由主动买卖方向统计，不是真实资金账户余额。",
        "- 热点评分用于缩小研究范围；是否入场仍需使用单股策略继续验证。",
    ]
    md_path = report_dir / "daily_signal_report.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")

    xlsx_path = report_dir / "daily_signal_report.xlsx"
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        pd.DataFrame([summary]).to_excel(writer, sheet_name="market_summary", index=False)
        sectors.to_excel(writer, sheet_name="sector_ranking", index=False)
        triggered.head(top_n).to_excel(writer, sheet_name="stock_top30", index=False)
        blocks.to_excel(writer, sheet_name="block_trade_premium", index=False)
        money.head(top_n).to_excel(writer, sheet_name="moneyflow_top", index=False)
        stocks.to_excel(writer, sheet_name="raw_signals", index=False)
    return {"markdown": str(md_path), "excel": str(xlsx_path)}
