from __future__ import annotations

from tradingagents.personal_alerts import (
    Alert,
    Quote,
    build_alerts,
    filter_new_alerts,
    normalize_ticker,
    render_message,
    ticker_code,
)


def test_ticker_normalization_accepts_common_a_share_forms():
    assert ticker_code("000725SZ") == "000725"
    assert normalize_ticker("600519SH") == "600519.SH"
    assert normalize_ticker("000966.SZ") == "000966.SZ"


def test_build_alerts_triggers_take_profit_and_stop_loss():
    board = {
        "holdings": [
            {"ticker": "000966.SZ", "name": "CY Power", "takeProfit": 4.8, "stopLoss": 3.9},
            {"ticker": "000725SZ", "name": "BOE A", "takeProfit": 8.6, "stopLoss": 7.5},
        ]
    }
    quotes = {
        "000966": Quote(ticker="000966.SZ", code="000966", name="CY Power", price=4.81),
        "000725": Quote(ticker="000725.SZ", code="000725", name="BOE A", price=7.49),
    }

    alerts = build_alerts(board, quotes)

    assert [alert.code for alert in alerts] == ["TAKE_PROFIT", "STOP_LOSS"]
    assert alerts[0].ticker == "000966.SZ"
    assert alerts[1].ticker == "000725.SZ"


def test_quant_exit_signal_is_opt_in_for_personal_alerts():
    board = {
        "holdings": [
            {
                "ticker": "000966.SZ",
                "name": "CY Power",
                "takeProfit": 4.8,
                "stopLoss": 3.9,
                "monitor": {"signal": "REDUCE_OR_EXIT"},
            }
        ]
    }
    quotes = {
        "000966": Quote(ticker="000966.SZ", code="000966", name="CY Power", price=3.96),
    }

    assert build_alerts(board, quotes) == []
    alerts = build_alerts(board, quotes, include_quant_signals=True)
    assert [alert.code for alert in alerts] == ["REDUCE_OR_EXIT"]


def test_filter_new_alerts_suppresses_repeated_active_alerts():
    alert = Alert(
        key="000966.SZ:TAKE_PROFIT:4.800",
        ticker="000966.SZ",
        name="CY Power",
        code="TAKE_PROFIT",
        level="success",
        price=4.81,
        threshold=4.8,
        message="hit",
    )
    state = {"active": {}}

    assert filter_new_alerts([alert], state) == [alert]
    assert filter_new_alerts([alert], state) == []
    assert filter_new_alerts([alert], state, repeat=True) == [alert]


def test_render_message_contains_actionable_price_context():
    alert = Alert(
        key="000966.SZ:STOP_LOSS:3.900",
        ticker="000966.SZ",
        name="CY Power",
        code="STOP_LOSS",
        level="danger",
        price=3.89,
        threshold=3.9,
        message="hit",
    )

    title, content = render_message([alert])

    assert "1 triggered" in title
    assert "000966.SZ" in content
    assert "price=3.89" in content
    assert "threshold=3.90" in content
