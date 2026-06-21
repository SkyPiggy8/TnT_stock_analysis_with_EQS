from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Callable

import pandas as pd

try:
    import akshare as ak
except ImportError:  # pragma: no cover - exercised only in missing optional dep envs
    ak = None

logger = logging.getLogger(__name__)

_CACHE: dict[tuple, object] = {}
_COMPANY_SUFFIXES = (
    "股份有限公司",
    "集团股份有限公司",
    "集团有限公司",
    "控股股份有限公司",
    "控股有限公司",
    "有限责任公司",
    "股份",
    "集团",
    "控股",
    "A",
)
_HIGH_IMPORTANCE_KEYWORDS = (
    "\u505c\u724c",
    "\u590d\u724c",
    "\u9000\u5e02",
    "\u7acb\u6848",
    "\u5904\u7f5a",
    "\u51cf\u6301",
    "\u89e3\u7981",
    "\u4e1a\u7ee9\u9884\u544a",
    "\u91cd\u5927\u5408\u540c",
    "\u91cd\u7ec4",
    "\u5e76\u8d2d",
    "\u76d1\u7ba1",
    "\u6da8\u505c",
    "\u8dcc\u505c",
)
_POSITIVE_KEYWORDS = (
    "\u4e2d\u6807",
    "\u589e\u6301",
    "\u56de\u8d2d",
    "\u4e1a\u7ee9\u589e\u957f",
    "\u653f\u7b56\u652f\u6301",
    "\u8ba2\u5355",
    "\u6da8\u4ef7",
    "\u63d0\u4ef7",
    "\u7a81\u7834",
    "\u521b\u65b0\u9ad8",
)
_NEGATIVE_KEYWORDS = (
    "\u51cf\u6301",
    "\u4e8f\u635f",
    "\u5904\u7f5a",
    "\u8c03\u67e5",
    "\u66b4\u96f7",
    "\u8fdd\u7ea6",
    "\u4e0b\u4fee",
    "\u4e1a\u7ee9\u4e0b\u964d",
    "\u89e3\u7981",
    "\u8dcc\u505c",
    "\u76d1\u7ba1\u51fd",
)
_CATEGORY_KEYWORDS = {
    "\u653f\u7b56": (
        "\u653f\u7b56",
        "\u53d1\u6539\u59d4",
        "\u80fd\u6e90\u5c40",
        "\u5de5\u4fe1\u90e8",
        "\u5546\u52a1\u90e8",
        "\u8d22\u653f\u90e8",
        "\u592e\u884c",
        "\u8bc1\u76d1\u4f1a",
    ),
    "\u4e1a\u7ee9": ("\u4e1a\u7ee9", "\u51c0\u5229", "\u8425\u6536", "\u5229\u6da6", "\u4e8f\u635f"),
    "\u884c\u4e1a": ("\u884c\u4e1a", "\u677f\u5757", "\u4ea7\u4e1a\u94fe", "\u666f\u6c14"),
    "\u8d44\u91d1": ("\u8d44\u91d1", "\u4e3b\u529b", "\u5317\u5411", "\u878d\u8d44", "\u878d\u5238"),
    "\u5730\u7f18\u653f\u6cbb": ("\u970d\u5c14\u6728\u5179", "\u5173\u7a0e", "\u5236\u88c1", "\u5730\u7f18"),
    "\u76d1\u7ba1": ("\u76d1\u7ba1", "\u7acb\u6848", "\u5904\u7f5a", "\u76d1\u7ba1\u51fd", "\u8bc1\u76d1\u4f1a"),
    "\u516c\u544a": ("\u516c\u544a", "\u505c\u724c", "\u590d\u724c", "\u51cf\u6301", "\u589e\u6301", "\u56de\u8d2d"),
    "\u5927\u5b97\u5546\u54c1": ("\u539f\u6cb9", "\u5929\u7136\u6c14", "\u7164\u70ad", "\u7535\u4ef7", "\u9ec4\u91d1"),
    "\u5b8f\u89c2": ("\u5b8f\u89c2", "\u7f8e\u5143", "\u5229\u7387", "\u901a\u80c0", "\u592e\u884c", "GDP"),
    "\u98ce\u9669": ("\u98ce\u9669", "\u8fdd\u7ea6", "\u66b4\u96f7", "\u4e8f\u635f", "\u4e0b\u4fee", "\u8dcc\u505c"),
}


class AkShareNewsUnavailableError(Exception):
    """Raised when AKShare news cannot be fetched by the provider."""


def _no_data(reason: str) -> str:
    return f"NO_DATA_AVAILABLE: {reason}"


def _ensure_akshare():
    if ak is None:
        raise AkShareNewsUnavailableError(
            "AKShare is not installed. Install it with `pip install akshare --upgrade`."
        )
    return ak


def _cached(key: tuple, fetcher: Callable[[], object]):
    if key not in _CACHE:
        _CACHE[key] = fetcher()
    return _CACHE[key]


def _clean_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return " ".join(str(value).strip().split())


def _row_get(row: dict, *names: str) -> str:
    for name in names:
        value = row.get(name, "")
        text = _clean_text(value)
        if text:
            return text
    return ""


def _normalize_datetime(value: str) -> str:
    value = _clean_text(value)
    if not value:
        return ""
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return value
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def _parse_datetime(value: str) -> datetime:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return datetime.min
    return parsed.to_pydatetime().replace(tzinfo=None)


def _records_from_df(df: pd.DataFrame) -> list[dict]:
    if df is None or df.empty:
        return []
    return df.to_dict("records")


def normalize_cn_ticker(symbol: str) -> str:
    """Normalize China A-share tickers to the six-digit code AKShare uses."""
    raw = _clean_text(symbol).upper()
    for suffix in (".SZ", ".SS", ".SH", ".BJ"):
        if raw.endswith(suffix):
            return raw[:-3]
    return raw


def get_cn_stock_name(symbol: str) -> str:
    """Resolve a China A-share code to its Chinese stock name via AKShare."""
    code = normalize_cn_ticker(symbol)
    if not (code.isdigit() and len(code) == 6):
        return ""

    def fetch_spot():
        client = _ensure_akshare()
        return client.stock_zh_a_spot_em()

    try:
        spot_df = _cached(("stock_zh_a_spot_em",), fetch_spot)
    except Exception as exc:
        logger.debug("AKShare A-share spot lookup failed for %s: %s", symbol, exc)
        return ""

    if spot_df is None or spot_df.empty:
        return ""

    for row in spot_df.to_dict("records"):
        row_code = _row_get(row, "代码", "code", "Code", "证券代码")
        if row_code == code:
            return _row_get(row, "名称", "股票简称", "股票名称", "name", "Name")
    return ""


def _short_stock_name(stock_name: str) -> str:
    short = _clean_text(stock_name)
    for suffix in _COMPANY_SUFFIXES:
        if short.endswith(suffix):
            short = short[: -len(suffix)]
    return short


def build_keywords(
    ticker: str,
    stock_name: str,
    extra_keywords: list[str] | None = None,
) -> list[str]:
    """Build keyword candidates for matching China A-share news text."""
    keywords = [
        normalize_cn_ticker(ticker),
        _clean_text(stock_name),
        _short_stock_name(stock_name),
    ]
    if extra_keywords:
        keywords.extend(extra_keywords)

    seen = set()
    result = []
    for keyword in keywords:
        keyword = _clean_text(keyword)
        if not keyword or keyword in seen:
            continue
        seen.add(keyword)
        result.append(keyword)
    return result


def filter_news_by_keywords(news_items: list[dict], keywords: list[str]) -> list[dict]:
    """Return news matching any keyword, or recent market news with a notice."""
    normalized = [_clean_text(keyword) for keyword in keywords if len(_clean_text(keyword)) >= 2]
    if not normalized:
        return list(news_items)

    matched = []
    for item in news_items:
        haystack = f"{item.get('title', '')} {item.get('content', '')}"
        if any(keyword in haystack for keyword in normalized):
            matched.append(item)
    if matched:
        return matched

    fallback = [dict(item) for item in news_items]
    if fallback:
        label = "/".join(normalized[:3])
        fallback[0]["_fallback_notice"] = (
            f"未找到直接匹配 {label} 的新闻，以下为最近市场快讯。"
        )
    return fallback


def _matched_keywords(text: str, keywords: tuple[str, ...]) -> list[str]:
    return [keyword for keyword in keywords if keyword and keyword in text]


def classify_cn_news_impact(
    item: dict,
    ticker: str = "",
    stock_name: str = "",
) -> dict:
    """Classify a Chinese market news item with simple A-share rules."""
    text = f"{item.get('title', '')} {item.get('content', '')}"
    matched_keywords: list[str] = []

    high_matches = _matched_keywords(text, _HIGH_IMPORTANCE_KEYWORDS)
    positive_matches = _matched_keywords(text, _POSITIVE_KEYWORDS)
    negative_matches = _matched_keywords(text, _NEGATIVE_KEYWORDS)
    matched_keywords.extend(high_matches)
    matched_keywords.extend(positive_matches)
    matched_keywords.extend(negative_matches)

    stock_keywords = build_keywords(ticker, stock_name) if ticker or stock_name else []
    stock_matches = [keyword for keyword in stock_keywords if keyword in text]
    matched_keywords.extend(stock_matches)

    categories = []
    for category, keywords in _CATEGORY_KEYWORDS.items():
        matches = _matched_keywords(text, keywords)
        if matches:
            categories.append(category)
            matched_keywords.extend(matches)

    if high_matches:
        importance = "high"
    elif positive_matches or negative_matches or categories:
        importance = "medium"
    else:
        importance = "low"

    if positive_matches and negative_matches:
        sentiment = "mixed"
    elif negative_matches:
        sentiment = "negative"
    elif positive_matches:
        sentiment = "positive"
    else:
        sentiment = "neutral"

    seen = set()
    unique_matches = []
    for keyword in matched_keywords:
        if keyword in seen:
            continue
        seen.add(keyword)
        unique_matches.append(keyword)

    return {
        "importance": importance,
        "sentiment": sentiment,
        "categories": categories,
        "matched_keywords": unique_matches,
    }


def _normalize_cls_row(row: dict) -> dict:
    raw = dict(row)
    title = _row_get(raw, "标题", "title", "Title")
    content = _row_get(raw, "内容", "摘要", "summary", "content", "Content")
    dt = _normalize_datetime(_row_get(raw, "发布时间", "发布日期", "时间", "datetime", "date"))
    return {
        "source": "财联社",
        "title": title,
        "content": content,
        "datetime": dt,
        "url": _row_get(raw, "链接", "url", "URL"),
        "raw": raw,
    }


def _normalize_ths_row(row: dict) -> dict:
    raw = dict(row)
    title = _row_get(raw, "标题", "title", "Title")
    content = _row_get(raw, "内容", "摘要", "summary", "content", "Content")
    dt = _normalize_datetime(_row_get(raw, "发布时间", "发布日期", "时间", "datetime", "date"))
    return {
        "source": "同花顺",
        "title": title,
        "content": content,
        "datetime": dt,
        "url": _row_get(raw, "链接", "url", "URL"),
        "raw": raw,
    }


def get_akshare_cls_news(symbol: str = "全部", limit: int = 20) -> list[dict]:
    """Fetch 财联社 market news from AKShare and normalize rows."""
    if symbol not in {"全部", "重点"}:
        symbol = "全部"
    try:
        client = _ensure_akshare()
        df = _cached(("cls", symbol), lambda: client.stock_info_global_cls(symbol=symbol))
        records = [_normalize_cls_row(row) for row in _records_from_df(df)]
        return records[:limit]
    except Exception as exc:
        logger.warning("AKShare 财联社 news fetch failed: %s", exc)
        return []


def get_akshare_ths_news(limit: int = 20) -> list[dict]:
    """Fetch 同花顺 market news from AKShare and normalize rows."""
    try:
        client = _ensure_akshare()
        df = _cached(("ths",), lambda: client.stock_info_global_ths())
        records = [_normalize_ths_row(row) for row in _records_from_df(df)]
        return records[:limit]
    except Exception as exc:
        logger.warning("AKShare 同花顺 news fetch failed: %s", exc)
        return []


def _dedupe_sort(news: list[dict]) -> list[dict]:
    seen: set[tuple[str, str, str]] = set()
    deduped = []
    for item in news:
        title = _clean_text(item.get("title"))
        content = _clean_text(item.get("content"))
        if not title and not content:
            continue
        key = (item.get("source", ""), title, item.get("datetime", ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return sorted(
        deduped,
        key=lambda item: _parse_datetime(item.get("datetime", "")),
        reverse=True,
    )


def _symbol_code(ticker: str) -> str:
    return normalize_cn_ticker(ticker)


def _stock_terms(ticker: str) -> list[str]:
    code = normalize_cn_ticker(ticker)
    stock_name = get_cn_stock_name(ticker)
    terms = set(build_keywords(ticker, stock_name))
    if not (code.isdigit() and len(code) == 6):
        return [term for term in terms if term]

    def fetch_info():
        client = _ensure_akshare()
        return client.stock_individual_info_em(symbol=code)

    try:
        info_df = _cached(("stock_info", code), fetch_info)
    except Exception as exc:
        logger.debug("AKShare stock info lookup failed for %s: %s", ticker, exc)
        return [term for term in terms if term]

    if info_df is None or info_df.empty:
        return [term for term in terms if term]

    for row in info_df.to_dict("records"):
        label = _row_get(row, "item", "项目", "指标")
        value = _row_get(row, "value", "值", "内容")
        if label in {"股票简称", "股票名称", "名称", "行业", "所属行业"} and value:
            terms.add(value)
    return [term for term in terms if term]


def _filter_by_terms(news: list[dict], terms: list[str]) -> list[dict]:
    filtered = filter_news_by_keywords(news, terms)
    if filtered and filtered[0].get("_fallback_notice"):
        return []
    return filtered


def _collect_news(limit: int, sources: list[str] | None = None) -> list[dict]:
    selected = {source.lower() for source in sources} if sources else {"cls", "财联社", "ths", "同花顺"}
    news: list[dict] = []
    fetch_limit = max(limit, 40)
    if selected & {"cls", "财联社"}:
        news.extend(get_akshare_cls_news("全部", fetch_limit))
        news.extend(get_akshare_cls_news("重点", fetch_limit))
    if selected & {"ths", "同花顺"}:
        news.extend(get_akshare_ths_news(fetch_limit))
    return _dedupe_sort(news)


def _format_news_block(title: str, news: list[dict], limit: int) -> str:
    if not news:
        return _no_data(f"No AKShare Chinese news found for {title}.")

    lines = [f"## {title}", ""]
    notice = _clean_text(news[0].get("_fallback_notice"))
    if notice:
        lines.extend([notice, ""])
    for item in news[:limit]:
        impact = classify_cn_news_impact(item)
        categories = ",".join(impact["categories"]) if impact["categories"] else "未分类"
        label = f"{impact['importance']}/{impact['sentiment']}/{categories}"
        lines.append(
            f"[{label}] {item.get('source', 'AKShare')} {item.get('datetime', '')} {item.get('title', '')}".strip()
        )
        content = _clean_text(item.get("content"))
        if content:
            lines.append(content)
        url = _clean_text(item.get("url"))
        if url:
            lines.append(url)
        lines.append("")
    return "\n".join(lines).strip()


def get_cn_market_news(
    ticker: str,
    curr_date: str,
    look_back_days: int = 1,
    limit: int = 40,
    sources: list[str] | None = None,
) -> str:
    """Return ticker-filtered Chinese market news, falling back to broad market news."""
    try:
        end_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    except ValueError:
        return _no_data(f"Invalid curr_date for AKShare Chinese news: {curr_date}")
    start_dt = end_dt - timedelta(days=look_back_days)

    try:
        all_news = _collect_news(limit, sources)
    except Exception as exc:
        logger.warning("AKShare Chinese market news collection failed: %s", exc)
        return _no_data(f"AKShare Chinese market news fetch failed: {exc}")

    dated_news = [
        item
        for item in all_news
        if start_dt <= _parse_datetime(item.get("datetime", "")) <= end_dt + timedelta(days=1)
    ]
    if not dated_news:
        dated_news = all_news

    code = normalize_cn_ticker(ticker)
    stock_name = get_cn_stock_name(ticker)
    keywords = _stock_terms(ticker) or build_keywords(ticker, stock_name)
    selected = filter_news_by_keywords(dated_news, keywords)
    matched = bool(selected) and not selected[0].get("_fallback_notice")
    if selected and not matched:
        label = f"{ticker}/{stock_name}" if stock_name else f"{ticker}/{code}"
        selected[0]["_fallback_notice"] = (
            f"未找到直接匹配 {label} 的新闻，以下为最近市场快讯。"
        )
    title = (
        f"AKShare Chinese news for {ticker} {stock_name}, from {start_dt:%Y-%m-%d} to {curr_date}"
        if matched
        else f"AKShare Chinese market news fallback for {ticker}, from {start_dt:%Y-%m-%d} to {curr_date}"
    )
    return _format_news_block(title, selected, limit)


def get_global_news_from_cn_sources(
    curr_date: str,
    look_back_days: int = 1,
    limit: int = 40,
) -> str:
    """Return broad Chinese market news from 财联社 and 同花顺."""
    try:
        end_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    except ValueError:
        return _no_data(f"Invalid curr_date for AKShare global Chinese news: {curr_date}")
    start_dt = end_dt - timedelta(days=look_back_days)

    try:
        all_news = _collect_news(limit)
    except Exception as exc:
        logger.warning("AKShare global Chinese news collection failed: %s", exc)
        return _no_data(f"AKShare global Chinese news fetch failed: {exc}")

    selected = [
        item
        for item in all_news
        if start_dt <= _parse_datetime(item.get("datetime", "")) <= end_dt + timedelta(days=1)
    ]
    if not selected:
        selected = all_news
    return _format_news_block(
        f"AKShare Chinese market news, from {start_dt:%Y-%m-%d} to {curr_date}",
        selected,
        limit,
    )


def get_news(ticker: str, start_date: str, end_date: str) -> str:
    """TradingAgents get_news-compatible wrapper."""
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        return _no_data(f"Invalid date range for AKShare Chinese news: {start_date} to {end_date}")
    look_back_days = max((end_dt - start_dt).days, 1)
    return get_cn_market_news(ticker, end_date, look_back_days, limit=40)


def get_global_news(
    curr_date: str,
    look_back_days: int | None = None,
    limit: int | None = None,
) -> str:
    """TradingAgents get_global_news-compatible wrapper."""
    return get_global_news_from_cn_sources(
        curr_date,
        look_back_days=look_back_days or 1,
        limit=limit or 40,
    )
