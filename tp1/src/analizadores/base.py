from __future__ import annotations

import queue
import time
from typing import Any, Callable


AnalyzerFn = Callable[[list[int], int, dict[str, Any]], tuple[Any, dict[str, Any], str | None]]


def _drain_latest(pid_queue: Any, current: list[int]) -> list[int]:
    latest = current
    while True:
        try:
            latest = pid_queue.get_nowait()
        except queue.Empty:
            return latest


def run_analyzer_loop(
    view_name: str,
    pid_queue: Any,
    result_queue: Any,
    interval_value: Any,
    focus_pid_value: Any,
    shutdown_event: Any,
    verbose_flag: Any,
    analyzer_fn: AnalyzerFn,
) -> None:
    state: dict[str, Any] = {}
    latest_pids: list[int] = []
    next_run = 0.0
    last_focus_pid: int | None = None
    while not shutdown_event.is_set():
        latest_pids = _drain_latest(pid_queue, latest_pids)
        now = time.monotonic()
        interval = max(0.1, float(interval_value.value))
        focus_pid = int(focus_pid_value.value)
        focus_changed = last_focus_pid is not None and focus_pid != last_focus_pid
        if now < next_run and not focus_changed:
            shutdown_event.wait(min(0.1, next_run - now))
            continue
        data: Any
        error: str | None
        try:
            data, state, error = analyzer_fn(latest_pids, focus_pid, state)
        except Exception as exc:  # pragma: no cover - protection path
            data = {}
            error = f"{type(exc).__name__}: {exc}"
        result_queue.put(
            {
                "view": view_name,
                "updated_at": time.time(),
                "data": data,
                "error": error,
            }
        )
        if verbose_flag.value:
            print(f"[{view_name}] publicado snapshot", flush=True)
        last_focus_pid = focus_pid
        next_run = time.monotonic() + interval
