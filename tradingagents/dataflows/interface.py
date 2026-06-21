from datetime import datetime
from typing import Annotated

# Import from vendor-specific modules
from .y_finance import (
    get_YFin_data_online,
    get_stock_stats_indicators_window,
    get_fundamentals as get_yfinance_fundamentals,
    get_balance_sheet as get_yfinance_balance_sheet,
    get_cashflow as get_yfinance_cashflow,
    get_income_statement as get_yfinance_income_statement,
    get_insider_transactions as get_yfinance_insider_transactions,
)
from .yfinance_news import get_news_yfinance, get_global_news_yfinance
from .alpha_vantage import (
    get_stock as get_alpha_vantage_stock,
    get_indicator as get_alpha_vantage_indicator,
    get_fundamentals as get_alpha_vantage_fundamentals,
    get_balance_sheet as get_alpha_vantage_balance_sheet,
    get_cashflow as get_alpha_vantage_cashflow,
    get_income_statement as get_alpha_vantage_income_statement,
    get_insider_transactions as get_alpha_vantage_insider_transactions,
    get_news as get_alpha_vantage_news,
    get_global_news as get_alpha_vantage_global_news,
)
from .alpha_vantage_common import (
    AlphaVantageRateLimitError,
    AlphaVantageUnavailableError,
)
from .akshare_data import (
    AkShareUnavailableError,
    get_indicator as get_akshare_indicator,
    get_stock as get_akshare_stock,
)
from .tushare_data import (
    TushareUnavailableError,
    get_indicator as get_tushare_indicator,
    get_stock as get_tushare_stock,
)
from .tushare_fundamentals import (
    get_balance_sheet as get_tushare_balance_sheet,
    get_cashflow as get_tushare_cashflow,
    get_fundamentals as get_tushare_fundamentals,
    get_income_statement as get_tushare_income_statement,
)
from .akshare_news_provider import (
    AkShareNewsUnavailableError,
    get_cn_market_news,
    get_global_news_from_cn_sources,
)
from .symbol_utils import NoMarketDataError

# Configuration and routing logic
from .config import get_config

try:
    from yfinance.exceptions import YFRateLimitError
except ImportError:  # pragma: no cover - test environments may stub yfinance
    class YFRateLimitError(Exception):
        pass


_A_SHARE_SUFFIXES = (".SZ", ".SS", ".SH", ".BJ")


def _is_a_share_ticker(ticker: str) -> bool:
    if not isinstance(ticker, str):
        return False
    upper = ticker.strip().upper()
    if upper.isdigit() and len(upper) == 6:
        return True
    return (
        len(upper) == 9
        and upper[:6].isdigit()
        and upper.endswith(_A_SHARE_SUFFIXES)
    )


def _get_cn_market_news_for_range(ticker: str, start_date: str, end_date: str) -> str:
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    look_back_days = max((end_dt - start_dt).days, 1)
    return get_cn_market_news(ticker, end_date, look_back_days=look_back_days)


def _move_vendor(vendors: list[str], vendor_name: str, first: bool) -> list[str]:
    selected = [vendor for vendor in vendors if vendor == vendor_name]
    others = [vendor for vendor in vendors if vendor != vendor_name]
    return selected + others if first else others + selected


def _move_vendors(vendors: list[str], vendor_names: list[str], first: bool) -> list[str]:
    selected = [vendor for name in vendor_names for vendor in vendors if vendor == name]
    others = [vendor for vendor in vendors if vendor not in vendor_names]
    return selected + others if first else others + selected


def _prioritize_vendors(method: str, vendors: list[str], args: tuple) -> list[str]:
    if not args:
        return vendors

    is_a_share = _is_a_share_ticker(args[0])
    if method == "get_news":
        return _move_vendor(vendors, "akshare_news", first=is_a_share)
    if method in {"get_stock_data", "get_indicators"}:
        return _move_vendors(vendors, ["tushare", "akshare"], first=is_a_share)
    if method in {
        "get_fundamentals",
        "get_balance_sheet",
        "get_cashflow",
        "get_income_statement",
    }:
        return _move_vendor(vendors, "tushare", first=is_a_share)
    return vendors


def _build_fallback_vendors(method: str, primary_vendors: list[str], args: tuple) -> list[str]:
    """Return the vendor chain for a tool call.

    For China A-shares, an explicit AKShare market-data configuration should
    not silently fall through to Yahoo Finance. Yahoo rate limits are common,
    and for `.SH`/`.SZ` symbols AKShare is the intended local data source.
    Users can still opt into Yahoo by listing `yfinance` in the vendor config.
    """
    if (
        method in {"get_stock_data", "get_indicators"}
        and args
        and _is_a_share_ticker(args[0])
        and ("tushare" in primary_vendors or "akshare" in primary_vendors)
        and "yfinance" not in primary_vendors
    ):
        return _prioritize_vendors(method, primary_vendors.copy(), args)

    # Build fallback chain: primary vendors first, then remaining available vendors
    all_available_vendors = list(VENDOR_METHODS[method].keys())
    fallback_vendors = primary_vendors.copy()
    for vendor in all_available_vendors:
        if vendor not in fallback_vendors:
            fallback_vendors.append(vendor)
    return _prioritize_vendors(method, fallback_vendors, args)


def format_data_vendor_unavailable(error: Exception, method: str | None = None) -> str:
    """Return an agent-readable provider failure with remediation hints."""
    error_type = type(error).__name__
    message = str(error)
    lowered = f"{error_type} {message}".lower()

    provider = "unknown"
    reason = "unavailable"
    action = "Retry later or choose another configured data vendor."

    if isinstance(error, YFRateLimitError) or "yfratelimiterror" in lowered or "too many requests" in lowered:
        provider = "Yahoo Finance / yfinance"
        reason = "rate_limited"
        action = (
            "yfinance has no official paid quota in this project path. Reduce repeated "
            "calls, wait before retrying, use cached data, or switch the affected tool "
            "to AKShare/Alpha Vantage where available."
        )
    elif isinstance(error, AlphaVantageRateLimitError) or "alpha vantage rate limit" in lowered:
        provider = "Alpha Vantage"
        reason = "rate_limited_or_quota_exceeded"
        action = (
            "Check Alpha Vantage plan limits for your API key. Free keys are commonly "
            "limited by per-day and per-minute/per-second quotas; upgrade the plan or "
            "reduce indicator calls."
        )
    elif isinstance(error, AlphaVantageUnavailableError) or "premium endpoint" in lowered:
        provider = "Alpha Vantage"
        reason = "endpoint_unavailable_or_plan_required"
        action = "Use an Alpha Vantage plan that includes this endpoint, or switch vendors."
    elif isinstance(error, TushareUnavailableError):
        provider = "Tushare"
        reason = "upstream_unreachable_or_token_error"
        action = (
            "Check TUSHARE_TOKEN in .env, confirm the tushare package is installed, "
            "and verify your Tushare quota/network access."
        )
    elif isinstance(error, (AkShareUnavailableError, AkShareNewsUnavailableError)):
        provider = "AKShare / EastMoney"
        reason = "upstream_unreachable_or_proxy_error"
        action = (
            "This usually means EastMoney/AKShare could not be reached. Check proxy/VPN "
            "settings, try direct network access, or set TRADINGAGENTS_AKSHARE_TRUST_ENV=true "
            "only if your network requires a working proxy."
        )

    method_text = f"\n- Tool method: {method}" if method else ""
    return (
        "DATA_VENDOR_UNAVAILABLE:\n"
        f"- Provider: {provider}{method_text}\n"
        f"- Reason: {reason}\n"
        f"- Error type: {error_type}\n"
        f"- Error detail: {message}\n"
        f"- Suggested action: {action}\n"
        "Do not estimate or fabricate values from this unavailable source."
    )

# Tools organized by category
TOOLS_CATEGORIES = {
    "core_stock_apis": {
        "description": "OHLCV stock price data",
        "tools": [
            "get_stock_data"
        ]
    },
    "technical_indicators": {
        "description": "Technical analysis indicators",
        "tools": [
            "get_indicators"
        ]
    },
    "fundamental_data": {
        "description": "Company fundamentals",
        "tools": [
            "get_fundamentals",
            "get_balance_sheet",
            "get_cashflow",
            "get_income_statement"
        ]
    },
    "news_data": {
        "description": "News and insider data",
        "tools": [
            "get_news",
            "get_global_news",
            "get_insider_transactions",
        ]
    }
}

VENDOR_LIST = [
    "yfinance",
    "alpha_vantage",
    "tushare",
    "akshare",
    "akshare_news",
]

# Mapping of methods to their vendor-specific implementations
VENDOR_METHODS = {
    # core_stock_apis
    "get_stock_data": {
        "alpha_vantage": get_alpha_vantage_stock,
        "yfinance": get_YFin_data_online,
        "tushare": get_tushare_stock,
        "akshare": get_akshare_stock,
    },
    # technical_indicators
    "get_indicators": {
        "alpha_vantage": get_alpha_vantage_indicator,
        "yfinance": get_stock_stats_indicators_window,
        "tushare": get_tushare_indicator,
        "akshare": get_akshare_indicator,
    },
    # fundamental_data
    "get_fundamentals": {
        "alpha_vantage": get_alpha_vantage_fundamentals,
        "yfinance": get_yfinance_fundamentals,
        "tushare": get_tushare_fundamentals,
    },
    "get_balance_sheet": {
        "alpha_vantage": get_alpha_vantage_balance_sheet,
        "yfinance": get_yfinance_balance_sheet,
        "tushare": get_tushare_balance_sheet,
    },
    "get_cashflow": {
        "alpha_vantage": get_alpha_vantage_cashflow,
        "yfinance": get_yfinance_cashflow,
        "tushare": get_tushare_cashflow,
    },
    "get_income_statement": {
        "alpha_vantage": get_alpha_vantage_income_statement,
        "yfinance": get_yfinance_income_statement,
        "tushare": get_tushare_income_statement,
    },
    # news_data
    "get_news": {
        "alpha_vantage": get_alpha_vantage_news,
        "yfinance": get_news_yfinance,
        "akshare_news": _get_cn_market_news_for_range,
    },
    "get_global_news": {
        "yfinance": get_global_news_yfinance,
        "alpha_vantage": get_alpha_vantage_global_news,
        "akshare_news": get_global_news_from_cn_sources,
    },
    "get_insider_transactions": {
        "alpha_vantage": get_alpha_vantage_insider_transactions,
        "yfinance": get_yfinance_insider_transactions,
    },
}

def get_category_for_method(method: str) -> str:
    """Get the category that contains the specified method."""
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"Method '{method}' not found in any category")

def get_vendor(category: str, method: str = None) -> str:
    """Get the configured vendor for a data category or specific tool method.
    Tool-level configuration takes precedence over category-level.
    """
    config = get_config()

    # Check tool-level configuration first (if method provided)
    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]

    # Fall back to category-level configuration
    return config.get("data_vendors", {}).get(category, "default")

def route_to_vendor(method: str, *args, **kwargs):
    """Route method calls to appropriate vendor implementation with fallback support."""
    category = get_category_for_method(method)
    vendor_config = get_vendor(category, method)
    primary_vendors = [v.strip() for v in vendor_config.split(',')]

    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    fallback_vendors = _build_fallback_vendors(method, primary_vendors, args)

    last_no_data: NoMarketDataError | None = None
    last_no_data_text: str | None = None
    first_unavailable_error: Exception | None = None
    first_error: Exception | None = None
    for vendor in fallback_vendors:
        if vendor not in VENDOR_METHODS[method]:
            continue

        vendor_impl = VENDOR_METHODS[method][vendor]
        impl_func = vendor_impl[0] if isinstance(vendor_impl, list) else vendor_impl

        try:
            result = impl_func(*args, **kwargs)
            if isinstance(result, str) and result.startswith("NO_DATA_AVAILABLE:"):
                last_no_data_text = result
                continue
            return result
        except (
            AlphaVantageRateLimitError,
            AlphaVantageUnavailableError,
            TushareUnavailableError,
            AkShareUnavailableError,
            AkShareNewsUnavailableError,
            YFRateLimitError,
        ) as e:
            if first_unavailable_error is None:
                first_unavailable_error = e
            continue  # Vendor unavailable: try the next vendor
        except NoMarketDataError as e:
            last_no_data = e  # No data here; another vendor may have it
            continue
        except Exception as e:
            # A fallback vendor failing for an incidental reason (e.g. no API
            # key configured) must not crash the call when another vendor
            # already determined the symbol simply has no data. Remember the
            # first error so a genuine primary-vendor failure still surfaces.
            if first_error is None:
                first_error = e
            continue

    # If any vendor reported "no data", the symbol is genuinely unavailable.
    # Return one explicit, instructive sentinel rather than a vendor-specific
    # empty string, so the agent reports "unavailable" instead of inventing a
    # value. This takes precedence over incidental fallback errors.
    if last_no_data is not None:
        sym = last_no_data.symbol
        canonical = last_no_data.canonical
        resolved = "" if canonical == sym else f" (resolved to '{canonical}')"
        return (
            f"NO_DATA_AVAILABLE: No market data found for '{sym}'{resolved} from "
            f"any configured vendor. The symbol may be invalid, delisted, or not "
            f"covered by Yahoo Finance / Alpha Vantage / Tushare / AKShare. Do not estimate or "
            f"fabricate values — report that data is unavailable for this symbol."
        )

    # No vendor returned data and none reported clean "no data" — surface the
    # first real error (e.g. the primary vendor's network failure).
    if last_no_data_text is not None:
        return last_no_data_text

    if first_unavailable_error is not None:
        return format_data_vendor_unavailable(first_unavailable_error, method)

    if first_error is not None:
        raise first_error

    raise RuntimeError(f"No available vendor for '{method}'")
