"""Manual AKShare Chinese news provider smoke test.

This script calls only dataflow functions. It does not invoke TradingAgents'
graph, tools, or any LLM provider.

Usage:
    python scripts/test_akshare_news_provider.py
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from textwrap import shorten


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tradingagents.dataflows.akshare_news_provider import (  # noqa: E402
    get_akshare_cls_news,
    get_akshare_ths_news,
    get_cn_market_news,
    get_global_news_from_cn_sources,
)


def _safe_text(value, width: int = 220) -> str:
    text = "" if value is None else " ".join(str(value).split())
    return shorten(text, width=width, placeholder="...")


def _print_news_items(title: str, fetcher) -> None:
    print(f"\n=== {title} ===")
    try:
        items = fetcher()
    except Exception as exc:  # noqa: BLE001 - manual diagnostic script
        print(f"ERROR: {type(exc).__name__}: {exc}")
        return

    if not items:
        print("NO_DATA_AVAILABLE: provider returned no rows")
        return

    for index, item in enumerate(items[:5], start=1):
        print(f"\n#{index}")
        print(f"source:   {_safe_text(item.get('source'))}")
        print(f"title:    {_safe_text(item.get('title'))}")
        print(f"datetime: {_safe_text(item.get('datetime'))}")
        print(f"content:  {_safe_text(item.get('content'))}")
        print(f"url:      {_safe_text(item.get('url'))}")


def _print_text_block(title: str, fetcher) -> None:
    print(f"\n=== {title} ===")
    try:
        text = fetcher()
    except Exception as exc:  # noqa: BLE001 - manual diagnostic script
        print(f"ERROR: {type(exc).__name__}: {exc}")
        return

    if not text:
        print("NO_DATA_AVAILABLE: provider returned empty text")
        return

    print(text)


def main() -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"AKShare Chinese news provider smoke test, date={today}")

    _print_news_items(
        'get_akshare_cls_news(symbol="重点")',
        lambda: get_akshare_cls_news(symbol="重点", limit=5),
    )
    _print_news_items(
        'get_akshare_cls_news(symbol="全部")',
        lambda: get_akshare_cls_news(symbol="全部", limit=5),
    )
    _print_news_items(
        "get_akshare_ths_news()",
        lambda: get_akshare_ths_news(limit=5),
    )
    _print_text_block(
        'get_cn_market_news(ticker="000966.SZ")',
        lambda: get_cn_market_news(ticker="000966.SZ", curr_date=today, limit=5),
    )
    _print_text_block(
        "get_global_news_from_cn_sources()",
        lambda: get_global_news_from_cn_sources(curr_date=today, limit=5),
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
