import os
import sys
import types
import unittest
from unittest import mock

import pandas as pd
import pytest

import tradingagents.default_config as default_config

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

from tradingagents.dataflows import interface
from tradingagents.dataflows import stockstats_utils
from tradingagents.dataflows.akshare_data import AkShareUnavailableError, get_stock
from tradingagents.dataflows.config import set_config


@pytest.mark.unit
class TestAkShareData(unittest.TestCase):
    def setUp(self):
        set_config(default_config.DEFAULT_CONFIG.copy())

    def tearDown(self):
        set_config(default_config.DEFAULT_CONFIG.copy())

    def test_get_stock_normalizes_a_share_symbol_and_columns(self):
        calls = {}

        fake_akshare = types.SimpleNamespace()

        def stock_zh_a_hist(**kwargs):
            calls.update(kwargs)
            return pd.DataFrame(
                {
                    "日期": ["2026-06-09", "2026-06-10"],
                    "开盘": [10.0, 10.2],
                    "收盘": [10.1, 10.3],
                    "最高": [10.4, 10.5],
                    "最低": [9.9, 10.1],
                    "成交量": [1000, 1200],
                    "成交额": [10100, 12360],
                    "换手率": [1.1, 1.2],
                }
            )

        fake_akshare.stock_zh_a_hist = stock_zh_a_hist

        with mock.patch.dict(sys.modules, {"akshare": fake_akshare}):
            result = get_stock("000977.SZ", "2026-06-09", "2026-06-10")

        self.assertEqual(calls["symbol"], "000977")
        self.assertEqual(calls["period"], "daily")
        self.assertEqual(calls["start_date"], "20260609")
        self.assertEqual(calls["end_date"], "20260610")
        self.assertIn("# Stock data for 000977.SZ from AKShare (000977)", result)
        self.assertIn("Date,Open,High,Low,Close,Volume,Amount,Turnover", result)

    def test_get_stock_accepts_shanghai_sh_alias(self):
        fake_akshare = types.SimpleNamespace()

        def stock_zh_a_hist(**kwargs):
            self.assertEqual(kwargs["symbol"], "600519")
            return pd.DataFrame(
                {
                    "\u65e5\u671f": ["2026-06-10"],
                    "\u5f00\u76d8": [1600.0],
                    "\u6536\u76d8": [1601.0],
                    "\u6700\u9ad8": [1605.0],
                    "\u6700\u4f4e": [1590.0],
                    "\u6210\u4ea4\u91cf": [1000],
                }
            )

        fake_akshare.stock_zh_a_hist = stock_zh_a_hist

        with mock.patch.dict(sys.modules, {"akshare": fake_akshare}):
            result = get_stock("600519.SH", "2026-06-10", "2026-06-10")

        self.assertIn("# Stock data for 600519.SH from AKShare (600519)", result)

    def test_route_to_vendor_can_use_akshare_first(self):
        with mock.patch.dict(
            interface.VENDOR_METHODS,
            {"get_stock_data": {"akshare": lambda *args: "akshare-ok"}},
            clear=False,
        ):
            set_config({"data_vendors": {"core_stock_apis": "akshare"}})
            result = interface.route_to_vendor(
                "get_stock_data", "000977.SZ", "2026-06-09", "2026-06-10"
            )
        self.assertEqual(result, "akshare-ok")

    def test_a_share_stock_data_prefers_akshare(self):
        calls = []

        def yfinance_stock(*args):
            calls.append("yfinance")
            return "yfinance-ok"

        def akshare_stock(*args):
            calls.append("akshare")
            return "akshare-ok"

        with mock.patch.dict(
            interface.VENDOR_METHODS,
            {"get_stock_data": {"yfinance": yfinance_stock, "akshare": akshare_stock}},
            clear=False,
        ):
            set_config({"data_vendors": {"core_stock_apis": "yfinance,akshare"}})
            result = interface.route_to_vendor(
                "get_stock_data", "600519.SH", "2026-06-09", "2026-06-10"
            )
        self.assertEqual(result, "akshare-ok")
        self.assertEqual(calls, ["akshare"])

    def test_a_share_akshare_config_does_not_auto_fallback_to_yfinance(self):
        calls = []

        def akshare_stock(*args):
            calls.append("akshare")
            raise AkShareUnavailableError("akshare down")

        def alpha_vantage_stock(*args):
            calls.append("alpha_vantage")
            return "alpha-vantage-should-not-run"

        def yfinance_stock(*args):
            calls.append("yfinance")
            return "yfinance-should-not-run"

        with mock.patch.dict(
            interface.VENDOR_METHODS,
            {
                "get_stock_data": {
                    "alpha_vantage": alpha_vantage_stock,
                    "yfinance": yfinance_stock,
                    "akshare": akshare_stock,
                }
            },
            clear=False,
        ):
            set_config({"data_vendors": {"core_stock_apis": "akshare"}})
            result = interface.route_to_vendor(
                "get_stock_data", "600519.SH", "2026-06-09", "2026-06-10"
            )
        self.assertIn("DATA_VENDOR_UNAVAILABLE", result)
        self.assertIn("Provider: AKShare / EastMoney", result)
        self.assertIn("Error type: AkShareUnavailableError", result)
        self.assertIn("akshare down", result)
        self.assertEqual(calls, ["akshare"])

    def test_us_stock_data_keeps_yfinance_first(self):
        calls = []

        def yfinance_stock(*args):
            calls.append("yfinance")
            return "yfinance-ok"

        def akshare_stock(*args):
            calls.append("akshare")
            return "akshare-ok"

        with mock.patch.dict(
            interface.VENDOR_METHODS,
            {"get_stock_data": {"akshare": akshare_stock, "yfinance": yfinance_stock}},
            clear=False,
        ):
            set_config({"data_vendors": {"core_stock_apis": "akshare,yfinance"}})
            result = interface.route_to_vendor(
                "get_stock_data", "NVDA", "2026-06-09", "2026-06-10"
            )
        self.assertEqual(result, "yfinance-ok")
        self.assertEqual(calls, ["yfinance"])

    def test_a_share_indicators_prefer_akshare(self):
        calls = []

        def yfinance_indicator(*args):
            calls.append("yfinance")
            return "yfinance-indicator"

        def akshare_indicator(*args):
            calls.append("akshare")
            return "akshare-indicator"

        with mock.patch.dict(
            interface.VENDOR_METHODS,
            {
                "get_indicators": {
                    "yfinance": yfinance_indicator,
                    "akshare": akshare_indicator,
                }
            },
            clear=False,
        ):
            set_config({"data_vendors": {"technical_indicators": "yfinance,akshare"}})
            result = interface.route_to_vendor(
                "get_indicators", "000977.SZ", "rsi", "2026-06-10", 30
            )
        self.assertEqual(result, "akshare-indicator")
        self.assertEqual(calls, ["akshare"])

    def test_stockstats_loader_uses_akshare_for_configured_a_share(self):
        fake_akshare = types.SimpleNamespace()

        def stock_zh_a_hist(**kwargs):
            self.assertEqual(kwargs["symbol"], "600519")
            return pd.DataFrame(
                {
                    "日期": ["2026-06-09", "2026-06-10"],
                    "开盘": [10.0, 10.2],
                    "收盘": [10.1, 10.3],
                    "最高": [10.4, 10.5],
                    "最低": [9.9, 10.1],
                    "成交量": [1000, 1200],
                }
            )

        fake_akshare.stock_zh_a_hist = stock_zh_a_hist
        set_config({"data_vendors": {"core_stock_apis": "akshare"}})

        with mock.patch.dict(sys.modules, {"akshare": fake_akshare}):
            with mock.patch.object(
                stockstats_utils.yf,
                "download",
                side_effect=AssertionError("yfinance should not be called"),
            ):
                data = stockstats_utils.load_ohlcv("600519.SH", "2026-06-10")

        self.assertEqual(list(data["Close"]), [10.1, 10.3])

    def test_akshare_loader_ignores_proxy_env_by_default(self):
        fake_akshare = types.SimpleNamespace()

        def stock_zh_a_hist(**kwargs):
            self.assertNotIn("HTTPS_PROXY", os.environ)
            self.assertEqual(os.environ.get("NO_PROXY"), "*")
            return pd.DataFrame(
                {
                    "日期": ["2026-06-10"],
                    "开盘": [10.2],
                    "收盘": [10.3],
                    "最高": [10.5],
                    "最低": [10.1],
                    "成交量": [1200],
                }
            )

        fake_akshare.stock_zh_a_hist = stock_zh_a_hist
        os.environ["HTTPS_PROXY"] = "http://bad-proxy.invalid:9999"
        try:
            set_config({
                "akshare_trust_env": False,
                "data_vendors": {"core_stock_apis": "akshare"},
            })
            with mock.patch.dict(sys.modules, {"akshare": fake_akshare}):
                data = stockstats_utils.load_ohlcv("600519.SH", "2026-06-10")
            self.assertEqual(list(data["Close"]), [10.3])
            self.assertEqual(os.environ["HTTPS_PROXY"], "http://bad-proxy.invalid:9999")
        finally:
            os.environ.pop("HTTPS_PROXY", None)


if __name__ == "__main__":
    unittest.main()
