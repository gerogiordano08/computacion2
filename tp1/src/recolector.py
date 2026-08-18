from __future__ import annotations

import queue
import time
from typing import Any

from macos_api import list_pids


def _put_latest(target_queue: Any, item: list[int]) -> None:
    while True:
        try:
            target_queue.put_nowait(item)
            return
        except queue.Full:
            try:
                target_queue.get_nowait()
            except queue.Empty:
                return


def recolector_main(pid_queues: dict[str, Any], shutdown_event: Any, verbose_flag: Any) -> None:
    while not shutdown_event.is_set():
        pids = list_pids()
        for pid_queue in pid_queues.values():
            _put_latest(pid_queue, pids)
        if verbose_flag.value:
            print(f"[recolector] distribuidos {len(pids)} pids", flush=True)
        shutdown_event.wait(1.0)

