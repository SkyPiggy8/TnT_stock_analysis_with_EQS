from __future__ import annotations

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
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.tushare_fundamentals import (
    build_fundamental_snapshot,
    get_income_statement,
)


def _financial_frame(**columns):
    return pd.DataFrame(columns)


class FakeFundamentalPro:
    def income(self, **kwargs):
        return _financial_frame(
            ts_code=["000966.SZ"] * 4,
            ann_date=["20260430", "20260420", "20251030", "20270430"],
            f_ann_date=["20260430", "20260420", "20251030", "20270430"],
            end_date=["20260331", "20260331", "20250930", "20270331"],
            report_type=["1"] * 4,
            total_revenue=[100.0, 90.0, 80.0, 999.0],
            revenue=[100.0, 90.0, 80.0, 999.0],
            operate_profit=[12.0, 11.0, 9.0, 99.0],
            total_profit=[11.0, 10.0, 8.0, 99.0],
            n_income=[8.0, 7.0, 6.0, 99.0],
            n_income_attr_p=[8.0, 7.0, 6.0, 99.0],
            basic_eps=[0.2, 0.18, 0.15, 1.0],
        )

    def balancesheet(self, **kwargs):
        return _financial_frame(
            ts_code=["000966.SZ", "000966.SZ"],
            ann_date=["20260430", "20251030"],
            f_ann_date=["20260430", "20251030"],
            end_date=["20260331", "20250930"],
            report_type=["1", "1"],
            money_cap=[30.0, 28.0],
            total_assets=[200.0, 190.0],
            total_liab=[120.0, 118.0],
            total_hldr_eqy_exc_min_int=[80.0, 72.0],
        )

    def cashflow(self, **kwargs):
        return _financial_frame(
            ts_code=["000966.SZ", "000966.SZ"],
            ann_date=["20260430", "20251030"],
            f_ann_date=["20260430", "20251030"],
            end_date=["20260331", "20250930"],
            report_type=["1", "1"],
            net_profit=[8.0, 6.0],
            n_cashflow_act=[10.0, 5.0],
            n_cashflow_inv_act=[-4.0, -3.0],
            n_cash_flows_fnc_act=[-2.0, 1.0],
        )

    def fina_indicator(self, **kwargs):
        return _financial_frame(
            ts_code=["000966.SZ", "000966.SZ"],
            ann_date=["20260430", "20251030"],
            end_date=["20260331", "20250930"],
            roe=[8.5, 7.2],
            grossprofit_margin=[22.0, 20.0],
            netprofit_margin=[8.0, 7.5],
            debt_to_assets=[60.0, 62.1],
            current_ratio=[1.2, 1.1],
            tr_yoy=[12.5, 8.0],
            netprofit_yoy=[20.0, 10.0],
        )

    def daily_basic(self, **kwargs):
        return _financial_frame(
            ts_code=["000966.SZ", "000966.SZ"],
            trade_date=["20260618", "20260617"],
            close=[4.48, 4.95],
            pe_ttm=[10.5, 11.0],
            pb=[1.2, 1.3],
            dv_ttm=[3.1, 3.0],
            total_mv=[1200000.0, 1300000.0],
        )

    def stock_basic(self, **kwargs):
        return _financial_frame(
            ts_code=["000966.SZ"],
            name=["长源电力"],
            area=["湖北"],
            industry=["火力发电"],
            market=["主板"],
            list_date=["20000316"],
        )


@pytest.mark.unit
class TestTushareFundamentals(unittest.TestCase):
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

    def fake_tushare(self):
        return types.SimpleNamespace(pro_api=lambda token=None: FakeFundamentalPro())

    def test_income_uses_latest_visible_revision_and_excludes_future_rows(self):
        with mock.patch.dict(sys.modules, {"tushare": self.fake_tushare()}):
            report = get_income_statement("000966.SZ", "quarterly", "2026-06-21")

        self.assertIn("2026-03-31,2026-04-30,100.0", report)
        self.assertNotIn("2027-03-31", report)
        self.assertNotIn(",90.0,", report)

    def test_snapshot_contains_visualization_metrics_and_trends(self):
        with mock.patch.dict(sys.modules, {"tushare": self.fake_tushare()}):
            snapshot = build_fundamental_snapshot("000966.SZ", "2026-06-21")

        self.assertEqual(snapshot["company"]["name"], "长源电力")
        self.assertEqual(snapshot["latestPeriod"], "2026-03-31")
        self.assertEqual(snapshot["metrics"]["revenue"], 100.0)
        self.assertEqual(snapshot["metrics"]["netProfit"], 8.0)
        self.assertEqual(snapshot["metrics"]["roe"], 8.5)
        self.assertEqual(snapshot["metrics"]["peTtm"], 10.5)
        self.assertEqual(snapshot["metrics"]["operatingCashFlow"], 10.0)
        self.assertEqual(len(snapshot["trends"]), 2)
        self.assertTrue(snapshot["summary"])

    def test_a_share_fundamentals_prefer_tushare(self):
        calls = []

        with mock.patch.dict(
            interface.VENDOR_METHODS,
            {
                "get_fundamentals": {
                    "tushare": lambda *args: calls.append("tushare") or "tushare-ok",
                    "yfinance": lambda *args: calls.append("yfinance") or "yfinance-ok",
                }
            },
            clear=False,
        ):
            set_config({"data_vendors": {"fundamental_data": "yfinance,tushare"}})
            result = interface.route_to_vendor("get_fundamentals", "000966.SZ", "2026-06-21")

        self.assertEqual(result, "tushare-ok")
        self.assertEqual(calls, ["tushare"])

    def test_non_a_share_fundamentals_keep_yfinance_first(self):
        calls = []

        with mock.patch.dict(
            interface.VENDOR_METHODS,
            {
                "get_fundamentals": {
                    "tushare": lambda *args: calls.append("tushare") or "tushare-ok",
                    "yfinance": lambda *args: calls.append("yfinance") or "yfinance-ok",
                }
            },
            clear=False,
        ):
            set_config({"data_vendors": {"fundamental_data": "tushare,yfinance"}})
            result = interface.route_to_vendor("get_fundamentals", "NVDA", "2026-06-21")

        self.assertEqual(result, "yfinance-ok")
        self.assertEqual(calls, ["yfinance"])


if __name__ == "__main__":
    unittest.main()
