from __future__ import annotations

import argparse
import curses
import json
import multiprocessing as mp
import signal
import time
from pathlib import Path
from typing import Any

from agregador import agregador_main
from analizadores.fds import analizador_fds
from analizadores.memoria import analizador_memoria
from analizadores.resumen import analizador_resumen
from analizadores.scheduling import analizador_scheduling
from analizadores.senales import analizador_senales
from analizadores.sistema import analizador_sistema
from analizadores.threads import analizador_threads
from app_support import VIEW_ORDER, apply_intervals, initial_snapshot_payload, load_config, snapshot_proxy_to_plain
from display import run_display
from recolector import recolector_main
from senales import install_signal_controller


ANALYZER_TARGETS = {
    "resumen": analizador_resumen,
    "memoria": analizador_memoria,
    "fds": analizador_fds,
    "threads": analizador_threads,
    "senales": analizador_senales,
    "scheduling": analizador_scheduling,
    "sistema": analizador_sistema,
}


def initialize_snapshot(snapshot_global: Any) -> None:
    for key, value in initial_snapshot_payload().items():
        snapshot_global[key] = value


def start_processes(
    ctx: Any,
    snapshot_global: Any,
    pid_queues: dict[str, Any],
    result_queue: Any,
    interval_values: dict[str, Any],
    focus_pid_value: Any,
    shutdown_event: Any,
    verbose_flag: Any,
) -> list[Any]:
    processes = [
        ctx.Process(
            name="recolector",
            target=recolector_main,
            args=(pid_queues, shutdown_event, verbose_flag),
        ),
        ctx.Process(
            name="agregador",
            target=agregador_main,
            args=(snapshot_global, result_queue, shutdown_event, verbose_flag),
        ),
    ]
    for view in VIEW_ORDER:
        args = (
            pid_queues[view],
            result_queue,
            interval_values[view],
            focus_pid_value,
        )
        if view == "sistema":
            args = args + (snapshot_global,)
        args = args + (
            shutdown_event,
            verbose_flag,
        )
        processes.append(
            ctx.Process(
                name=f"analizador_{view}",
                target=ANALYZER_TARGETS[view],
                args=args,
            )
        )
    for process in processes:
        process.start()
    return processes


def dump_snapshot(snapshot_global: Any, destination_dir: Path) -> Path:
    payload = snapshot_proxy_to_plain(snapshot_global)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    dump_path = destination_dir / f"dump_{timestamp}.json"
    dump_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return dump_path


def stop_processes(processes: list[Any], shutdown_event: Any) -> None:
    shutdown_event.set()
    for process in processes:
        process.join(timeout=2.0)
    for process in processes:
        if process.is_alive():
            process.terminate()
    for process in processes:
        process.join(timeout=1.0)


def make_signal_handler(
    config_path: Path,
    interval_values: dict[str, Any],
    snapshot_global: Any,
    shutdown_event: Any,
    verbose_flag: Any,
) -> tuple[dict[str, Any], Any]:
    runtime = {"config": load_config(config_path)}

    def handle_signal(signum: int) -> tuple[bool, str | None, dict[str, Any] | None]:
        if signum in (signal.SIGINT, signal.SIGTERM):
            shutdown_event.set()
            return True, f"Shutdown solicitado por {signal.Signals(signum).name}", None
        if signum == signal.SIGHUP:
            runtime["config"] = load_config(config_path)
            apply_intervals(interval_values, runtime["config"])
            return False, "Configuracion recargada desde config.json", runtime["config"]
        if signum == signal.SIGUSR1:
            dump_path = dump_snapshot(snapshot_global, config_path.parent)
            return False, f"Snapshot exportado a {dump_path.name}", None
        if signum == signal.SIGUSR2:
            with verbose_flag.get_lock():
                verbose_flag.value = 0 if verbose_flag.value else 1
            mode = "on" if verbose_flag.value else "off"
            return False, f"Verbose {mode}", None
        if hasattr(signal, "SIGWINCH") and signum == signal.SIGWINCH:
            return False, "Redimension detectada", None
        return False, None, None

    return runtime, handle_signal


def headless_loop(
    duration: float | None,
    shutdown_event: Any,
    signal_controller: Any,
    signal_handler: Any,
) -> None:
    deadline = time.monotonic() + duration if duration is not None else None
    while not shutdown_event.is_set():
        for signum in signal_controller.drain():
            should_exit, _message, _config = signal_handler(signum)
            if should_exit:
                return
        if deadline is not None and time.monotonic() >= deadline:
            return
        time.sleep(0.1)


def run_monitor(config_path: Path, use_ui: bool, duration: float | None) -> int:
    ctx = mp.get_context("spawn")
    signal_controller = install_signal_controller()
    try:
        with ctx.Manager() as manager:
            snapshot_global = manager.dict()
            initialize_snapshot(snapshot_global)
            shutdown_event = ctx.Event()
            result_queue = ctx.Queue()
            pid_queues = {view: ctx.Queue(maxsize=1) for view in VIEW_ORDER}
            interval_values = {view: ctx.Value("d", 0.0) for view in VIEW_ORDER}
            focus_pid_value = ctx.Value("i", 0)
            verbose_flag = ctx.Value("b", 0)
            runtime, signal_handler = make_signal_handler(
                config_path,
                interval_values,
                snapshot_global,
                shutdown_event,
                verbose_flag,
            )
            apply_intervals(interval_values, runtime["config"])
            processes = start_processes(
                ctx,
                snapshot_global,
                pid_queues,
                result_queue,
                interval_values,
                focus_pid_value,
                shutdown_event,
                verbose_flag,
            )
            try:
                if use_ui:
                    curses.wrapper(
                        run_display,
                        snapshot_global,
                        interval_values,
                        focus_pid_value,
                        shutdown_event,
                        signal_controller,
                        signal_handler,
                        runtime["config"],
                        verbose_flag,
                    )
                else:
                    headless_loop(duration, shutdown_event, signal_controller, signal_handler)
                return 0
            finally:
                stop_processes(processes, shutdown_event)
    finally:
        signal_controller.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor multiproceso de procesos y threads en macOS")
    parser.add_argument("--config", default="config.json", help="Ruta al archivo de configuracion JSON")
    parser.add_argument("--no-ui", action="store_true", help="Ejecuta la arquitectura sin curses")
    parser.add_argument("--duration", type=float, default=None, help="Duracion para modo headless")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = Path(args.config).resolve()
    return run_monitor(config_path, use_ui=not args.no_ui, duration=args.duration)


if __name__ == "__main__":
    raise SystemExit(main())
