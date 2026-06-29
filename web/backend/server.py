from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = ROOT / "web" / "frontend"
FRONTEND_DIST_DIR = FRONTEND_DIR / "dist"
REPORTS_DIR = ROOT / "reports"
PERSONAL_BOARD_PATH = ROOT / "web" / "backend" / "personal_board.json"
PERSONAL_BOARD_MAX_ITEMS = 200

FUTURE_THEME_KEYWORDS = [
    "energy",
    "power",
    "battery",
    "semiconductor",
    "chip",
    "optical",
    "robot",
    "auto",
    "ev",
    "smart",
    "home",
    "satellite",
    "rocket",
    "aerospace",
    "新能源",
    "电力",
    "储能",
    "半导体",
    "芯片",
    "光模块",
    "机器人",
    "汽车",
    "智能",
    "家居",
    "低空",
    "卫星",
    "火箭",
    "航天",
    "军工",
]
EXCLUDED_THEME_KEYWORDS = [
    "房地产",
    "地产",
    "白酒",
    "消费",
    "医药",
    "医疗",
    "st",
]

DEFAULT_PERSONAL_BOARD = {
    "holdings": [],
    "watchlist": [],
    "rules": {
        "focus": FUTURE_THEME_KEYWORDS,
        "avoid": EXCLUDED_THEME_KEYWORDS,
        "minCircMvYuan": 2_000_000_000,
        "notes": [
            "Prefer sector-level value investing with visible future demand.",
            "Avoid unfamiliar fields, policy/geopolitical shock exposure, hype stocks, and small caps.",
            "Use hotspot radar only to narrow research scope; single-stock reports still decide entries and exits.",
        ],
    },
    "notification": {
        "mode": "local_only",
        "remoteName": "小龙虾",
        "enabled": False,
    },
}

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tradingagents.dataflows.a_share_quant_strategy import build_quant_strategy_report  # noqa: E402
from tradingagents.dataflows.tushare_fundamentals import build_fundamental_snapshot  # noqa: E402
from tradingagents.hotspot_monitor import HotspotMonitor, load_hotspot_config  # noqa: E402
from web.backend.hotspot_export import render_hotspot_export  # noqa: E402


_FUNDAMENTAL_CACHE: dict[tuple[str, str], tuple[float, dict]] = {}
_FUNDAMENTAL_CACHE_TTL_SECONDS = 300
_HOTSPOT_MONITOR: HotspotMonitor | None = None
_HOTSPOT_MONITOR_LOCK = threading.Lock()
_HOTSPOT_JOBS: dict[str, dict] = {}
_HOTSPOT_JOBS_LOCK = threading.Lock()


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        os.environ.setdefault(key, value)


def _get_hotspot_monitor() -> HotspotMonitor:
    global _HOTSPOT_MONITOR
    if _HOTSPOT_MONITOR is None:
        with _HOTSPOT_MONITOR_LOCK:
            if _HOTSPOT_MONITOR is None:
                _HOTSPOT_MONITOR = HotspotMonitor(load_hotspot_config())
    return _HOTSPOT_MONITOR


def _hotspot_job_snapshot(job_id: str) -> dict:
    with _HOTSPOT_JOBS_LOCK:
        if job_id not in _HOTSPOT_JOBS:
            raise FileNotFoundError(job_id)
        return dict(_HOTSPOT_JOBS[job_id])


def _start_hotspot_job(trade_date: str | None, *, refresh_target: bool = True) -> dict:
    job_id = uuid.uuid4().hex
    job = {
        "jobId": job_id,
        "status": "queued",
        "tradeDate": trade_date or "latest",
        "stage": "queued",
        "current": 0,
        "total": 0,
        "progress": 0,
        "message": "等待开始",
        "startedAt": datetime.now().isoformat(timespec="seconds"),
        "finishedAt": None,
        "error": None,
    }
    with _HOTSPOT_JOBS_LOCK:
        active = next(
            (
                dict(item)
                for item in _HOTSPOT_JOBS.values()
                if item["status"] in {"queued", "running"}
            ),
            None,
        )
        if active:
            return {**active, "alreadyRunning": True}
        _HOTSPOT_JOBS[job_id] = job

    def run() -> None:
        def progress(stage: str, current: int, total: int, message: str) -> None:
            with _HOTSPOT_JOBS_LOCK:
                item = _HOTSPOT_JOBS[job_id]
                item.update(
                    status="running",
                    stage=stage,
                    current=current,
                    total=total,
                    progress=round(current / total * 100, 1) if total else 0,
                    message=message,
                )

        try:
            result = _get_hotspot_monitor().scan(
                trade_date,
                refresh_target=refresh_target,
                progress=progress,
            )
            with _HOTSPOT_JOBS_LOCK:
                _HOTSPOT_JOBS[job_id].update(
                    status="complete",
                    stage="complete",
                    progress=100,
                    message="扫描完成",
                    tradeDate=result["tradeDate"],
                    finishedAt=datetime.now().isoformat(timespec="seconds"),
                )
        except Exception as exc:  # noqa: BLE001 - background job boundary
            with _HOTSPOT_JOBS_LOCK:
                _HOTSPOT_JOBS[job_id].update(
                    status="failed",
                    stage="failed",
                    message="扫描失败",
                    error=f"{type(exc).__name__}: {exc}",
                    finishedAt=datetime.now().isoformat(timespec="seconds"),
                )

    threading.Thread(target=run, name=f"hotspot-{job_id[:8]}", daemon=True).start()
    return dict(job)


def _json_response(handler: BaseHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _html_download_response(
    handler: BaseHTTPRequestHandler,
    html: str,
    filename: str,
) -> None:
    body = html.encode("utf-8")
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Disposition", f'attachment; filename="{filename}"')
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json_body(handler: BaseHTTPRequestHandler, max_bytes: int = 65_536) -> dict:
    length = int(handler.headers.get("Content-Length", "0") or 0)
    if length > max_bytes:
        raise ValueError("request body too large")
    if length == 0:
        return {}
    payload = json.loads(handler.rfile.read(length).decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object")
    return payload


def _clone_default_board() -> dict:
    return json.loads(json.dumps(DEFAULT_PERSONAL_BOARD, ensure_ascii=False))


def _ticker_key(value: str | None) -> str:
    return re.sub(r"[^0-9A-Za-z.]", "", str(value or "").upper())


def _number(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
        return float(match.group(0)) if match else None


def _board_item(raw: object, allowed: set[str]) -> dict:
    if not isinstance(raw, dict):
        return {}
    item = {key: raw.get(key) for key in allowed if raw.get(key) not in (None, "")}
    item["id"] = str(item.get("id") or uuid.uuid4().hex[:12])
    if "ticker" in item:
        item["ticker"] = _ticker_key(str(item["ticker"]))
    for key in ("shares", "costPrice", "takeProfit", "stopLoss", "targetPrice"):
        if key in item:
            parsed = _number(item.get(key))
            if parsed is None:
                item.pop(key, None)
            else:
                item[key] = parsed
    return item


def _clean_personal_board(payload: dict) -> dict:
    board = _clone_default_board()
    holding_fields = {
        "id",
        "ticker",
        "name",
        "shares",
        "costPrice",
        "takeProfit",
        "stopLoss",
        "reportId",
        "thesis",
        "note",
        "createdAt",
        "updatedAt",
        "monitor",
    }
    watch_fields = {
        "id",
        "ticker",
        "name",
        "theme",
        "targetPrice",
        "reason",
        "note",
        "createdAt",
        "updatedAt",
    }
    holdings = [_board_item(item, holding_fields) for item in payload.get("holdings", [])[:PERSONAL_BOARD_MAX_ITEMS]]
    watchlist = [_board_item(item, watch_fields) for item in payload.get("watchlist", [])[:PERSONAL_BOARD_MAX_ITEMS]]
    board["holdings"] = [item for item in holdings if item.get("ticker")]
    board["watchlist"] = [item for item in watchlist if item.get("ticker")]
    if isinstance(payload.get("notification"), dict):
        board["notification"].update(
            {
                key: payload["notification"][key]
                for key in ("mode", "remoteName", "enabled")
                if key in payload["notification"]
            }
        )
    return board


def _load_personal_board() -> dict:
    if not PERSONAL_BOARD_PATH.exists():
        return _clone_default_board()
    try:
        payload = json.loads(PERSONAL_BOARD_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"personal board JSON is invalid: {PERSONAL_BOARD_PATH}") from exc
    if not isinstance(payload, dict):
        raise ValueError("personal board JSON must be an object")
    return _clean_personal_board(payload)


def _save_personal_board(payload: dict) -> dict:
    board = _clean_personal_board(payload)
    PERSONAL_BOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    PERSONAL_BOARD_PATH.write_text(
        json.dumps(board, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return board


def _latest_reports_by_ticker() -> dict[str, dict]:
    result: dict[str, dict] = {}
    for report in _list_reports():
        ticker = _ticker_key(report.get("ticker"))
        if ticker and ticker not in result:
            result[ticker] = report
    return result


def _stock_blob(row: dict) -> str:
    return " ".join(
        str(row.get(key) or "")
        for key in ("name", "ts_code", "industry", "sector_level_1", "sector_level_2", "concept_tags", "risk_flags")
    ).lower()


def _matches_any(text: str, keywords: list[str]) -> bool:
    return any(keyword.lower() in text for keyword in keywords)


def _latest_hotspot_payload() -> dict:
    try:
        return _get_hotspot_monitor().load_result(None)
    except Exception:
        return {"tradeDate": "", "summary": {}, "sectors": [], "stocks": [], "blockTrades": [], "moneyflowTop": []}


def _hotspot_rows_by_ticker(payload: dict) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for bucket in ("stocks", "moneyflowTop", "blockTrades"):
        for row in payload.get(bucket, []) or []:
            ticker = _ticker_key(row.get("ts_code"))
            if ticker and ticker not in rows:
                rows[ticker] = row
    return rows


def _hotspot_candidates(payload: dict) -> list[dict]:
    unique: dict[str, dict] = {}
    for bucket in ("stocks", "moneyflowTop", "blockTrades"):
        for row in payload.get(bucket, []) or []:
            ticker = _ticker_key(row.get("ts_code"))
            if not ticker or ticker in unique:
                continue
            text = _stock_blob(row)
            circ_mv = _number(row.get("circ_mv_yuan"))
            if _matches_any(text, EXCLUDED_THEME_KEYWORDS):
                continue
            if circ_mv is not None and circ_mv < DEFAULT_PERSONAL_BOARD["rules"]["minCircMvYuan"]:
                continue
            if not _matches_any(text, FUTURE_THEME_KEYWORDS):
                continue
            unique[ticker] = {
                "ticker": ticker,
                "name": row.get("name") or ticker,
                "theme": row.get("sector_level_1") or row.get("industry") or "",
                "stockScore": row.get("stock_score"),
                "netFlowRatio": row.get("net_flow_ratio"),
                "bigOrderRatio": row.get("big_elg_flow_ratio"),
                "amountRatio20": row.get("amount_ratio_20"),
                "reason": "hotspot_match",
            }
    return sorted(unique.values(), key=lambda item: _number(item.get("stockScore")) or 0, reverse=True)[:24]


def _holding_alerts(item: dict, report: dict | None) -> list[dict]:
    alerts = []
    monitor = item.get("monitor") if isinstance(item.get("monitor"), dict) else {}
    latest_price = _number(monitor.get("latestPrice"))
    take_profit = _number(item.get("takeProfit"))
    stop_loss = _number(item.get("stopLoss"))
    if not report:
        alerts.append({"level": "warn", "code": "NO_REPORT", "message": "No TradingAgents report is bound to this holding."})
    if latest_price is None:
        alerts.append({"level": "info", "code": "NO_PRICE", "message": "No refreshed price snapshot yet."})
        return alerts
    if take_profit is not None and latest_price >= take_profit:
        alerts.append({"level": "success", "code": "TAKE_PROFIT", "message": "Latest price reached the manual take-profit line."})
    if stop_loss is not None and latest_price <= stop_loss:
        alerts.append({"level": "danger", "code": "STOP_LOSS", "message": "Latest price reached the manual stop-loss line."})
    signal = str(monitor.get("signal") or "").upper()
    if signal in {"REDUCE_OR_EXIT", "SELL_TAKE_PROFIT", "EXPIRED"}:
        alerts.append({"level": "danger", "code": signal, "message": "The refreshed quant report is in an exit-oriented state."})
    return alerts


def _personal_board_payload(board: dict | None = None) -> dict:
    board = board or _load_personal_board()
    reports_by_ticker = _latest_reports_by_ticker()
    hotspot_payload = _latest_hotspot_payload()
    hotspot_rows = _hotspot_rows_by_ticker(hotspot_payload)

    holdings = []
    for item in board["holdings"]:
        ticker = _ticker_key(item.get("ticker"))
        report = reports_by_ticker.get(ticker)
        hotspot = hotspot_rows.get(ticker)
        latest_price = _number((item.get("monitor") or {}).get("latestPrice"))
        cost_price = _number(item.get("costPrice"))
        shares = _number(item.get("shares")) or 0
        pnl = (latest_price - cost_price) * shares if latest_price is not None and cost_price is not None else None
        pnl_pct = (latest_price / cost_price - 1) * 100 if latest_price is not None and cost_price else None
        holdings.append(
            {
                **item,
                "hasReport": bool(report),
                "latestReport": report,
                "hotspot": hotspot,
                "pnl": pnl,
                "pnlPct": pnl_pct,
                "alerts": _holding_alerts(item, report),
            }
        )

    watchlist = []
    for item in board["watchlist"]:
        ticker = _ticker_key(item.get("ticker"))
        report = reports_by_ticker.get(ticker)
        hotspot = hotspot_rows.get(ticker)
        watchlist.append(
            {
                **item,
                "hasReport": bool(report),
                "latestReport": report,
                "hotspot": hotspot,
                "hotspotScore": hotspot.get("stock_score") if hotspot else None,
                "hotspotDate": hotspot_payload.get("tradeDate") if hotspot else "",
            }
        )

    return {
        **board,
        "holdings": holdings,
        "watchlist": watchlist,
        "hotspotDate": hotspot_payload.get("tradeDate", ""),
        "hotspotCandidates": _hotspot_candidates(hotspot_payload),
        "reports": list(reports_by_ticker.values()),
        "updatedAt": datetime.now().isoformat(timespec="seconds"),
        "storagePath": str(PERSONAL_BOARD_PATH),
    }


def _refresh_personal_board() -> dict:
    board = _load_personal_board()
    today = datetime.now().strftime("%Y-%m-%d")
    refreshed = []
    for item in board["holdings"]:
        ticker = _ticker_key(item.get("ticker"))
        monitor = dict(item.get("monitor") or {})
        try:
            quant = _quant_payload(ticker, today)
            summary = quant.get("summary", {})
            monitor.update(
                {
                    "latestPrice": _number(summary.get("latestClose")),
                    "latestDate": summary.get("latestFlowDate") or today,
                    "signal": summary.get("signal") or "UNKNOWN",
                    "takeProfit": summary.get("takeProfit"),
                    "riskExit": summary.get("riskExit"),
                    "currentExit": summary.get("currentExit"),
                    "refreshedAt": quant.get("generatedAt"),
                    "error": "",
                }
            )
        except Exception as exc:  # noqa: BLE001 - diagnostic refresh endpoint
            monitor.update(
                {
                    "refreshedAt": datetime.now().isoformat(timespec="seconds"),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
        item["monitor"] = monitor
        item["updatedAt"] = datetime.now().isoformat(timespec="seconds")
        refreshed.append(ticker)
    saved = _save_personal_board(board)
    payload = _personal_board_payload(saved)
    payload["refreshed"] = refreshed
    return payload


def _read_text(path: Path, limit: int | None = None) -> str:
    if not path.exists() or not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text if limit is None else text[:limit]


def _safe_report_dir(report_id: str) -> Path:
    name = unquote(report_id).strip()
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise ValueError("invalid report id")
    path = (REPORTS_DIR / name).resolve()
    if REPORTS_DIR.resolve() not in path.parents:
        raise ValueError("invalid report path")
    if not path.exists() or not path.is_dir():
        raise FileNotFoundError(name)
    return path


def _report_ticker(report_dir: Path) -> str:
    match = re.match(r"(.+?)_\d{8}_\d{6}$", report_dir.name)
    return match.group(1) if match else report_dir.name


def _report_date(report_dir: Path) -> str:
    match = re.search(r"_(\d{8})_\d{6}$", report_dir.name)
    if not match:
        return ""
    raw = match.group(1)
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"


def _extract_signal(markdown: str) -> str:
    for pattern in (
        r"FINAL TRANSACTION PROPOSAL:\s*\*\*(BUY|HOLD|SELL)\*\*",
        r"\*\*Action\*\*:\s*(BUY|HOLD|SELL)",
        r"\b(BUY|HOLD|SELL)\b",
    ):
        match = re.search(pattern, markdown, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    return "UNKNOWN"


def _first_signal(*markdown_blocks: str) -> str:
    for markdown in markdown_blocks:
        signal = _extract_signal(markdown or "")
        if signal != "UNKNOWN":
            return signal
    return "UNKNOWN"


def _extract_quant_summary(markdown: str) -> dict:
    def first(pattern: str, default: str = "") -> str:
        match = re.search(pattern, markdown, re.MULTILINE)
        return match.group(1).strip() if match else default

    rows = []
    backtest_trades = []
    table_kind = None
    for line in markdown.splitlines():
        if line.startswith("| Date | Close | Net inflow"):
            table_kind = "market"
            continue
        if line.startswith("| Signal date | Entry date | Exit date"):
            table_kind = "backtest"
            continue
        if table_kind:
            if not line.startswith("|"):
                table_kind = None
                continue
            if line.startswith("|---"):
                continue
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if table_kind == "market" and len(cells) >= 7:
                rows.append(
                    {
                        "date": cells[0],
                        "close": cells[1],
                        "netInflow": cells[2],
                        "avgTurnover": cells[3],
                        "inflowRatio": cells[4],
                        "turnoverExpansion": cells[5],
                        "signal": cells[6],
                    }
                )
            elif table_kind == "backtest" and len(cells) >= 8:
                backtest_trades.append(
                    {
                        "signalDate": cells[0],
                        "entryDate": cells[1],
                        "exitDate": cells[2],
                        "entryPrice": cells[3],
                        "exitPrice": cells[4],
                        "return": cells[5],
                        "holdingDays": cells[6],
                        "status": cells[7],
                    }
                )

    signal_net_inflow = first(r"^- Signal-window 3-day net inflow:\s*(.+)$") or first(
        r"^- (?:3-day net inflow|Net inflow):\s*(.+)$"
    )
    signal_inflow_ratio = first(r"^- Signal-window flow intensity:\s*(.+)$") or first(
        r"^- (?:Net inflow / matched turnover|Net inflow / previous 10-day average turnover):\s*(.+)$"
    )
    latest_net_inflow = first(r"^- Latest 3-day net inflow:\s*(.+)$")
    latest_inflow_ratio = first(r"^- Latest 3-day flow intensity:\s*(.+)$")
    latest_flow_date = first(r"^- Latest flow date:\s*(.+)$")
    if rows:
        latest_total = None
        if not latest_net_inflow:
            try:
                latest_total = sum(float(row["netInflow"].replace(",", "")) for row in rows[-3:])
                latest_net_inflow = f"{latest_total:.2f} 万元"
            except (TypeError, ValueError):
                pass
        if not latest_inflow_ratio:
            try:
                if latest_total is None:
                    latest_total = sum(float(row["netInflow"].replace(",", "")) for row in rows[-3:])
                matched_days = min(3, len(rows))
                matched_turnover = float(rows[-1]["avgTurnover"].replace(",", "")) * matched_days
                latest_inflow_ratio = f"{latest_total / matched_turnover:.2%}"
            except (TypeError, ValueError, ZeroDivisionError):
                latest_inflow_ratio = rows[-1]["inflowRatio"]
        latest_flow_date = latest_flow_date or rows[-1]["date"]

    return {
        "signal": first(r"^Signal:\s*(.+)$", "UNKNOWN"),
        "reason": first(r"^Reason:\s*(.+)$"),
        "day0": first(r"^- Day 0:\s*(.+)$"),
        "day0Close": first(r"^- Day 0 close:\s*(.+)$"),
        "netInflow": signal_net_inflow,
        "inflowRatio": signal_inflow_ratio,
        "signalNetInflow": signal_net_inflow,
        "signalInflowRatio": signal_inflow_ratio,
        "latestNetInflow": latest_net_inflow,
        "latestInflowRatio": latest_inflow_ratio,
        "latestFlowDate": latest_flow_date,
        "entryZone": first(r"^- Suggested entry zone:\s*(.+)$"),
        "entryBasis": first(r"^- Entry pricing basis:\s*(.+)$"),
        "entryDate": first(r"^- Reference entry date:\s*(.+)$"),
        "entryPrice": first(r"^- Reference entry price:\s*(.+)$"),
        "takeProfit": first(r"^- Take-profit level:\s*(.+)$"),
        "riskExit": first(r"^- Risk-exit level:\s*(.+)$"),
        "currentExit": first(r"^- Current exit trigger:\s*(.+)$"),
        "suggestedExit": first(r"^- Suggested exit price now:\s*(.+)$"),
        "latestClose": first(r"^- Latest close:\s*(.+)$"),
        "completedTrades": first(r"^- Completed non-overlapping trades:\s*(.+)$", "0"),
        "winRate": first(r"^- Win rate:\s*(.+)$"),
        "averageReturn": first(r"^- Average return after modeled costs:\s*(.+)$"),
        "totalReturn": first(r"^- Compounded return after modeled costs:\s*(.+)$"),
        "benchmarkReturn": first(r"^- Buy-and-hold benchmark return:\s*(.+)$"),
        "excessReturn": first(r"^- Excess return vs benchmark:\s*(.+)$"),
        "maxDrawdown": first(r"^- Trade-sequence max drawdown:\s*(.+)$"),
        "profitFactor": first(r"^- Profit factor:\s*(.+)$"),
        "averageHoldingDays": first(r"^- Average holding days:\s*(.+)$"),
        "evidenceGrade": first(r"^- Evidence grade:\s*(.+)$", "INSUFFICIENT_SAMPLE"),
        "backtestTrades": backtest_trades,
        "rows": rows,
    }


def _list_reports() -> list[dict]:
    if not REPORTS_DIR.exists():
        return []
    reports = []
    for path in REPORTS_DIR.iterdir():
        if not path.is_dir():
            continue
        complete = path / "complete_report.md"
        if not complete.exists():
            continue
        quant = path / "quant_strategy_report.md"
        decision = _read_text(path / "5_portfolio" / "decision.md", limit=4000)
        trader = _read_text(path / "3_trading" / "trader.md", limit=4000)
        reports.append(
            {
                "id": path.name,
                "ticker": _report_ticker(path),
                "analysisDate": _report_date(path),
                "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
                "signal": _first_signal(decision, trader, _read_text(complete, limit=12000)),
                "hasQuant": quant.exists(),
                "hasFetchLog": (path / "data_fetch.log").exists(),
            }
        )
    return sorted(reports, key=lambda item: item["modified"], reverse=True)


def _report_payload(report_id: str) -> dict:
    path = _safe_report_dir(report_id)
    files = {
        "complete": "complete_report.md",
        "quant": "quant_strategy_report.md",
        "fetchLog": "data_fetch.log",
        "market": "1_analysts/market.md",
        "sentiment": "1_analysts/sentiment.md",
        "news": "1_analysts/news.md",
        "fundamentals": "1_analysts/fundamentals.md",
        "trader": "3_trading/trader.md",
        "portfolio": "5_portfolio/decision.md",
    }
    sections = {key: _read_text(path / rel) for key, rel in files.items()}
    return {
        "id": path.name,
        "ticker": _report_ticker(path),
        "analysisDate": _report_date(path),
        "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
        "signal": _first_signal(sections["portfolio"], sections["trader"], sections["complete"]),
        "quantSummary": _extract_quant_summary(sections["quant"]),
        "sections": sections,
    }


def _quant_payload(ticker: str, analysis_date: str) -> dict:
    markdown = build_quant_strategy_report(ticker, analysis_date)
    return {
        "ticker": ticker.upper(),
        "analysisDate": analysis_date,
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "summary": _extract_quant_summary(markdown),
        "markdown": markdown,
    }


def _fundamental_payload(ticker: str, analysis_date: str) -> dict:
    key = (ticker.upper(), analysis_date)
    now = time.monotonic()
    cached = _FUNDAMENTAL_CACHE.get(key)
    if cached and now - cached[0] < _FUNDAMENTAL_CACHE_TTL_SECONDS:
        return {**cached[1], "cached": True}

    payload = build_fundamental_snapshot(ticker, analysis_date)
    payload["generatedAt"] = datetime.now().isoformat(timespec="seconds")
    payload["cached"] = False
    _FUNDAMENTAL_CACHE[key] = (now, payload)
    return payload


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "TradingAgentsDashboard/0.1"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        try:
            if path == "/api/health":
                return _json_response(self, {"ok": True, "reportsDir": str(REPORTS_DIR)})
            if path == "/api/reports":
                return _json_response(self, {"reports": _list_reports()})
            if path.startswith("/api/personal-board"):
                return _json_response(self, _personal_board_payload())
            if path == "/api/hotspots/dates":
                monitor = _get_hotspot_monitor()
                store = monitor.store
                local_dates = store.available_raw_dates()
                scanned_dates = store.available_dates()
                try:
                    calendar_end = datetime.now()
                    calendar_start = calendar_end - timedelta(days=400)
                    trade_dates = monitor.trading_dates(calendar_start, calendar_end)
                    latest_trade_date = trade_dates[-1] if trade_dates else ""
                except Exception:  # Keep historical reports usable while the vendor is unavailable.
                    trade_dates = sorted(set(local_dates + scanned_dates))
                    latest_trade_date = (scanned_dates or local_dates or [""])[0]
                return _json_response(
                    self,
                    {
                        "dates": local_dates,
                        "scannedDates": scanned_dates,
                        "tradeDates": trade_dates,
                        "latestTradeDate": latest_trade_date,
                    },
                )
            if path.startswith("/api/hotspots/jobs/"):
                job_id = path.removeprefix("/api/hotspots/jobs/").strip()
                return _json_response(self, _hotspot_job_snapshot(job_id))
            if path == "/api/hotspots":
                trade_date = (query.get("date") or [""])[0] or None
                return _json_response(self, _get_hotspot_monitor().load_result(trade_date))
            if path == "/api/hotspots/export":
                trade_date = (query.get("date") or [""])[0] or None
                payload = _get_hotspot_monitor().load_result(trade_date)
                if not payload.get("tradeDate"):
                    raise FileNotFoundError(trade_date or "latest")
                filename = f'a-share-hotspot-{payload["tradeDate"]}.html'
                return _html_download_response(
                    self,
                    render_hotspot_export(payload),
                    filename,
                )
            if path.startswith("/api/reports/"):
                report_id = path.removeprefix("/api/reports/")
                return _json_response(self, _report_payload(report_id))
            if path.startswith("/api/quant/"):
                ticker = unquote(path.removeprefix("/api/quant/")).strip().upper()
                analysis_date = (query.get("date") or [""])[0] or datetime.now().strftime("%Y-%m-%d")
                return _json_response(self, _quant_payload(ticker, analysis_date))
            if path.startswith("/api/fundamentals/"):
                ticker = unquote(path.removeprefix("/api/fundamentals/")).strip().upper()
                analysis_date = (query.get("date") or [""])[0] or datetime.now().strftime("%Y-%m-%d")
                return _json_response(self, _fundamental_payload(ticker, analysis_date))
            return self._serve_static(path)
        except FileNotFoundError:
            return _json_response(self, {"error": "not_found"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:  # noqa: BLE001 - local diagnostic API
            return _json_response(
                self,
                {"error": type(exc).__name__, "detail": str(exc)},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/personal-board":
                payload = _read_json_body(self)
                return _json_response(self, _personal_board_payload(_save_personal_board(payload)))
            if parsed.path == "/api/personal-board/refresh":
                return _json_response(self, _refresh_personal_board())
            if parsed.path == "/api/hotspots/scan":
                payload = _read_json_body(self)
                trade_date = payload.get("tradeDate") or None
                if trade_date and not re.fullmatch(r"\d{4}-?\d{2}-?\d{2}", str(trade_date)):
                    raise ValueError("tradeDate must be YYYYMMDD or YYYY-MM-DD")
                refresh_target = payload.get("refreshTarget", True)
                if not isinstance(refresh_target, bool):
                    raise ValueError("refreshTarget must be a boolean")
                job = _start_hotspot_job(
                    str(trade_date) if trade_date else None,
                    refresh_target=refresh_target,
                )
                status = HTTPStatus.CONFLICT if job.get("alreadyRunning") else HTTPStatus.ACCEPTED
                return _json_response(self, job, status)
            return _json_response(self, {"error": "not_found"}, HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            return _json_response(
                self,
                {"error": type(exc).__name__, "detail": str(exc)},
                HTTPStatus.BAD_REQUEST,
            )
        except Exception as exc:  # noqa: BLE001 - local diagnostic API
            return _json_response(
                self,
                {"error": type(exc).__name__, "detail": str(exc)},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def log_message(self, fmt: str, *args) -> None:
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def _serve_static(self, path: str) -> None:
        static_root = FRONTEND_DIST_DIR if (FRONTEND_DIST_DIR / "index.html").exists() else FRONTEND_DIR
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        target = (static_root / rel).resolve()
        if static_root.resolve() not in target.parents and target != static_root.resolve():
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if not target.exists() or not target.is_file():
            target = static_root / "index.html"
        body = target.read_bytes()
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="TradingAgents local dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    _load_dotenv()
    httpd = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(f"TradingAgents dashboard: http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop.")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
