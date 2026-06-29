from __future__ import annotations

import argparse
import copy
import json
import os
import sys
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
    parser.add_argument("--json", action="store_true", help="Print machine-readable summary.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_dotenv()

    if args.market_hours_only and not market_is_open():
        result = {"status": "skipped", "reason": "outside_market_hours", "sent": 0}
        print(json.dumps(result, ensure_ascii=False) if args.json else "Skipped: outside market hours.")
        return 0

    webhook_url = args.webhook_url or os.getenv("TRADINGAGENTS_ALERT_WEBHOOK_URL", "")
    webhook_type = args.webhook_type or os.getenv("TRADINGAGENTS_ALERT_WEBHOOK_TYPE", "generic")

    try:
        board = load_board(args.board)
        quotes = load_akshare_quotes()
        state = load_state(args.state)
        next_state = copy.deepcopy(state)
        alerts = build_alerts(board, quotes)
        new_alerts = filter_new_alerts(alerts, next_state, repeat=args.repeat)
    except PersonalAlertError as exc:
        print(f"Personal alert failed: {exc}", file=sys.stderr)
        return 2

    title, content = render_message(new_alerts)
    should_send = bool(new_alerts and webhook_url and not args.dry_run)
    if should_send:
        try:
            send_webhook(title, content, webhook_url, webhook_type=webhook_type)
        except Exception as exc:  # noqa: BLE001 - CLI boundary
            print(f"Webhook send failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 3
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
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False))
        if new_alerts:
            print(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
