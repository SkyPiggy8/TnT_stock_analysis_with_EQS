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
- 3-day net inflow: 3500.00 万元
- Net inflow / matched turnover: 3.50%
- Reference entry date: 2026-06-11
- Reference entry price: 10.55
- Take-profit level: 12.55
- Risk-exit level: 9.55
- Current exit trigger: 10.15
- Suggested exit price now: 10.15
"""

    summary = _extract_quant_summary(markdown)

    assert summary["signal"] == "ACTIVE_HOLD_MONITOR"
    assert summary["entryZone"] == "10.20 - 10.60"
    assert summary["entryPrice"] == "10.55"
    assert summary["currentExit"] == "10.15"
    assert summary["suggestedExit"] == "10.15"
    assert summary["netInflow"] == "3500.00 万元"
