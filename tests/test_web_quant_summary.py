import pytest

from web.backend.server import _extract_quant_summary


@pytest.mark.unit
def test_dashboard_extracts_upgraded_entry_and_exit_prices():
    markdown = """
Signal: ACTIVE_HOLD_MONITOR
Reason: monitoring
- Suggested entry zone: 10.20 - 10.60
- Entry pricing basis: valuation plus ATR
- Latest close: 11.00 (2026-06-20)
- Day 0: 2026-06-10
- Day 0 close: 10.50
- Latest 3-day net inflow: -1200.00 万元
- Latest 3-day flow intensity: -1.20%
- Latest flow date: 2026-06-20
- Signal-window 3-day net inflow: 3500.00 万元
- Signal-window flow intensity: 3.50%
- Reference entry date: 2026-06-11
- Reference entry price: 10.55
- Take-profit level: 12.55
- Risk-exit level: 9.55
- Current exit trigger: 10.15
- Suggested exit price now: 10.15
- Completed non-overlapping trades: 6
- Win rate: 66.67%
- Average return after modeled costs: 3.10%
- Compounded return after modeled costs: 19.80%
- Buy-and-hold benchmark return: 10.00%
- Excess return vs benchmark: 9.80%
- Trade-sequence max drawdown: -5.20%
- Profit factor: 1.85
- Average holding days: 12.5
- Evidence grade: PROMISING_IN_SAMPLE

| Signal date | Entry date | Exit date | Entry | Exit | Net return | Holding days | Exit type |
|---|---|---|---:|---:|---:|---:|---|
| 2026-01-01 | 2026-01-02 | 2026-01-12 | 10.00 | 11.00 | 9.70% | 10 | SELL_TAKE_PROFIT |
"""

    summary = _extract_quant_summary(markdown)

    assert summary["signal"] == "ACTIVE_HOLD_MONITOR"
    assert summary["entryZone"] == "10.20 - 10.60"
    assert summary["entryPrice"] == "10.55"
    assert summary["currentExit"] == "10.15"
    assert summary["suggestedExit"] == "10.15"
    assert summary["netInflow"] == "3500.00 万元"
    assert summary["signalNetInflow"] == "3500.00 万元"
    assert summary["latestNetInflow"] == "-1200.00 万元"
    assert summary["latestInflowRatio"] == "-1.20%"
    assert summary["latestFlowDate"] == "2026-06-20"
    assert summary["completedTrades"] == "6"
    assert summary["evidenceGrade"] == "PROMISING_IN_SAMPLE"
    assert summary["excessReturn"] == "9.80%"
    assert summary["backtestTrades"][0]["status"] == "SELL_TAKE_PROFIT"


@pytest.mark.unit
def test_dashboard_derives_latest_three_day_flow_for_legacy_reports():
    markdown = """
Signal: REDUCE_OR_EXIT
- 3-day net inflow: 1200.00 万元
- Net inflow / matched turnover: 4.00%

| Date | Close | Net inflow (万元) | Prev avg turnover (万元) | Flow intensity | Turnover expansion | Signal |
|---|---:|---:|---:|---:|---:|---|
| 2026-06-16 | 4.94 | -100.00 | 1000.00 | -1.00% | 1.00x | |
| 2026-06-17 | 4.83 | -200.00 | 1000.00 | -2.00% | 1.00x | |
| 2026-06-18 | 4.48 | -300.00 | 1000.00 | -3.00% | 1.00x | |
"""

    summary = _extract_quant_summary(markdown)

    assert summary["signalNetInflow"] == "1200.00 万元"
    assert summary["latestNetInflow"] == "-600.00 万元"
    assert summary["latestInflowRatio"] == "-20.00%"
    assert summary["latestFlowDate"] == "2026-06-18"
