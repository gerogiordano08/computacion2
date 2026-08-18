from __future__ import annotations

from typing import Any

from analizadores.base import run_analyzer_loop
from macos_api import get_focused_pid, inspect_threads


def _analyze_threads(pids: list[int], focus_pid: int, state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str | None]:
    pid = get_focused_pid(pids, focus_pid)
    if pid is None:
        return {"focused_pid": None, "thread_count": 0, "threads": []}, state, None
    info = inspect_threads(pid)
    info["focused_pid"] = pid
    return info, state, info.get("error")


def analizador_threads(
    pid_queue: Any,
    result_queue: Any,
    interval_value: Any,
    focus_pid_value: Any,
    shutdown_event: Any,
    verbose_flag: Any,
) -> None:
    run_analyzer_loop(
        "threads",
        pid_queue,
        result_queue,
        interval_value,
        focus_pid_value,
        shutdown_event,
        verbose_flag,
        _analyze_threads,
    )
