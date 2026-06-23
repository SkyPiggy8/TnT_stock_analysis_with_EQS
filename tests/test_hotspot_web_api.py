from __future__ import annotations

import threading
import time

import pytest

from web.backend import server


@pytest.mark.unit
def test_hotspot_background_job_is_singleton_and_reports_progress(monkeypatch):
    release = threading.Event()

    class FakeMonitor:
        def scan(self, trade_date, progress):
            progress("download", 1, 2, "下载日线")
            release.wait(timeout=2)
            progress("calculate", 2, 2, "计算评分")
            return {"tradeDate": "20260618"}

    monkeypatch.setattr(server, "_HOTSPOT_MONITOR", FakeMonitor())
    with server._HOTSPOT_JOBS_LOCK:
        server._HOTSPOT_JOBS.clear()

    first = server._start_hotspot_job("20260618")
    for _ in range(50):
        snapshot = server._hotspot_job_snapshot(first["jobId"])
        if snapshot["status"] == "running":
            break
        time.sleep(0.01)
    second = server._start_hotspot_job("20260618")
    assert second["jobId"] == first["jobId"]
    assert second["alreadyRunning"] is True
    assert snapshot["stage"] == "download"
    assert snapshot["progress"] == 50

    release.set()
    for _ in range(100):
        snapshot = server._hotspot_job_snapshot(first["jobId"])
        if snapshot["status"] == "complete":
            break
        time.sleep(0.01)
    assert snapshot["status"] == "complete"
    assert snapshot["tradeDate"] == "20260618"
    assert snapshot["progress"] == 100
