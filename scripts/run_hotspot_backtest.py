from __future__ import annotations

import argparse
import json
import logging

from tradingagents.hotspot_monitor import HotspotMonitor, load_hotspot_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the hotspot-radar T+1 diagnostic backtest")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--holding-days", default="1,3,5,10")
    parser.add_argument("--buy-price-mode", choices=["next_open"], default="next_open")
    parser.add_argument("--config")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    holding_days = [int(value) for value in args.holding_days.split(",") if value.strip()]
    monitor = HotspotMonitor(load_hotspot_config(args.config))
    result = monitor.backtest(args.start_date, args.end_date, holding_days=holding_days)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
