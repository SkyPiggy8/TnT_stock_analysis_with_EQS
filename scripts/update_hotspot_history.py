from __future__ import annotations

import argparse
import logging

from tradingagents.hotspot_monitor import HotspotMonitor, load_hotspot_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill batch Tushare data for the hotspot radar")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--config")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    monitor = HotspotMonitor(load_hotspot_config(args.config))
    dates = monitor.update_history(args.start_date, args.end_date, force=args.force)
    print(f"Cached {len(dates)} trading days")


if __name__ == "__main__":
    main()
