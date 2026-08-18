from __future__ import annotations

import queue
from typing import Any


def agregador_main(snapshot_global: Any, result_queue: Any, shutdown_event: Any, verbose_flag: Any) -> None:
    while not shutdown_event.is_set():
        try:
            message = result_queue.get(timeout=0.25)
        except queue.Empty:
            continue
        snapshot_global[message["view"]] = {
            "updated_at": message["updated_at"],
            "data": message["data"],
            "error": message["error"],
        }
        if verbose_flag.value:
            print(f"[agregador] actualizada vista {message['view']}", flush=True)
    while True:
        try:
            message = result_queue.get_nowait()
        except queue.Empty:
            break
        snapshot_global[message["view"]] = {
            "updated_at": message["updated_at"],
            "data": message["data"],
            "error": message["error"],
        }

