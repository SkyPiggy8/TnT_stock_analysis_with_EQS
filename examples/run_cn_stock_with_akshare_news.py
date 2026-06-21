"""Run a China A-share analysis with Tushare market data and Chinese news.

Usage:
    python examples/run_cn_stock_with_akshare_news.py
    python examples/run_cn_stock_with_akshare_news.py 2026-06-10

This example uses a local config copy, so it does not change the default
US-stock flow.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from pprint import pprint


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tradingagents.agents.utils.news_data_tools import get_global_news, get_news  # noqa: E402
from tradingagents.default_config import DEFAULT_CONFIG  # noqa: E402
from tradingagents.graph.trading_graph import TradingAgentsGraph  # noqa: E402


TICKER = "000966.SZ"


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _date_or_today(argv: list[str]) -> str:
    if len(argv) < 2:
        return _today()
    datetime.strptime(argv[1], "%Y-%m-%d")
    return argv[1]


def _build_cn_config() -> dict:
    config = DEFAULT_CONFIG.copy()
    config["data_vendors"] = {
        **DEFAULT_CONFIG["data_vendors"],
        "core_stock_apis": "tushare,akshare",
        "technical_indicators": "tushare,akshare",
        "news_data": "akshare_news,yfinance",
    }
    return config


def _print_news_inputs(ticker: str, curr_date: str) -> None:
    start_date = (datetime.strptime(curr_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")

    print("\n=== News input for market/news analysts: get_news ===")
    try:
        print(get_news.func(ticker, start_date, curr_date))
    except Exception as exc:  # noqa: BLE001 - diagnostic example
        print(f"ERROR fetching ticker news: {type(exc).__name__}: {exc}")

    print("\n=== News input for News Analyst: get_global_news ===")
    try:
        print(get_global_news.func(curr_date, 1, 20))
    except Exception as exc:  # noqa: BLE001 - diagnostic example
        print(f"ERROR fetching global news: {type(exc).__name__}: {exc}")


def main(argv: list[str]) -> int:
    curr_date = _date_or_today(argv)
    config = _build_cn_config()

    print(f"Running China A-share example: ticker={TICKER}, date={curr_date}")
    print("\n=== Data vendor config ===")
    pprint(config["data_vendors"])

    _print_news_inputs(TICKER, curr_date)

    graph = TradingAgentsGraph(
        selected_analysts=["market", "news", "fundamentals"],
        debug=True,
        config=config,
    )
    _, decision = graph.propagate(TICKER, curr_date)

    print("\n=== Final decision ===")
    print(decision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
