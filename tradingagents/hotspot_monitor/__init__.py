"""A-share end-of-day hotspot radar.

The package is deterministic and research-only.  It never connects to a
broker and never submits an order.
"""

from .config import load_hotspot_config
from .service import HotspotMonitor, run_daily_scan

__all__ = ["HotspotMonitor", "load_hotspot_config", "run_daily_scan"]
