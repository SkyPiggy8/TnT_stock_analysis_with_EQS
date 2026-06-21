import os
import sys
import types
import unittest
from unittest import mock

import pandas as pd
import pytest

from tradingagents.dataflows.a_share_quant_strategy import build_quant_strategy_report


def _market_frames(periods: int = 50):
    dates = pd.bdate_range("2026-01-05", periods=periods)
    closes = [10.0 + index * 0.05 for index in range(periods)]
    daily = pd.DataFrame(
        {
            "ts_code": ["000001.SZ"] * periods,
            "trade_date": [date.strftime("%Y%m%d") for date in dates],
            "open": closes,
            "high": [price + 0.35 for price in closes],
            "low": [price - 0.35 for price in closes],
            "close": closes,
            "vol": [100_000] * periods,
            # Tushare daily amount is thousand CNY; this becomes 100,000 万元.
            "amount": [1_000_000.0] * periods,
        }
    )
    moneyflow = pd.DataFrame(
        {
            "ts_code": ["000001.SZ"] * periods,
            "trade_date": [date.strftime("%Y%m%d") for date in dates],
            "buy_lg_amount": [0.0] * periods,
            "sell_lg_amount": [0.0] * periods,
            "buy_elg_amount": [0.0] * periods,
            "sell_elg_amount": [0.0] * periods,
            "net_mf_amount": [0.0] * periods,
        }
    )
    return dates, daily, moneyflow


def _trigger(moneyflow: pd.DataFrame, end_index: int):
    # 10,500 万元 over three days / (100,000 万元 * 3) = 3.5%.
    for index in range(end_index - 2, end_index + 1):
        moneyflow.loc[index, "net_mf_amount"] = 3_500.0


class FakePro:
    def __init__(self, daily, moneyflow, valuation=None, factors=None):
        self._daily = daily
        self._moneyflow = moneyflow
        self._valuation = valuation if valuation is not None else pd.DataFrame()
        self._factors = factors if factors is not None else pd.DataFrame()

    def daily(self, **kwargs):
        return self._daily

    def moneyflow(self, **kwargs):
        return self._moneyflow

    def daily_basic(self, **kwargs):
        return self._valuation

    def adj_factor(self, **kwargs):
        return self._factors


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

    def _report(self, daily, moneyflow, date, valuation=None, final_state=None):
        pro = FakePro(daily, moneyflow, valuation=valuation)
        fake_tushare = types.SimpleNamespace(pro_api=lambda token=None: pro)
        with mock.patch.dict(sys.modules, {"tushare": fake_tushare}):
            return build_quant_strategy_report(
                "000001.SZ",
                date.strftime("%Y-%m-%d"),
                final_state=final_state,
            )

    def test_signal_uses_multi_day_flow_and_enters_on_next_trading_day(self):
        dates, daily, moneyflow = _market_frames()
        _trigger(moneyflow, 32)

        report = self._report(daily, moneyflow, dates[-1])

        self.assertIn("Signal: ACTIVE_HOLD_MONITOR", report)
        self.assertIn(f"- Day 0: {dates[32].strftime('%Y-%m-%d')}", report)
        self.assertIn(f"- Reference entry date: {dates[33].strftime('%Y-%m-%d')}", report)
        self.assertIn("- Net inflow / matched turnover: 3.50%", report)
        self.assertNotIn("Reference entry price: 11.60\n", report)
        self.assertIn("Day 0 close is never treated as an executable fill", report)
        self.assertIn("- Example position limit:", report)
        self.assertIn("## Lookback Backtest Snapshot", report)

    def test_historical_stop_remains_exit_after_later_price_recovery(self):
        dates, daily, moneyflow = _market_frames()
        _trigger(moneyflow, 32)
        daily.loc[35, "low"] = 5.0
        daily.loc[35, "close"] = 11.75

        report = self._report(daily, moneyflow, dates[-1])

        self.assertIn("Signal: REDUCE_OR_EXIT", report)
        self.assertIn(f"- Exit event date: {dates[35].strftime('%Y-%m-%d')}", report)
        self.assertIn("- Suggested exit price now:", report)

    def test_latest_day_signal_waits_for_t_plus_one_execution(self):
        dates, daily, moneyflow = _market_frames()
        _trigger(moneyflow, len(dates) - 1)

        report = self._report(daily, moneyflow, dates[-1])

        self.assertIn("Signal: PENDING_ENTRY", report)
        self.assertIn("- Reference entry price: PENDING_NEXT_TRADING_DAY", report)

    def test_relative_valuation_constrains_suggested_entry_zone(self):
        dates, daily, moneyflow = _market_frames()
        _trigger(moneyflow, 32)
        valuation_dates = pd.bdate_range("2025-07-01", periods=120)
        valuation = pd.DataFrame(
            {
                "ts_code": ["000001.SZ"] * 120,
                "trade_date": [date.strftime("%Y%m%d") for date in valuation_dates],
                "close": [12.0] * 120,
                "pe_ttm": [10.0] * 119 + [20.0],
                "pb": [2.0] * 120,
            }
        )

        report = self._report(daily, moneyflow, dates[-1], valuation=valuation)

        self.assertIn("## Fundamental Relative Valuation", report)
        self.assertIn("Fundamental entry ceiling after 10% safety margin", report)
        self.assertIn("PE(TTM) 20.00 vs history median 10.00", report)
        self.assertIn("- Suggested entry zone:", report)

    def test_material_change_pauses_new_entry(self):
        dates, daily, moneyflow = _market_frames()
        _trigger(moneyflow, len(dates) - 1)
        final_state = {"fundamentals_report": "公司被监管立案，基本面恶化。"}

        report = self._report(daily, moneyflow, dates[-1], final_state=final_state)

        self.assertIn("Signal: FUNDAMENTAL_REVIEW_REQUIRED", report)
        self.assertIn("暂停新增入场", report)


if __name__ == "__main__":
    unittest.main()
