from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

try:
    from tradingagents.dataflows.akshare_data import _akshare_proxy_env
except Exception:  # pragma: no cover - keeps the module usable before package setup.
    from contextlib import nullcontext as _akshare_proxy_env  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BOARD_PATH = ROOT / "web" / "backend" / "personal_board.json"
DEFAULT_STATE_PATH = ROOT / "web" / "backend" / "personal_alert_state.json"
EXIT_SIGNALS = {"REDUCE_OR_EXIT", "SELL_TAKE_PROFIT", "EXPIRED"}
CN = ZoneInfo("Asia/Shanghai")


class PersonalAlertError(RuntimeError):
    pass


@dataclass(frozen=True)
class Quote:
    ticker: str
    code: str
    name: str
    price: float
    pct_change: float | None = None
    source: str = "akshare.stock_zh_a_spot_em"
    timestamp: str = ""


@dataclass(frozen=True)
class Alert:
    key: str
    ticker: str
    name: str
    code: str
    level: str
    price: float | None
    threshold: float | None
    message: str


def load_dotenv(path: Path | None = None) -> None:
    env_path = path or (ROOT / ".env")
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def ticker_code(value: str) -> str:
    match = re.search(r"\d{6}", str(value or ""))
    if not match:
        raise PersonalAlertError(f"invalid A-share ticker: {value!r}")
    return match.group(0)


def normalize_ticker(value: str) -> str:
    code = ticker_code(value)
    raw = str(value or "").upper()
    if raw.endswith(".SH") or raw.endswith("SH"):
        return f"{code}.SH"
    if raw.endswith(".BJ") or raw.endswith("BJ"):
        return f"{code}.BJ"
    return f"{code}.SZ"


def number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
        return float(match.group(0)) if match else None


def load_board(path: Path = DEFAULT_BOARD_PATH) -> dict[str, Any]:
    if not path.exists():
        raise PersonalAlertError(f"personal board not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PersonalAlertError(f"personal board must be a JSON object: {path}")
    return payload


def load_state(path: Path = DEFAULT_STATE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"active": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {"active": {}}


def save_state(state: dict[str, Any], path: Path = DEFAULT_STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _row_value(row: Any, *columns: str) -> Any:
    for column in columns:
        if column in row and row[column] not in (None, ""):
            return row[column]
    return None


def load_akshare_quotes() -> dict[str, Quote]:
    try:
        import akshare as ak
    except ImportError as exc:
        raise PersonalAlertError("akshare is not installed; run `pip install akshare`.") from exc

    try:
        with _akshare_proxy_env():
            frame = ak.stock_zh_a_spot_em()
    except Exception as exc:
        raise PersonalAlertError(f"akshare stock_zh_a_spot_em failed: {exc}") from exc

    if frame is None or frame.empty:
        raise PersonalAlertError("akshare stock_zh_a_spot_em returned no rows")

    quotes: dict[str, Quote] = {}
    timestamp = datetime.now(CN).isoformat(timespec="seconds")
    for _, row in frame.iterrows():
        code = str(_row_value(row, "\u4ee3\u7801", "code", "symbol") or "").strip()
        if not re.fullmatch(r"\d{6}", code):
            continue
        price = number(_row_value(row, "\u6700\u65b0\u4ef7", "latest", "price", "close"))
        if price is None or price <= 0:
            continue
        quote = Quote(
            ticker=normalize_ticker(code),
            code=code,
            name=str(_row_value(row, "\u540d\u79f0", "name") or code),
            price=price,
            pct_change=number(_row_value(row, "\u6da8\u8dcc\u5e45", "pct_change")),
            timestamp=timestamp,
        )
        quotes[code] = quote
    return quotes


def evaluate_holding(holding: dict[str, Any], quote: Quote | None) -> list[Alert]:
    ticker = normalize_ticker(str(holding.get("ticker") or holding.get("name") or ""))
    code = ticker_code(ticker)
    name = str(holding.get("name") or quote.name if quote else holding.get("name") or ticker)
    alerts: list[Alert] = []
    take_profit = number(holding.get("takeProfit"))
    stop_loss = number(holding.get("stopLoss"))
    signal = str((holding.get("monitor") or {}).get("signal") or "").upper()

    if quote is None:
        alerts.append(
            Alert(
                key=f"{ticker}:NO_QUOTE",
                ticker=ticker,
                name=name,
                code="NO_QUOTE",
                level="warn",
                price=None,
                threshold=None,
                message=f"{ticker} has no realtime quote from AKShare.",
            )
        )
        return alerts

    if take_profit is not None and quote.price >= take_profit:
        alerts.append(
            Alert(
                key=f"{ticker}:TAKE_PROFIT:{take_profit:.3f}",
                ticker=ticker,
                name=name,
                code="TAKE_PROFIT",
                level="success",
                price=quote.price,
                threshold=take_profit,
                message=f"{ticker} {name} reached take-profit line {take_profit:.2f}; latest {quote.price:.2f}.",
            )
        )
    if stop_loss is not None and quote.price <= stop_loss:
        alerts.append(
            Alert(
                key=f"{ticker}:STOP_LOSS:{stop_loss:.3f}",
                ticker=ticker,
                name=name,
                code="STOP_LOSS",
                level="danger",
                price=quote.price,
                threshold=stop_loss,
                message=f"{ticker} {name} reached stop-loss line {stop_loss:.2f}; latest {quote.price:.2f}.",
            )
        )
    if signal in EXIT_SIGNALS:
        alerts.append(
            Alert(
                key=f"{ticker}:QUANT_SIGNAL:{signal}",
                ticker=ticker,
                name=name,
                code=signal,
                level="danger",
                price=quote.price,
                threshold=None,
                message=f"{ticker} {name} has exit-oriented quant signal {signal}; latest {quote.price:.2f}.",
            )
        )
    return alerts


def filter_new_alerts(alerts: list[Alert], state: dict[str, Any], repeat: bool = False) -> list[Alert]:
    if repeat:
        return alerts
    active = state.setdefault("active", {})
    current_keys = {alert.key for alert in alerts}
    new_alerts = [alert for alert in alerts if alert.key not in active]
    for key in list(active):
        if key not in current_keys:
            active.pop(key, None)
    for alert in alerts:
        active[alert.key] = {
            "ticker": alert.ticker,
            "code": alert.code,
            "firstSeenAt": active.get(alert.key, {}).get("firstSeenAt") or datetime.now(CN).isoformat(timespec="seconds"),
            "lastSeenAt": datetime.now(CN).isoformat(timespec="seconds"),
            "price": alert.price,
            "threshold": alert.threshold,
        }
    return new_alerts


def build_alerts(board: dict[str, Any], quotes: dict[str, Quote]) -> list[Alert]:
    alerts: list[Alert] = []
    for holding in board.get("holdings", []):
        if not isinstance(holding, dict):
            continue
        try:
            code = ticker_code(str(holding.get("ticker") or holding.get("name") or ""))
        except PersonalAlertError:
            continue
        alerts.extend(evaluate_holding(holding, quotes.get(code)))
    return alerts


def market_is_open(now: datetime | None = None) -> bool:
    current = now.astimezone(CN) if now else datetime.now(CN)
    if current.weekday() >= 5:
        return False
    t = current.time()
    return time(9, 25) <= t <= time(11, 35) or time(12, 55) <= t <= time(15, 5)


def render_message(alerts: list[Alert]) -> tuple[str, str]:
    title = f"TradingAgents price alert: {len(alerts)} triggered"
    lines = [title, "", f"Time: {datetime.now(CN).strftime('%Y-%m-%d %H:%M:%S')}"]
    for alert in alerts:
        price = "-" if alert.price is None else f"{alert.price:.2f}"
        threshold = "-" if alert.threshold is None else f"{alert.threshold:.2f}"
        lines.append(f"- [{alert.code}] {alert.ticker} {alert.name}: price={price}, threshold={threshold}")
        lines.append(f"  {alert.message}")
    return title, "\n".join(lines)


def send_webhook(title: str, content: str, url: str, webhook_type: str = "generic", timeout: int = 10) -> requests.Response:
    webhook_type = webhook_type.lower().strip()
    if webhook_type == "serverchan":
        response = requests.post(url, data={"title": title, "desp": content}, timeout=timeout)
    elif webhook_type == "wecom":
        response = requests.post(
            url,
            json={"msgtype": "markdown", "markdown": {"content": content}},
            timeout=timeout,
        )
    else:
        response = requests.post(
            url,
            json={"title": title, "text": title, "content": content, "desp": content},
            timeout=timeout,
        )
    response.raise_for_status()
    return response

