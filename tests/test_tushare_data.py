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
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.tushare_data import TushareUnavailableError, get_stock


@pytest.mark.unit
class TestTushareData(unittest.TestCase):
    def setUp(self):
        self._old_token = os.environ.get("TUSHARE_TOKEN")
        os.environ["TUSHARE_TOKEN"] = "test-token"
        set_config(default_config.DEFAULT_CONFIG.copy())

    def tearDown(self):
        if self._old_token is None:
            os.environ.pop("TUSHARE_TOKEN", None)
        else:
            os.environ["TUSHARE_TOKEN"] = self._old_token
        set_config(default_config.DEFAULT_CONFIG.copy())

    def test_get_stock_uses_tushare_daily_and_normalizes_columns(self):
        calls = {}
        fake_tushare = types.SimpleNamespace()

        class FakePro:
            def daily(self, **kwargs):
                calls.update(kwargs)
                return pd.DataFrame(
                    {
                        "ts_code": ["000977.SZ", "000977.SZ"],
                        "trade_date": ["20260610", "20260609"],
                        "open": [10.2, 10.0],
                        "high": [10.5, 10.4],
                        "low": [10.1, 9.9],
                        "close": [10.3, 10.1],
                        "vol": [1200, 1000],
                        "amount": [12360, 10100],
                    }
                )

        fake_tushare.pro_api = lambda token=None: FakePro()

        with mock.patch.dict(sys.modules, {"tushare": fake_tushare}):
            result = get_stock("000977.SZ", "2026-06-09", "2026-06-10")

        self.assertEqual(calls["ts_code"], "000977.SZ")
        self.assertEqual(calls["start_date"], "20260609")
        self.assertEqual(calls["end_date"], "20260610")
        self.assertIn("# Stock data for 000977.SZ from Tushare (000977.SZ)", result)
        self.assertIn("Date,Open,High,Low,Close,Volume,Amount", result)
        self.assertLess(result.find("2026-06-09"), result.find("2026-06-10"))

    def test_get_stock_accepts_shanghai_ss_alias(self):
        calls = {}
        fake_tushare = types.SimpleNamespace()

        class FakePro:
            def daily(self, **kwargs):
                calls.update(kwargs)
                return pd.DataFrame(
                    {
                        "trade_date": ["20260610"],
                        "open": [1600.0],
                        "high": [1605.0],
                        "low": [1590.0],
                        "close": [1601.0],
                        "vol": [1000],
                    }
                )

        fake_tushare.pro_api = lambda token=None: FakePro()

        with mock.patch.dict(sys.modules, {"tushare": fake_tushare}):
            result = get_stock("600519.SS", "2026-06-10", "2026-06-10")

        self.assertEqual(calls["ts_code"], "600519.SH")
        self.assertIn("# Stock data for 600519.SS from Tushare (600519.SH)", result)

    def test_missing_token_is_actionable(self):
        os.environ.pop("TUSHARE_TOKEN", None)
        fake_tushare = types.SimpleNamespace(pro_api=lambda token=None: object())

        with mock.patch.dict(sys.modules, {"tushare": fake_tushare}):
            with self.assertRaises(TushareUnavailableError) as ctx:
                get_stock("000977.SZ", "2026-06-09", "2026-06-10")

        self.assertIn("TUSHARE_TOKEN is not set", str(ctx.exception))

    def test_a_share_stock_data_prefers_tushare(self):
        calls = []

        def yfinance_stock(*args):
            calls.append("yfinance")
            return "yfinance-ok"

        def akshare_stock(*args):
            calls.append("akshare")
            return "akshare-ok"

        def tushare_stock(*args):
            calls.append("tushare")
            return "tushare-ok"

        with mock.patch.dict(
            interface.VENDOR_METHODS,
            {
                "get_stock_data": {
                    "akshare": akshare_stock,
                    "tushare": tushare_stock,
                    "yfinance": yfinance_stock,
                }
            },
            clear=False,
        ):
            set_config({"data_vendors": {"core_stock_apis": "akshare,tushare,yfinance"}})
            result = interface.route_to_vendor(
                "get_stock_data", "600519.SH", "2026-06-09", "2026-06-10"
            )

        self.assertEqual(result, "tushare-ok")
        self.assertEqual(calls, ["tushare"])

    def test_non_a_share_keeps_yfinance_first(self):
        calls = []

        def yfinance_stock(*args):
            calls.append("yfinance")
            return "yfinance-ok"

        def akshare_stock(*args):
            calls.append("akshare")
            return "akshare-ok"

        def tushare_stock(*args):
            calls.append("tushare")
            return "tushare-ok"

        with mock.patch.dict(
            interface.VENDOR_METHODS,
            {
                "get_stock_data": {
                    "tushare": tushare_stock,
                    "akshare": akshare_stock,
                    "yfinance": yfinance_stock,
                }
            },
            clear=False,
        ):
            set_config({"data_vendors": {"core_stock_apis": "tushare,akshare,yfinance"}})
            result = interface.route_to_vendor(
                "get_stock_data", "NVDA", "2026-06-09", "2026-06-10"
            )

        self.assertEqual(result, "yfinance-ok")
        self.assertEqual(calls, ["yfinance"])

    def test_stockstats_loader_uses_tushare_for_configured_a_share(self):
        calls = {}
        fake_tushare = types.SimpleNamespace()

        class FakePro:
            def daily(self, **kwargs):
                calls.update(kwargs)
                return pd.DataFrame(
                    {
                        "trade_date": ["20260609", "20260610"],
                        "open": [10.0, 10.2],
                        "high": [10.4, 10.5],
                        "low": [9.9, 10.1],
                        "close": [10.1, 10.3],
                        "vol": [1000, 1200],
                    }
                )

        fake_tushare.pro_api = lambda token=None: FakePro()
        set_config({"data_vendors": {"core_stock_apis": "tushare,akshare"}})

        with mock.patch.dict(sys.modules, {"tushare": fake_tushare}):
            data = stockstats_utils.load_ohlcv("600519.SH", "2026-06-10")

        self.assertEqual(calls["ts_code"], "600519.SH")
        self.assertEqual(list(data["Close"]), [10.1, 10.3])


if __name__ == "__main__":
    unittest.main()
