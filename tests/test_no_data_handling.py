"""Tests that empty vendor results never become fabricated data.

Covers two systematic fixes:
  - load_ohlcv must not cache an empty download (cache poisoning), and must
    raise NoMarketDataError instead of returning an empty frame.
  - route_to_vendor must convert NoMarketDataError into a single explicit
    "NO_DATA_AVAILABLE" sentinel after all vendors are exhausted.
"""

import os
import sys
import types
import unittest
from unittest import mock

import pandas as pd
import pytest
import requests

try:
    import yfinance  # noqa: F401
except ImportError:
    fake_yfinance = types.ModuleType("yfinance")
    fake_yfinance.download = lambda *args, **kwargs: pd.DataFrame()
    fake_yfinance_exceptions = types.ModuleType("yfinance.exceptions")

    class YFRateLimitError(Exception):
        pass

    fake_yfinance_exceptions.YFRateLimitError = YFRateLimitError
    fake_yfinance.exceptions = fake_yfinance_exceptions
    sys.modules.setdefault("yfinance", fake_yfinance)
    sys.modules.setdefault("yfinance.exceptions", fake_yfinance_exceptions)

try:
    import stockstats  # noqa: F401
except ImportError:
    fake_stockstats = types.ModuleType("stockstats")
    fake_stockstats.wrap = lambda data: data
    sys.modules.setdefault("stockstats", fake_stockstats)

from tradingagents.dataflows import stockstats_utils, interface
from tradingagents.dataflows.alpha_vantage_common import (
    AlphaVantageRateLimitError,
    AlphaVantageUnavailableError,
    _make_api_request,
)
from tradingagents.dataflows.alpha_vantage_indicator import get_indicator
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.symbol_utils import NoMarketDataError
from yfinance.exceptions import YFRateLimitError


@pytest.mark.unit
class TestLoadOhlcvNoPoison(unittest.TestCase):
    def setUp(self):
        self._tmp = os.path.join(os.path.dirname(__file__), "_tmp_cache")
        os.makedirs(self._tmp, exist_ok=True)
        set_config({"data_cache_dir": self._tmp})

    def tearDown(self):
        for f in os.listdir(self._tmp):
            os.remove(os.path.join(self._tmp, f))
        os.rmdir(self._tmp)

    def test_empty_download_raises_and_does_not_cache(self):
        empty = pd.DataFrame()
        with mock.patch.object(stockstats_utils.yf, "download", return_value=empty) as dl:
            with self.assertRaises(NoMarketDataError):
                stockstats_utils.load_ohlcv("FAKE", "2026-01-01")
        # Nothing should have been written to the cache.
        self.assertEqual(os.listdir(self._tmp), [])

        # A second call must re-attempt the fetch (no poisoned cache served).
        with mock.patch.object(stockstats_utils.yf, "download", return_value=empty) as dl2:
            with self.assertRaises(NoMarketDataError):
                stockstats_utils.load_ohlcv("FAKE", "2026-01-01")
            self.assertTrue(dl2.called)


@pytest.mark.unit
class TestRouteToVendorSentinel(unittest.TestCase):
    def test_no_data_from_all_vendors_returns_sentinel(self):
        def raises_no_data(symbol, *a, **k):
            raise NoMarketDataError(symbol, "GC=F", "no rows")

        patched = {"yfinance": raises_no_data, "alpha_vantage": raises_no_data}
        with mock.patch.dict(
            interface.VENDOR_METHODS, {"get_stock_data": patched}, clear=False
        ):
            result = interface.route_to_vendor(
                "get_stock_data", "XAUUSD+", "2026-01-01", "2026-01-10"
            )
        self.assertIn("NO_DATA_AVAILABLE", result)
        self.assertIn("XAUUSD+", result)
        self.assertIn("GC=F", result)
        self.assertIn("Do not estimate", result)

    def test_unconfigured_fallback_does_not_mask_no_data(self):
        # When the primary vendor reports no data and the fallback is simply
        # unavailable (e.g. missing API key -> raises), the no-data sentinel
        # must win rather than the fallback's incidental error crashing out.
        def raises_no_data(symbol, *a, **k):
            raise NoMarketDataError(symbol, symbol, "no rows")

        def raises_unavailable(symbol, *a, **k):
            raise ValueError("ALPHA_VANTAGE_API_KEY environment variable is not set.")

        patched = {"yfinance": raises_no_data, "alpha_vantage": raises_unavailable}
        with mock.patch.dict(
            interface.VENDOR_METHODS, {"get_stock_data": patched}, clear=False
        ):
            result = interface.route_to_vendor(
                "get_stock_data", "FAKE", "2026-01-01", "2026-01-10"
            )
        self.assertIn("NO_DATA_AVAILABLE", result)

    def test_alpha_vantage_unavailable_falls_back(self):
        def raises_unavailable(symbol, *a, **k):
            raise AlphaVantageUnavailableError("premium endpoint")

        def returns_data(symbol, *a, **k):
            return "ok"

        patched = {"alpha_vantage": raises_unavailable, "yfinance": returns_data}
        with mock.patch.dict(
            interface.VENDOR_METHODS, {"get_stock_data": patched}, clear=False
        ):
            set_config({"data_vendors": {"core_stock_apis": "alpha_vantage"}})
            result = interface.route_to_vendor(
                "get_stock_data", "NVDA", "2026-01-01", "2026-01-10"
            )
        self.assertEqual(result, "ok")

    def test_yfinance_rate_limit_returns_actionable_vendor_message(self):
        def raises_rate_limit(symbol, *a, **k):
            raise YFRateLimitError("Too Many Requests. Rate limited. Try after a while.")

        patched = {"yfinance": raises_rate_limit}
        with mock.patch.dict(
            interface.VENDOR_METHODS, {"get_stock_data": patched}, clear=False
        ):
            set_config({"data_vendors": {"core_stock_apis": "yfinance"}})
            result = interface.route_to_vendor(
                "get_stock_data", "NVDA", "2026-01-01", "2026-01-10"
            )
        self.assertIn("DATA_VENDOR_UNAVAILABLE", result)
        self.assertIn("Provider: Yahoo Finance / yfinance", result)
        self.assertIn("rate_limited", result)
        self.assertIn("no official paid quota", result)

    def test_alpha_vantage_rate_limit_returns_plan_hint(self):
        def raises_rate_limit(symbol, *a, **k):
            raise AlphaVantageRateLimitError("Alpha Vantage rate limit exceeded")

        patched = {"alpha_vantage": raises_rate_limit}
        with mock.patch.dict(
            interface.VENDOR_METHODS, {"get_stock_data": patched}, clear=False
        ):
            set_config({"data_vendors": {"core_stock_apis": "alpha_vantage"}})
            result = interface.route_to_vendor(
                "get_stock_data", "IBM", "2026-01-01", "2026-01-10"
            )
        self.assertIn("DATA_VENDOR_UNAVAILABLE", result)
        self.assertIn("Provider: Alpha Vantage", result)
        self.assertIn("rate_limited_or_quota_exceeded", result)
        self.assertIn("upgrade the plan", result)


@pytest.mark.unit
class TestAlphaVantageErrors(unittest.TestCase):
    def test_premium_endpoint_response_raises_before_csv_parsing(self):
        response = mock.Mock()
        response.text = (
            '{"Information": "Thank you for using Alpha Vantage! '
            'This is a premium endpoint."}'
        )
        response.raise_for_status.return_value = None

        with mock.patch(
            "tradingagents.dataflows.alpha_vantage_common.get_api_key",
            return_value="test-key",
        ):
            with mock.patch(
                "tradingagents.dataflows.alpha_vantage_common.requests.get",
                return_value=response,
            ):
                with self.assertRaises(AlphaVantageUnavailableError):
                    _make_api_request("TIME_SERIES_DAILY_ADJUSTED", {"symbol": "IBM"})

    def test_network_error_redacts_api_key_and_is_unavailable(self):
        raw_error = (
            "HTTPSConnectionPool(host='www.alphavantage.co', port=443): "
            "Max retries exceeded with url: "
            "/query?symbol=GOLD&function=EMA&apikey=SECRET123&source=trading_agents "
            "(Caused by SSLError('wrong version number'))"
        )

        with mock.patch(
            "tradingagents.dataflows.alpha_vantage_common.get_api_key",
            return_value="SECRET123",
        ):
            with mock.patch(
                "tradingagents.dataflows.alpha_vantage_common.requests.get",
                side_effect=requests.exceptions.SSLError(raw_error),
            ):
                with self.assertRaises(AlphaVantageUnavailableError) as ctx:
                    _make_api_request("EMA", {"symbol": "GOLD"})

        message = str(ctx.exception)
        self.assertIn("Alpha Vantage request unavailable for EMA", message)
        self.assertIn("apikey=<redacted>", message)
        self.assertNotIn("SECRET123", message)

    def test_indicator_unavailable_falls_back(self):
        def raises_unavailable(*args, **kwargs):
            raise AlphaVantageUnavailableError("network down")

        def returns_data(*args, **kwargs):
            return "yfinance-indicator-ok"

        patched = {
            "alpha_vantage": raises_unavailable,
            "yfinance": returns_data,
        }
        with mock.patch.dict(
            interface.VENDOR_METHODS, {"get_indicators": patched}, clear=False
        ):
            set_config({"data_vendors": {"technical_indicators": "alpha_vantage"}})
            result = interface.route_to_vendor(
                "get_indicators", "GOLD", "rsi", "2026-06-10", 30
            )
        self.assertEqual(result, "yfinance-indicator-ok")

    def test_indicator_propagates_alpha_vantage_unavailable(self):
        with mock.patch(
            "tradingagents.dataflows.alpha_vantage_indicator._make_api_request",
            side_effect=AlphaVantageUnavailableError("network down"),
        ):
            with self.assertRaises(AlphaVantageUnavailableError):
                get_indicator("GOLD", "rsi", "2026-06-10", 30)


if __name__ == "__main__":
    unittest.main()
