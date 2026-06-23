from __future__ import annotations

import argparse
import json
import logging

from tradingagents.hotspot_monitor import HotspotMonitor, load_hotspot_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the A-share end-of-day hotspot radar")
    parser.add_argument("--trade-date", help="YYYYMMDD; defaults to the latest open trading day")
    parser.add_argument("--config", help="Optional YAML override")
    parser.add_argument("--force", action="store_true", help="Ignore cached raw files")
    parser.add_argument("--no-excel", action="store_true")
    parser.add_argument("--no-markdown", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    monitor = HotspotMonitor(load_hotspot_config(args.config))
    result = monitor.scan(
        args.trade_date,
        force=args.force,
        export_excel=not args.no_excel,
        export_markdown=not args.no_markdown,
    )
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
