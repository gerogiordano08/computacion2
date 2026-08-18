from __future__ import annotations

import time
from typing import Any

from analizadores.base import run_analyzer_loop
from macos_api import build_summary_entry, get_process_states_via_ps


def _analyze_resumen(pids: list[int], focus_pid: int, state: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any], str | None]:
    cpu_state = state.setdefault("cpu", {})
    details_cache = state.setdefault("details_cache", {})
    now = time.monotonic()
    refresh_budget = 6
    refresh_targets: set[int] = set()
    if focus_pid in pids:
        refresh_targets.add(focus_pid)
    stale_cutoff = now - 20.0
    # pbi_status is not consistently meaningful for processes we may inspect
    # without elevated privileges.  One ps call gives their public BSD state
    # without adding a subprocess per PID.
    public_states = get_process_states_via_ps()
    for pid in pids:
        if len(refresh_targets) >= refresh_budget:
            break
        cached = details_cache.get(pid)
        if cached is None or float(cached.get("updated_at", 0.0)) < stale_cutoff:
            refresh_targets.add(pid)
    rows: list[dict[str, Any]] = []
    for pid in pids:
        entry = build_summary_entry(pid, cpu_state, now, include_details=(pid in refresh_targets))
        if entry:
            public_state = public_states.get(pid)
            if public_state:
                entry["state"], entry["state_name"] = public_state
            if pid in refresh_targets:
                details_cache[pid] = {
                    "path": entry.get("path"),
                    "args": entry.get("args") or [],
                    "command": entry.get("command"),
                    "basename": entry.get("basename"),
                    "updated_at": now,
                }
            else:
                cached = details_cache.get(pid)
                if cached:
                    if cached.get("path"):
                        entry["path"] = cached["path"]
                    if cached.get("args"):
                        entry["args"] = list(cached["args"])
                    if cached.get("command"):
                        entry["command"] = cached["command"]
                    if cached.get("basename"):
                        entry["basename"] = cached["basename"]
            rows.append(entry)
    rows.sort(key=lambda item: (-item["cpu"], -item["rss"], item["pid"]))
    active = {item["pid"] for item in rows}
    for known_pid in list(cpu_state):
        if known_pid not in active:
            cpu_state.pop(known_pid, None)
    for known_pid in list(details_cache):
        if known_pid not in active:
            details_cache.pop(known_pid, None)
    return rows, state, None


def analizador_resumen(
    pid_queue: Any,
    result_queue: Any,
    interval_value: Any,
    focus_pid_value: Any,
    shutdown_event: Any,
    verbose_flag: Any,
) -> None:
    run_analyzer_loop(
        "resumen",
        pid_queue,
        result_queue,
        interval_value,
        focus_pid_value,
        shutdown_event,
        verbose_flag,
        _analyze_resumen,
    )
