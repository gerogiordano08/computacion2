from __future__ import annotations

from typing import Any

from analizadores.base import run_analyzer_loop
from macos_api import get_focused_pid, inspect_scheduling


def _analyze_scheduling(pids: list[int], focus_pid: int, state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str | None]:
    pid = get_focused_pid(pids, focus_pid)
    if pid is None:
        return {"focused_pid": None}, state, None
    info = inspect_scheduling(pid)
    info["focused_pid"] = pid
    return info, state, info.get("error")


def analizador_scheduling(
    pid_queue: Any,
    result_queue: Any,
    interval_value: Any,
    focus_pid_value: Any,
    shutdown_event: Any,
    verbose_flag: Any,
) -> None:
    run_analyzer_loop(
        "scheduling",
        pid_queue,
        result_queue,
        interval_value,
        focus_pid_value,
        shutdown_event,
        verbose_flag,
        _analyze_scheduling,
    )
