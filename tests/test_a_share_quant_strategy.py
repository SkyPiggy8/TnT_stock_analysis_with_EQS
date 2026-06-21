import os
import sys
import types
import unittest
from unittest import mock

import pandas as pd
import pytest

from tradingagents.dataflows.a_share_quant_strategy import build_quant_strategy_report


@pytest.mark.unit
class TestAShareQuantStrategy(unittest.TestCase):
    def setUp(self):
        self._old_token = os.environ.get("TUSHARE_TOKEN")
        os.environ["TUSHARE_TOKEN"] = "test-token"

    def tearDown(self):
        if self._old_token is None:
            os.environ.pop("TUSHARE_TOKEN", None)
        else:
            os.environ["TUSHARE_TOKEN"] = self._old_token

    def test_moneyflow_trigger_uses_five_percent_of_prev_10_day_turnover(self):
        dates = pd.bdate_range("2026-05-01", periods=22)
        trade_dates = [d.strftime("%Y%m%d") for d in dates]

        daily = pd.DataFrame(
            {
                "ts_code": ["000001.SZ"] * len(dates),
                "trade_date": trade_dates,
                "open": [10.0] * len(dates),
                "high": [10.5] * len(dates),
                "low": [9.8] * len(dates),
                "close": [10.0 + i * 0.05 for i in range(len(dates))],
                "vol": [100000] * len(dates),
                # Tushare daily amount is thousand CNY; 1,000,000 = 1bn CNY.
                "amount": [1_000_000.0] * len(dates),
            }
        )
        moneyflow = pd.DataFrame(
            {
                "ts_code": ["000001.SZ"] * len(dates),
                "trade_date": trade_dates,
                "buy_lg_amount": [0.0] * len(dates),
                "sell_lg_amount": [0.0] * len(dates),
                "buy_elg_amount": [0.0] * len(dates),
                "sell_elg_amount": [0.0] * len(dates),
                "net_mf_amount": [0.0] * len(dates),
            }
        )
        # 5,000 ten-thousand CNY = 50m CNY, exactly 5% of 1bn CNY.
        moneyflow.loc[10, "net_mf_amount"] = 5_000.0

        class FakePro:
            def daily(self, **kwargs):
                return daily

            def moneyflow(self, **kwargs):
                return moneyflow

        fake_tushare = types.SimpleNamespace(pro_api=lambda token=None: FakePro())

        with mock.patch.dict(sys.modules, {"tushare": fake_tushare}):
            report = build_quant_strategy_report("000001.SZ", dates[-1].strftime("%Y-%m-%d"))

        self.assertIn("Signal: ACTIVE_BUY_OR_HOLD", report)
        self.assertIn("Net inflow / previous 10-day average turnover: 5.00%", report)
        self.assertIn("Take-profit level", report)
        self.assertIn("Risk-exit level", report)


if __name__ == "__main__":
    unittest.main()
