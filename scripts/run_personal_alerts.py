from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tradingagents.personal_alerts import (  # noqa: E402
    DEFAULT_BOARD_PATH,
    DEFAULT_STATE_PATH,
    PersonalAlertError,
    build_alerts,
    filter_new_alerts,
    load_akshare_quotes,
    load_board,
    load_dotenv,
    load_state,
    market_is_open,
    render_message,
    save_state,
    send_webhook,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run personal holding price alerts.")
    parser.add_argument("--board", type=Path, default=DEFAULT_BOARD_PATH)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--webhook-url", default="")
    parser.add_argument(
        "--webhook-type",
        default="",
        choices=["", "generic", "serverchan", "wecom"],
        help="generic posts JSON; serverchan posts title/desp; wecom posts markdown.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print alerts without sending.")
    parser.add_argument("--repeat", action="store_true", help="Send repeated alerts even when already active.")
    parser.add_argument("--market-hours-only", action="store_true", help="Skip outside A-share trading windows.")
    parser.add_argument("--watch", action="store_true", help="Keep polling quotes and send alerts when thresholds are hit.")
    parser.add_argument("--interval", type=int, default=60, help="Polling interval in seconds for --watch.")
    parser.add_argument("--include-quant-signals", action="store_true", help="Also alert on exit-oriented quant signals.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable summary.")
    return parser.parse_args()


def run_once(args: argparse.Namespace, webhook_url: str, webhook_type: str) -> tuple[int, dict]:
    if args.market_hours_only and not market_is_open():
        result = {"status": "skipped", "reason": "outside_market_hours", "sent": 0}
        return 0, result

    try:
        board = load_board(args.board)
        quotes = load_akshare_quotes()
        state = load_state(args.state)
        next_state = copy.deepcopy(state)
        alerts = build_alerts(board, quotes, include_quant_signals=args.include_quant_signals)
        new_alerts = filter_new_alerts(alerts, next_state, repeat=args.repeat)
    except PersonalAlertError as exc:
        return 2, {"status": "failed", "error": str(exc)}

    title, content = render_message(new_alerts)
    should_send = bool(new_alerts and webhook_url and not args.dry_run)
    if should_send:
        try:
            send_webhook(title, content, webhook_url, webhook_type=webhook_type)
        except Exception as exc:  # noqa: BLE001 - CLI boundary
            return 3, {"status": "failed", "error": f"Webhook send failed: {type(exc).__name__}: {exc}"}
    if webhook_url and not args.dry_run:
        save_state(next_state, args.state)

    result = {
        "status": "ok",
        "activeAlerts": len(alerts),
        "newAlerts": len(new_alerts),
        "sent": len(new_alerts) if should_send else 0,
        "dryRun": args.dry_run or not webhook_url,
        "webhookType": webhook_type if webhook_url else "",
        "board": str(args.board),
        "state": str(args.state),
    }
    if new_alerts:
        result["message"] = content
    return 0, result


def print_result(result: dict, json_output: bool) -> None:
    if json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        return
    if result.get("status") == "skipped":
        print(f"Skipped: {result.get('reason')}", flush=True)
        return
    print(json.dumps({key: value for key, value in result.items() if key != "message"}, ensure_ascii=False), flush=True)
    if result.get("message"):
        print(result["message"], flush=True)


def main() -> int:
    args = parse_args()
    load_dotenv()

    webhook_url = args.webhook_url or os.getenv("TRADINGAGENTS_ALERT_WEBHOOK_URL", "")
    webhook_type = args.webhook_type or os.getenv("TRADINGAGENTS_ALERT_WEBHOOK_TYPE", "generic")

    if args.watch and not args.dry_run and not webhook_url:
        print("Personal alert failed: --watch requires TRADINGAGENTS_ALERT_WEBHOOK_URL or --webhook-url.", file=sys.stderr)
        return 4

    if args.watch:
        interval = max(10, int(args.interval or 60))
        print(f"Watching personal alerts every {interval}s. Press Ctrl+C to stop.", flush=True)
        while True:
            code, result = run_once(args, webhook_url, webhook_type)
            print_result(result, args.json)
            if code not in (0, 2):
                return code
            time.sleep(interval)

    code, result = run_once(args, webhook_url, webhook_type)
    if code == 2:
        print(f"Personal alert failed: {result.get('error')}", file=sys.stderr)
        return code
    if code == 3:
        print(result.get("error"), file=sys.stderr)
        return code
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_result(result, False)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
