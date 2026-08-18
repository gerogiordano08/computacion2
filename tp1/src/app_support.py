from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


VIEW_ORDER = [
    "resumen",
    "memoria",
    "fds",
    "threads",
    "senales",
    "scheduling",
    "sistema",
]

VIEW_KEYS = {
    "1": "resumen",
    "r": "resumen",
    "2": "memoria",
    "m": "memoria",
    "3": "fds",
    "f": "fds",
    "4": "threads",
    "t": "threads",
    "5": "senales",
    "s": "senales",
    "6": "scheduling",
    "p": "scheduling",
    "7": "sistema",
    "g": "sistema",
}

VIEW_TITLES = {
    "resumen": "Resumen",
    "memoria": "Memoria",
    "fds": "File Descriptors",
    "threads": "Threads",
    "senales": "Senales",
    "scheduling": "Scheduling",
    "sistema": "Sistema",
}

DEFAULT_INTERVALS = {
    "resumen": 2.0,
    "memoria": 3.0,
    "fds": 5.0,
    "threads": 2.0,
    "senales": 10.0,
    "scheduling": 10.0,
    "sistema": 2.0,
}

MIN_INTERVALS = {
    "resumen": 0.5,
    "memoria": 1.0,
    "fds": 2.0,
    "threads": 0.5,
    "senales": 5.0,
    "scheduling": 5.0,
    "sistema": 1.0,
}

DEFAULT_CONFIG = {
    "intervals": DEFAULT_INTERVALS,
    "minimum_intervals": MIN_INTERVALS,
    "filters": {
        "command": "",
        "user": "",
    },
    "display": {
        "sort": "cpu",
    },
}


def merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


def load_config(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path)
    if not path.exists():
        return copy.deepcopy(DEFAULT_CONFIG)
    try:
        user_config = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return copy.deepcopy(DEFAULT_CONFIG)
    merged = merge_dicts(DEFAULT_CONFIG, user_config)
    for view in VIEW_ORDER:
        value = float(merged["intervals"].get(view, DEFAULT_INTERVALS[view]))
        merged["intervals"][view] = max(MIN_INTERVALS[view], value)
    return merged


def build_empty_snapshot_entry(default_data: Any) -> dict[str, Any]:
    return {
        "updated_at": None,
        "data": default_data,
        "error": None,
    }


def initial_snapshot_payload() -> dict[str, Any]:
    return {
        "resumen": build_empty_snapshot_entry([]),
        "memoria": build_empty_snapshot_entry({"focused_pid": None, "info": None}),
        "fds": build_empty_snapshot_entry({"focused_pid": None, "count": 0, "entries": []}),
        "threads": build_empty_snapshot_entry({"focused_pid": None, "thread_count": 0, "threads": []}),
        "senales": build_empty_snapshot_entry({"focused_pid": None, "blocked": [], "pending": [], "notes": []}),
        "scheduling": build_empty_snapshot_entry({"focused_pid": None}),
        "sistema": build_empty_snapshot_entry({}),
    }


def snapshot_proxy_to_plain(snapshot_proxy: Any) -> dict[str, Any]:
    return copy.deepcopy({key: snapshot_proxy.get(key) for key in VIEW_ORDER})


def apply_intervals(interval_values: dict[str, Any], config: dict[str, Any]) -> None:
    for view in VIEW_ORDER:
        interval = float(config["intervals"].get(view, DEFAULT_INTERVALS[view]))
        interval = max(MIN_INTERVALS[view], interval)
        value_proxy = interval_values[view]
        with value_proxy.get_lock():
            value_proxy.value = interval


def clamp_interval(view: str, candidate: float) -> float:
    return max(MIN_INTERVALS[view], round(candidate, 1))

