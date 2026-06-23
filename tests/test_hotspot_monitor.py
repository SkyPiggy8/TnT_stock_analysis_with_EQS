from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.hotspot_monitor.backtest import run_basic_backtest
from tradingagents.hotspot_monitor.config import load_hotspot_config
from tradingagents.hotspot_monitor.scoring import score_stocks
from tradingagents.hotspot_monitor.service import HotspotMonitor
from tradingagents.hotspot_monitor.sectors import score_sectors
from tradingagents.hotspot_monitor.signals import aggregate_block_trades, calculate_stock_signals
from tradingagents.hotspot_monitor.units import (
    normalize_block_trade,
    normalize_daily,
    normalize_daily_basic,
    normalize_moneyflow,
)
from tradingagents.hotspot_monitor.universe import filter_universe
from tradingagents.hotspot_monitor.store import HotspotStore


@pytest.mark.unit
def test_tushare_amount_units_are_centralized():
    daily = normalize_daily(pd.DataFrame({"amount": [123.0]}))
    money = normalize_moneyflow(pd.DataFrame({"net_mf_amount": [12.0]}))
    basic = normalize_daily_basic(pd.DataFrame({"circ_mv": [50.0], "total_mv": [80.0]}))
    block = normalize_block_trade(pd.DataFrame({"price": [10.0], "vol": [2.0], "amount": [20.0]}))
    assert daily.loc[0, "daily_amount_yuan"] == 123_000
    assert money.loc[0, "net_mf_amount_yuan"] == 120_000
    assert basic.loc[0, "circ_mv_yuan"] == 500_000
    assert basic.loc[0, "total_mv_yuan"] == 800_000
    assert block.loc[0, "block_vol_shares"] == 20_000
    assert block.loc[0, "block_amount_yuan"] == 200_000


@pytest.mark.unit
def test_block_trade_aggregation_uses_volume_weighted_price():
    daily = pd.DataFrame(
        {"ts_code": ["000001.SZ"], "trade_date": ["20260618"], "close": [10.0], "amount": [1000.0]}
    )
    block = pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "000001.SZ"],
            "trade_date": ["20260618", "20260618"],
            "price": [10.0, 12.0],
            "vol": [1.0, 3.0],
            "amount": [10.0, 36.0],
            "buyer": ["A", "B"],
            "seller": ["C", "D"],
        }
    )
    result = aggregate_block_trades(block, daily).iloc[0]
    assert result["block_trade_count"] == 2
    assert result["block_vwap_price"] == pytest.approx(11.5)
    assert result["block_vwap_premium"] == pytest.approx(0.15)
    assert result["block_total_amount_yuan"] == 460_000
    assert result["buyer_list"] == "A；B"


def _history_frames(periods: int = 70):
    dates = pd.bdate_range("2026-03-01", periods=periods)
    codes = ["000001.SZ"] * periods
    daily = pd.DataFrame(
        {
            "ts_code": codes,
            "trade_date": dates.strftime("%Y%m%d"),
            "open": [10.0] * periods,
            "high": [10.5] * periods,
            "low": [9.5] * periods,
            "close": [10.0 + index * 0.01 for index in range(periods)],
            "pct_chg": [0.1] * periods,
            "vol": [100_000.0] * periods,
            "amount": [100_000.0] * periods,
        }
    )
    basic = pd.DataFrame(
        {
            "ts_code": codes,
            "trade_date": dates.strftime("%Y%m%d"),
            "turnover_rate": [2.0] * periods,
            "volume_ratio": [1.0] * periods,
            "circ_mv": [500_000.0] * periods,
            "total_mv": [600_000.0] * periods,
        }
    )
    money = pd.DataFrame(
        {
            "ts_code": codes,
            "trade_date": dates.strftime("%Y%m%d"),
            "buy_lg_amount": [200.0] * periods,
            "sell_lg_amount": [100.0] * periods,
            "buy_elg_amount": [200.0] * periods,
            "sell_elg_amount": [100.0] * periods,
            "net_mf_amount": [80.0 + (index % 5) * 10.0 for index in range(periods - 1)] + [1000.0],
        }
    )
    return dates, daily, basic, money


@pytest.mark.unit
def test_rolling_moneyflow_signal_excludes_current_day_from_baseline():
    dates, daily, basic, money = _history_frames()
    config = load_hotspot_config()
    result = calculate_stock_signals(
        daily, basic, money, pd.DataFrame(), dates[-1].strftime("%Y%m%d"), config
    ).iloc[0]
    assert result["net_flow_ratio"] == pytest.approx(0.10)
    assert result["net_flow_zscore_60"] > 1.5
    assert bool(result["signal_moneyflow_net"])


@pytest.mark.unit
def test_universe_filters_st_bse_new_and_illiquid():
    config = load_hotspot_config()
    stocks = pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "000002.SZ", "830001.BJ", "000003.SZ"],
            "name": ["正常股份", "*ST测试", "北交测试", "新股"],
            "market": ["主板", "主板", "北交所", "主板"],
            "list_date": ["20000101", "20000101", "20000101", "20260601"],
            "industry": ["银行"] * 4,
        }
    )
    daily = pd.DataFrame(
        {"ts_code": stocks["ts_code"], "daily_amount_yuan": [80e6, 80e6, 80e6, 10e6]}
    )
    basic = pd.DataFrame(
        {"ts_code": stocks["ts_code"], "circ_mv_yuan": [5e9, 5e9, 5e9, 1e9]}
    )
    result, stats = filter_universe(stocks, daily, basic, "20260618", config)
    assert result["ts_code"].tolist() == ["000001.SZ"]
    assert stats["eligibleStocks"] == 1


@pytest.mark.unit
def test_balanced_score_is_clipped_and_does_not_require_block_trade():
    config = load_hotspot_config()
    _, daily, basic, money = _history_frames()
    stock = calculate_stock_signals(daily, basic, money, pd.DataFrame(), daily.iloc[-1]["trade_date"], config)
    stock["sector_level_1"] = "银行"
    sectors = score_sectors(stock, 0.05, 1.3)
    scored = score_stocks(stock, sectors, config).iloc[0]
    assert 0 <= scored["stock_score"] <= 100
    assert scored["block_trade_score"] == 0
    assert scored["stock_score"] > 0


@pytest.mark.unit
def test_backtest_enters_at_next_open_and_marks_limit_up():
    signals = pd.DataFrame(
        {
            "trade_date": ["20260615", "20260615"],
            "ts_code": ["000001.SZ", "300001.SZ"],
            "any_signal": [True, True],
            "sector_level_1": ["银行", "科技"],
            "stock_score": [80.0, 90.0],
        }
    )
    daily = pd.DataFrame(
        {
            "trade_date": ["20260615", "20260616", "20260617"] * 2,
            "ts_code": ["000001.SZ"] * 3 + ["300001.SZ"] * 3,
            "open": [10.0, 10.2, 10.5, 10.0, 12.0, 12.2],
            "close": [10.0, 10.4, 10.6, 10.0, 12.0, 12.3],
        }
    )
    trades, metrics = run_basic_backtest(signals, daily, [1, 2])
    normal = trades[trades["ts_code"] == "000001.SZ"].iloc[0]
    growth = trades[trades["ts_code"] == "300001.SZ"].iloc[0]
    assert normal["entry_price"] == 10.2
    assert normal["return_1d"] == pytest.approx(10.4 / 10.2 - 1)
    assert growth["warning"] == "LIMIT_UP_ENTRY"
    assert metrics.loc[metrics["holding_days"] == 1, "trigger_count"].iloc[0] == 1


@pytest.mark.unit
def test_backtest_marks_suspension_limit_down_and_group_metrics():
    signals = pd.DataFrame(
        {
            "trade_date": ["20260615", "20260615"],
            "ts_code": ["000001.SZ", "000002.SZ"],
            "any_signal": [True, True],
            "sector_level_1": ["银行", "银行"],
            "circ_mv_yuan": [4e9, 8e9],
        }
    )
    daily = pd.DataFrame(
        {
            "trade_date": [
                "20260615", "20260616", "20260617",
                "20260615", "20260617",
                "20260615", "20260616", "20260617",
            ],
            "ts_code": ["000001.SZ"] * 3 + ["000002.SZ"] * 2 + ["600000.SH"] * 3,
            "open": [10.0, 10.2, 9.3, 8.0, 8.1, 5.0, 5.0, 5.0],
            "close": [10.0, 10.4, 9.3, 8.0, 8.1, 5.0, 5.0, 5.0],
        }
    )
    trades, metrics = run_basic_backtest(signals, daily, [1, 2])

    liquid = trades[trades["ts_code"] == "000001.SZ"].iloc[0]
    suspended = trades[trades["ts_code"] == "000002.SZ"].iloc[0]
    assert liquid["exit_warning_2d"] == "LIMIT_DOWN_EXIT"
    assert suspended["entry_warning"] == "SUSPENDED_ENTRY"
    assert {"all", "sector", "market_cap"}.issubset(set(metrics["group_type"]))


@pytest.mark.unit
def test_daily_scan_is_batch_cached_and_idempotent(tmp_path):
    dates = pd.bdate_range("2026-05-01", periods=25).strftime("%Y%m%d").tolist()

    class FakeBatchClient:
        def __init__(self):
            self.calls = {name: 0 for name in ("daily", "daily_basic", "moneyflow", "block_trade")}

        def trade_calendar(self, start_date, end_date):
            selected = [date for date in dates if start_date <= date <= end_date]
            return pd.DataFrame({"cal_date": selected, "is_open": [1] * len(selected)})

        def stock_basic(self):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ", "000002.SZ"],
                    "symbol": ["000001", "000002"],
                    "name": ["热点一号", "普通二号"],
                    "area": ["深圳", "深圳"],
                    "industry": ["银行", "地产"],
                    "market": ["主板", "主板"],
                    "list_date": ["20000101", "20000101"],
                }
            )

        def sector_members(self):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ", "000002.SZ"],
                    "l1_name": ["银行", "房地产"],
                    "l2_name": ["股份制银行", "住宅开发"],
                }
            )

        def daily(self, trade_date):
            self.calls["daily"] += 1
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ", "000002.SZ"], "trade_date": [trade_date] * 2,
                    "open": [10.0, 8.0], "high": [10.5, 8.2], "low": [9.8, 7.8],
                    "close": [10.2, 8.0], "pct_chg": [2.0, 0.0], "vol": [100000, 100000],
                    "amount": [100000.0, 80000.0],
                }
            )

        def daily_basic(self, trade_date):
            self.calls["daily_basic"] += 1
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ", "000002.SZ"], "trade_date": [trade_date] * 2,
                    "turnover_rate": [2.0, 1.5], "volume_ratio": [1.5, 1.0],
                    "pe_ttm": [10.0, 12.0], "pb": [1.0, 1.1],
                    "total_mv": [600000.0, 400000.0], "circ_mv": [500000.0, 300000.0],
                }
            )

        def moneyflow(self, trade_date):
            self.calls["moneyflow"] += 1
            final = trade_date == dates[-1]
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ", "000002.SZ"], "trade_date": [trade_date] * 2,
                    "buy_lg_amount": [700.0 if final else 200.0, 100.0],
                    "sell_lg_amount": [100.0, 100.0],
                    "buy_elg_amount": [700.0 if final else 200.0, 100.0],
                    "sell_elg_amount": [100.0, 100.0],
                    "net_mf_amount": [1000.0 if final else 100.0, 0.0],
                }
            )

        def block_trade(self, trade_date):
            self.calls["block_trade"] += 1
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"], "trade_date": [trade_date], "price": [10.8],
                    "vol": [20.0], "amount": [216.0], "buyer": ["买方A"], "seller": ["卖方B"],
                }
            )

    config = load_hotspot_config()
    config["storage"].update({"data_dir": tmp_path / "data", "report_dir": tmp_path / "reports", "history_days": 20})
    config["signals"]["moneyflow"].update({"short_window": 5, "long_window": 10})
    config["signals"]["technical"].update({"ma_windows": [2, 3, 5], "volume_window": 5})
    fake = FakeBatchClient()
    monitor = HotspotMonitor(config, client=fake, store=HotspotStore(config))
    first = monitor.scan(dates[-1])
    calls_after_first = fake.calls.copy()
    second = monitor.scan(dates[-1])

    assert first["tradeDate"] == dates[-1]
    assert first["summary"]["eligibleStocks"] == 2
    assert first["stocks"][0]["ts_code"] == "000001.SZ"
    assert first["summary"]["reportPaths"]["markdown"]
    assert second["stocks"][0]["stock_score"] == first["stocks"][0]["stock_score"]
    assert fake.calls == calls_after_first
    assert fake.calls["daily"] == 20
    assert fake.calls["block_trade"] == 1


@pytest.mark.unit
def test_store_evolves_result_schema(tmp_path):
    config = load_hotspot_config()
    config["storage"].update(
        {"data_dir": tmp_path / "data", "report_dir": tmp_path / "reports"}
    )
    store = HotspotStore(config)
    store.save_frame("daily_signals", "20260618", pd.DataFrame({"score": [80.0]}))
    store.save_frame(
        "daily_signals",
        "20260618",
        pd.DataFrame({"score": [75.0], "risk_flags": ["NEAR_LIMIT_DOWN"]}),
    )

    saved = store.load_frame("daily_signals", "20260618")
    assert saved.loc[0, "risk_flags"] == "NEAR_LIMIT_DOWN"
    store.save_frame(
        "data_quality_flags",
        "20260618",
        pd.DataFrame(
            {"ts_code": ["000001.SZ"], "data_quality_flags": ["MISSING_MONEYFLOW"]}
        ),
    )
    quality = store.load_frame("data_quality_flags", "20260618")
    assert quality.loc[0, "data_quality_flags"] == "MISSING_MONEYFLOW"


@pytest.mark.unit
def test_empty_market_cache_is_refetched_but_empty_block_cache_is_valid(tmp_path):
    config = load_hotspot_config()
    config["storage"].update(
        {"data_dir": tmp_path / "data", "report_dir": tmp_path / "reports"}
    )
    store = HotspotStore(config)
    date = "20260622"
    for interface in ("daily", "daily_basic", "moneyflow", "block_trade"):
        store.write_raw(interface, date, pd.DataFrame())

    class Client:
        def __init__(self):
            self.calls = []

        def daily(self, trade_date):
            self.calls.append("daily")
            return pd.DataFrame({"ts_code": ["000001.SZ"], "trade_date": [trade_date]})

        def daily_basic(self, trade_date):
            self.calls.append("daily_basic")
            return pd.DataFrame({"ts_code": ["000001.SZ"], "trade_date": [trade_date]})

        def moneyflow(self, trade_date):
            self.calls.append("moneyflow")
            return pd.DataFrame({"ts_code": ["000001.SZ"], "trade_date": [trade_date]})

        def block_trade(self, trade_date):
            self.calls.append("block_trade")
            return pd.DataFrame()

    client = Client()
    monitor = HotspotMonitor(config, client=client, store=store)
    monitor._fetch_date(date, include_block=True)

    assert client.calls == ["daily", "daily_basic", "moneyflow"]
    assert len(store.read_raw("daily", date)) == 1


@pytest.mark.unit
def test_available_raw_dates_requires_all_market_inputs(tmp_path):
    config = load_hotspot_config()
    config["storage"].update(
        {"data_dir": tmp_path / "data", "report_dir": tmp_path / "reports"}
    )
    store = HotspotStore(config)
    complete = "20260618"
    partial = "20260617"
    for interface in ("daily", "daily_basic", "moneyflow"):
        store.write_raw(interface, complete, pd.DataFrame({"ts_code": ["000001.SZ"]}))
    store.write_raw("daily", partial, pd.DataFrame({"ts_code": ["000001.SZ"]}))

    assert store.available_raw_dates() == [complete]
