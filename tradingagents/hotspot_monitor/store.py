from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


class HotspotStore:
    """Parquet raw cache plus a small DuckDB result catalog."""

    def __init__(self, config: dict[str, Any]):
        self.data_dir = Path(config["storage"]["data_dir"])
        self.raw_dir = self.data_dir / "raw"
        self.db_path = self.data_dir / "hotspot_monitor.duckdb"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self):
        return duckdb.connect(str(self.db_path))

    @staticmethod
    def _quote_identifier(value: str) -> str:
        return '"' + value.replace('"', '""') + '"'

    def _add_missing_columns(self, con, table: str) -> None:
        """Evolve a result table when a newer scanner adds output fields."""
        table_columns = {
            row[0]
            for row in con.execute(f"DESCRIBE {self._quote_identifier(table)}").fetchall()
        }
        for name, data_type, *_ in con.execute("DESCRIBE payload").fetchall():
            if name not in table_columns:
                con.execute(
                    f"ALTER TABLE {self._quote_identifier(table)} "
                    f"ADD COLUMN {self._quote_identifier(name)} {data_type}"
                )

    def _initialize(self) -> None:
        with self._connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS scan_runs (
                    trade_date VARCHAR PRIMARY KEY,
                    status VARCHAR NOT NULL,
                    started_at TIMESTAMP,
                    finished_at TIMESTAMP,
                    summary_json VARCHAR,
                    error VARCHAR
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS data_quality_flags (
                    trade_date VARCHAR,
                    ts_code VARCHAR,
                    data_quality_flags VARCHAR
                )
                """
            )

    @staticmethod
    def _date_key(trade_date: str) -> str:
        return trade_date.replace("-", "")

    def raw_path(self, interface: str, trade_date: str) -> Path:
        safe = interface.replace("/", "_").replace("\\", "_")
        return self.raw_dir / safe / f"{self._date_key(trade_date)}.parquet"

    def has_raw(self, interface: str, trade_date: str) -> bool:
        return self.raw_path(interface, trade_date).exists()

    def write_raw(self, interface: str, trade_date: str, frame: pd.DataFrame) -> Path:
        path = self.raw_path(interface, trade_date)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = frame.copy()
        if not len(payload.columns):
            payload = pd.DataFrame({"_empty": pd.Series(dtype="boolean")})
        payload.to_parquet(path, index=False)
        return path

    def read_raw(self, interface: str, trade_date: str) -> pd.DataFrame:
        path = self.raw_path(interface, trade_date)
        if not path.exists():
            return pd.DataFrame()
        frame = pd.read_parquet(path)
        return frame.drop(columns=["_empty"], errors="ignore")

    def read_many(self, interface: str, trade_dates: list[str]) -> pd.DataFrame:
        frames = [self.read_raw(interface, date) for date in trade_dates]
        frames = [frame for frame in frames if not frame.empty]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def save_frame(self, table: str, trade_date: str, frame: pd.DataFrame) -> None:
        if table not in {
            "daily_signals",
            "sector_scores",
            "backtest_metrics",
            "data_quality_flags",
        }:
            raise ValueError(f"Unsupported result table: {table}")
        with self._connect() as con:
            exists = con.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [table]
            ).fetchone()[0]
            if exists:
                con.execute(f'DELETE FROM "{table}" WHERE trade_date = ?', [trade_date])
            if frame.empty:
                return
            payload = frame.copy()
            payload["trade_date"] = trade_date
            con.register("payload", payload)
            if not exists:
                con.execute(f'CREATE TABLE "{table}" AS SELECT * FROM payload')
            else:
                self._add_missing_columns(con, table)
                con.execute(f'INSERT INTO "{table}" BY NAME SELECT * FROM payload')

    def load_frame(self, table: str, trade_date: str) -> pd.DataFrame:
        with self._connect() as con:
            exists = con.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [table]
            ).fetchone()[0]
            if not exists:
                return pd.DataFrame()
            return con.execute(
                f'SELECT * FROM "{table}" WHERE trade_date = ?', [trade_date]
            ).fetchdf()

    def available_dates(self) -> list[str]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT trade_date FROM scan_runs WHERE status = 'complete' ORDER BY trade_date DESC"
            ).fetchall()
        return [row[0] for row in rows]

    def available_raw_dates(
        self,
        interfaces: tuple[str, ...] = ("daily", "daily_basic", "moneyflow"),
    ) -> list[str]:
        """Return dates with all market-wide inputs already cached locally."""

        date_sets: list[set[str]] = []
        for interface in interfaces:
            directory = self.raw_dir / interface
            if not directory.exists():
                return []
            dates = {
                path.stem
                for path in directory.glob("*.parquet")
                if len(path.stem) == 8 and path.stem.isdigit()
            }
            date_sets.append(dates)
        available = set.intersection(*date_sets) if date_sets else set()
        return sorted(available, reverse=True)

    def record_run(
        self,
        trade_date: str,
        status: str,
        *,
        summary: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        now = datetime.now()
        with self._connect() as con:
            current = con.execute(
                "SELECT started_at FROM scan_runs WHERE trade_date = ?", [trade_date]
            ).fetchone()
            started = current[0] if current and current[0] else now
            finished = now if status in {"complete", "failed", "skipped"} else None
            con.execute("DELETE FROM scan_runs WHERE trade_date = ?", [trade_date])
            con.execute(
                "INSERT INTO scan_runs VALUES (?, ?, ?, ?, ?, ?)",
                [
                    trade_date,
                    status,
                    started,
                    finished,
                    json.dumps(summary, ensure_ascii=False) if summary else None,
                    error,
                ],
            )

    def load_summary(self, trade_date: str) -> dict[str, Any]:
        with self._connect() as con:
            row = con.execute(
                "SELECT summary_json FROM scan_runs WHERE trade_date = ? AND status = 'complete'",
                [trade_date],
            ).fetchone()
        return json.loads(row[0]) if row and row[0] else {}
