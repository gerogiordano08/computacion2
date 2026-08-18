from __future__ import annotations

import time
from typing import Any

from macos_api import get_system_snapshot


def analizador_sistema(
    pid_queue: Any,
    result_queue: Any,
    interval_value: Any,
    focus_pid_value: Any,
    snapshot_global: Any,
    shutdown_event: Any,
    verbose_flag: Any,
) -> None:
    del focus_pid_value
    previous_ticks: list[int] | None = None
    latest_pids: list[int] = []
    next_run = 0.0
    while not shutdown_event.is_set():
        while True:
            try:
                latest_pids = pid_queue.get_nowait()
            except Exception:
                break
        now = time.monotonic()
        interval = max(0.1, float(interval_value.value))
        if now < next_run:
            shutdown_event.wait(min(0.1, next_run - now))
            continue
        summary_rows = list(snapshot_global.get("resumen", {}).get("data", []) or [])
        snapshot = get_system_snapshot(latest_pids, previous_ticks, summary_rows=summary_rows)
        previous_ticks = snapshot.get("cpu", {}).get("raw_ticks")
        result_queue.put(
            {
                "view": "sistema",
                "updated_at": time.time(),
                "data": snapshot,
                "error": snapshot.get("vm_stat_error"),
            }
        )
        if verbose_flag.value:
            print("[sistema] publicado snapshot", flush=True)
        next_run = time.monotonic() + interval
