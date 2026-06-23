from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = ROOT / "config" / "hotspot_monitor.yaml"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Hotspot config must be a mapping: {path}")
    return payload


def _resolve_path(value: str | Path, *, relative_to: Path) -> Path:
    path = Path(os.path.expandvars(str(value))).expanduser()
    if not path.is_absolute():
        path = relative_to / path
    return path.resolve()


def load_hotspot_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load the committed defaults and merge an optional user override."""

    config = _read_yaml(DEFAULT_CONFIG_PATH)
    source = DEFAULT_CONFIG_PATH
    if path:
        source = Path(path).expanduser().resolve()
        config = _deep_merge(config, _read_yaml(source))

    data_override = os.getenv("TRADINGAGENTS_HOTSPOT_DATA_DIR")
    report_override = os.getenv("TRADINGAGENTS_HOTSPOT_REPORT_DIR")
    if data_override:
        config["storage"]["data_dir"] = data_override
    if report_override:
        config["storage"]["report_dir"] = report_override

    config["storage"]["data_dir"] = _resolve_path(
        config["storage"]["data_dir"], relative_to=ROOT
    )
    config["storage"]["report_dir"] = _resolve_path(
        config["storage"]["report_dir"], relative_to=ROOT
    )
    config["config_path"] = source
    config["project_root"] = ROOT
    return config
