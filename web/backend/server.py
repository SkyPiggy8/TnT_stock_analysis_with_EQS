from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import time
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = ROOT / "web" / "frontend"
REPORTS_DIR = ROOT / "reports"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tradingagents.dataflows.a_share_quant_strategy import build_quant_strategy_report  # noqa: E402
from tradingagents.dataflows.tushare_fundamentals import build_fundamental_snapshot  # noqa: E402


_FUNDAMENTAL_CACHE: dict[tuple[str, str], tuple[float, dict]] = {}
_FUNDAMENTAL_CACHE_TTL_SECONDS = 300


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


def _json_response(handler: BaseHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


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
    table_started = False
    for line in markdown.splitlines():
        if line.startswith("| Date | Close | Net inflow"):
            table_started = True
            continue
        if table_started:
            if not line.startswith("|") or line.startswith("|---"):
                continue
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) >= 7:
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

    return {
        "signal": first(r"^Signal:\s*(.+)$", "UNKNOWN"),
        "reason": first(r"^Reason:\s*(.+)$"),
        "day0": first(r"^- Day 0:\s*(.+)$"),
        "day0Close": first(r"^- Day 0 close:\s*(.+)$"),
        "netInflow": first(r"^- Net inflow:\s*(.+)$"),
        "inflowRatio": first(r"^- Net inflow / previous 10-day average turnover:\s*(.+)$"),
        "takeProfit": first(r"^- Take-profit level:\s*(.+)$"),
        "riskExit": first(r"^- Risk-exit level:\s*(.+)$"),
        "latestClose": first(r"^- Latest close:\s*(.+)$"),
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

    def log_message(self, fmt: str, *args) -> None:
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def _serve_static(self, path: str) -> None:
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        target = (FRONTEND_DIR / rel).resolve()
        if FRONTEND_DIR.resolve() not in target.parents and target != FRONTEND_DIR.resolve():
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if not target.exists() or not target.is_file():
            target = FRONTEND_DIR / "index.html"
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
