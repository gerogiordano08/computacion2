from __future__ import annotations

import curses
import textwrap
import time
from typing import Any, Callable

from app_support import VIEW_KEYS, VIEW_ORDER, VIEW_TITLES, clamp_interval


SignalHandlerFn = Callable[[int], tuple[bool, str | None, dict[str, Any] | None]]


def format_bytes(value: int | None) -> str:
    if value is None:
        return "-"
    size = float(value)
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if abs(size) < 1024.0 or unit == units[-1]:
            return f"{size:.1f}{unit}" if unit != "B" else f"{int(size)}B"
        size /= 1024.0
    return f"{value}B"


def format_timestamp(timestamp: float | None) -> str:
    if not timestamp:
        return "never"
    return time.strftime("%H:%M:%S", time.localtime(timestamp))


def format_value(value: Any) -> str:
    return "N/D" if value is None else str(value)


def format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "N/D"
    days, rem = divmod(max(0, seconds), 86_400)
    hours, rem = divmod(rem, 3_600)
    minutes, _ = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def format_ns_duration(ns_value: int | None) -> str:
    if ns_value is None:
        return "N/D"
    seconds = max(0.0, float(ns_value) / 1_000_000_000.0)
    if seconds < 1.0:
        return f"{seconds * 1000.0:.1f}ms"
    if seconds < 60.0:
        return f"{seconds:.2f}s"
    minutes, rem = divmod(seconds, 60.0)
    return f"{int(minutes)}m{rem:.0f}s"


def format_state_counts(counts: dict[str, int] | None) -> str:
    if not counts:
        return "N/D"
    return " ".join(f"{key}={value}" for key, value in sorted(counts.items()))


def format_signal_list(values: list[str] | None, available: bool) -> str:
    if not available:
        return "N/D"
    if not values:
        return "ninguna"
    return ", ".join(values)


class MonitorDisplay:
    def __init__(
        self,
        stdscr: Any,
        snapshot_global: Any,
        interval_values: dict[str, Any],
        focus_pid_value: Any,
        shutdown_event: Any,
        signal_controller: Any,
        signal_handler: SignalHandlerFn,
        config: dict[str, Any],
        verbose_flag: Any,
    ) -> None:
        self.stdscr = stdscr
        self.snapshot_global = snapshot_global
        self.interval_values = interval_values
        self.focus_pid_value = focus_pid_value
        self.shutdown_event = shutdown_event
        self.signal_controller = signal_controller
        self.signal_handler = signal_handler
        self.verbose_flag = verbose_flag
        self.active_view = "resumen"
        self.selected_index = 0
        self.pinned_pid: int | None = None
        self.command_filter = config.get("filters", {}).get("command", "")
        self.user_filter = config.get("filters", {}).get("user", "")
        self.sort_key = config.get("display", {}).get("sort", "cpu")
        self.status_message = ""
        self.show_help = False
        self.detail_scroll = 0
        self.should_exit = False
        self._cached_snapshot = {key: self.snapshot_global.get(key) for key in VIEW_ORDER}
        self._next_snapshot_poll = 0.0

    def apply_config(self, config: dict[str, Any]) -> None:
        self.command_filter = config.get("filters", {}).get("command", self.command_filter)
        self.user_filter = config.get("filters", {}).get("user", self.user_filter)
        self.sort_key = config.get("display", {}).get("sort", self.sort_key)

    def loop(self) -> None:
        curses.curs_set(0)
        try:
            curses.mousemask(0)
            curses.mouseinterval(0)
        except curses.error:
            pass
        self.stdscr.nodelay(True)
        self.stdscr.keypad(True)
        while not self.shutdown_event.is_set() and not self.should_exit:
            self._process_signals()
            now = time.monotonic()
            if now >= self._next_snapshot_poll:
                self._cached_snapshot = {key: self.snapshot_global.get(key) for key in VIEW_ORDER}
                self._next_snapshot_poll = now + 0.2
            snapshot = self._cached_snapshot
            summary_rows = list(snapshot.get("resumen", {}).get("data", []) or [])
            rows = self._filtered_rows(summary_rows)
            self._normalize_selection(rows)
            self._sync_focus_pid(rows, summary_rows)
            self._draw(snapshot, rows, summary_rows)
            self._handle_input(rows)
            time.sleep(0.08)

    def _process_signals(self) -> None:
        for signum in self.signal_controller.drain():
            should_exit, message, config = self.signal_handler(signum)
            if config:
                self.apply_config(config)
            if message:
                self.status_message = message
            if should_exit:
                self.should_exit = True

    def _filtered_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        command_filter = self.command_filter.lower().strip()
        user_filter = self.user_filter.lower().strip()
        if not command_filter and not user_filter and self.sort_key == "cpu":
            filtered = list(rows)
        else:
            filtered = []
            for row in rows:
                command = (row.get("basename") or row.get("command") or "").lower()
                user = (row.get("user") or "").lower()
                if command_filter and command_filter not in command:
                    continue
                if user_filter and user_filter not in user:
                    continue
                filtered.append(row)
            if self.sort_key == "rss":
                filtered.sort(key=lambda item: (-item.get("rss", 0), -item.get("cpu", 0), item["pid"]))
            elif self.sort_key == "pid":
                filtered.sort(key=lambda item: item["pid"])
            else:
                filtered.sort(key=lambda item: (-item.get("cpu", 0.0), -item.get("rss", 0), item["pid"]))
        if self.pinned_pid is not None:
            for index, row in enumerate(filtered):
                if row["pid"] == self.pinned_pid:
                    if index != 0:
                        filtered.insert(0, filtered.pop(index))
                    break
        return filtered

    def _normalize_selection(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            self.selected_index = 0
            return
        self.selected_index = max(0, min(self.selected_index, len(rows) - 1))

    def _sync_focus_pid(self, visible_rows: list[dict[str, Any]], all_rows: list[dict[str, Any]]) -> None:
        focus_pid = 0
        all_pids = {row["pid"] for row in all_rows}
        if self.pinned_pid and self.pinned_pid in all_pids:
            focus_pid = self.pinned_pid
        elif visible_rows:
            focus_pid = visible_rows[self.selected_index]["pid"]
        with self.focus_pid_value.get_lock():
            self.focus_pid_value.value = focus_pid

    def _draw(self, snapshot: dict[str, Any], visible_rows: list[dict[str, Any]], all_rows: list[dict[str, Any]]) -> None:
        self.stdscr.erase()
        height, width = self.stdscr.getmaxyx()
        top_height = self._top_height(height)
        self._add_line(0, 0, self._header_text(snapshot), width, curses.A_BOLD)
        self._add_line(1, 0, "PID   PPID  UID:GID     USER         ST   CPU%   RSS       THR  COMMAND", width, curses.A_UNDERLINE)
        list_rows = max(1, top_height - 3)
        offset = 0
        if self.selected_index >= list_rows:
            offset = self.selected_index - list_rows + 1
        for idx, row in enumerate(visible_rows[offset : offset + list_rows], start=0):
            real_index = offset + idx
            marker = " "
            if self.pinned_pid == row["pid"]:
                marker = "*"
            elif real_index == self.selected_index:
                marker = ">"
            uid_gid = f"{row.get('uid', '-')}:{row.get('gid', '-')}"
            text = (
                f"{marker}{row['pid']:5d} {row['ppid']:5d} "
                f"{uid_gid:11} "
                f"{(row.get('user') or '-')[:12]:12} "
                f"{row.get('state','?'):>2} "
                f"{row.get('cpu',0.0):6.1f} "
                f"{format_bytes(row.get('rss')):>8} "
                f"{row.get('threads',0):4d} "
                f"{(row.get('basename') or row.get('command') or '-')}"
            )
            style = curses.A_REVERSE if real_index == self.selected_index else curses.A_NORMAL
            self._add_line(2 + idx, 0, text, width, style)
        divider_y = top_height
        self._add_line(divider_y, 0, "-" * max(1, width - 1), width)
        detail_lines = self._detail_lines(snapshot, visible_rows, all_rows)
        detail_height = max(1, height - divider_y - 2)
        max_scroll = max(0, len(detail_lines) - detail_height)
        self.detail_scroll = max(0, min(self.detail_scroll, max_scroll))
        detail_window = detail_lines[self.detail_scroll : self.detail_scroll + detail_height]
        for idx, line in enumerate(detail_window, start=0):
            self._add_line(divider_y + 1 + idx, 0, line, width)
        scroll_hint = ""
        if max_scroll:
            scroll_hint = f" | detalle {self.detail_scroll + 1}-{self.detail_scroll + len(detail_window)}/{len(detail_lines)} [] scroll"
        footer = self.status_message or "F1/h/? ayuda | q salir | enter pin | c orden | +/- intervalo"
        footer = f"{footer}{scroll_hint}"
        self._add_line(height - 1, 0, footer, width, curses.A_DIM)
        self.stdscr.refresh()

    def _top_height(self, total_height: int) -> int:
        if self.show_help:
            return max(7, min(10, total_height // 3))
        return max(8, total_height // 2)

    def _header_text(self, snapshot: dict[str, Any]) -> str:
        interval = self.interval_values[self.active_view].value
        updated = format_timestamp(snapshot.get(self.active_view, {}).get("updated_at"))
        pinned = self.pinned_pid if self.pinned_pid is not None else "-"
        verbose = "on" if self.verbose_flag.value else "off"
        return (
            f"{VIEW_TITLES[self.active_view]} | sort={self.sort_key} | "
            f"interval={interval:.1f}s | updated={updated} | pin={pinned} | verbose={verbose} | "
            f"cmd='{self.command_filter}' user='{self.user_filter}'"
        )

    def _detail_lines(
        self,
        snapshot: dict[str, Any],
        visible_rows: list[dict[str, Any]],
        all_rows: list[dict[str, Any]],
    ) -> list[str]:
        if self.show_help:
            return self._help_lines()
        focused_pid = int(self.focus_pid_value.value)
        summary_by_pid = {row["pid"]: row for row in all_rows}
        summary = summary_by_pid.get(focused_pid)
        lines = [f"Vista activa: {VIEW_TITLES[self.active_view]}"]
        active_error = snapshot.get(self.active_view, {}).get("error")
        if active_error:
            lines.append(f"error: {active_error}")
        if not summary and self.active_view != "sistema":
            lines.append("No hay proceso enfocado todavia.")
            return lines
        if self.active_view == "resumen":
            assert summary is not None
            args_text = " ".join(summary.get("args") or []) or "-"
            lines.extend(
                [
                    f"PID={summary['pid']} PPID={summary['ppid']} UID={summary['uid']} GID={summary['gid']} USER={summary['user']}",
                    f"STATE={summary.get('state', '?')}/{summary['state_name']} CPU={summary['cpu']:.1f}% RSS={format_bytes(summary['rss'])} THREADS={summary['threads']}",
                ]
            )
            lines.extend(self._wrapped_field_lines("PATH", summary.get("path") or "-"))
            lines.extend(self._wrapped_field_lines("ARGS", args_text))
            return lines
        if self.active_view == "memoria":
            info = snapshot["memoria"]["data"].get("info")
            if not info:
                lines.append("Sin datos de memoria para el proceso enfocado.")
                return lines
            lines.extend(
                [
                    f"PID={info['pid']} RSS={format_bytes(info['resident_size'])} VIRT={format_bytes(info['virtual_size'])} FOOTPRINT={format_bytes(info['phys_footprint'])}",
                    f"WIRED={format_bytes(info['wired_size'])} FAULTS={info['faults']} PAGEINS={info['pageins']}",
                    f"INTERNAL={format_bytes(info.get('internal'))} EXTERNAL={format_bytes(info.get('external'))} REUSABLE={format_bytes(info.get('reusable'))} COMPRESSED={format_bytes(info.get('compressed'))}",
                    f"REGION_COUNT={info.get('region_count', 0)} task_vm={info.get('task_vm_region_count', 0)} vmmap={info.get('vmmap_region_count', 0)}",
                    "Regiones vmmap:",
                ]
            )
            for region in info.get("regions", [])[:8]:
                lines.append(
                    f"  {region['region'][:20]:20} {region['start']}-{region['end']} [{region['size']}] {region['protection']}"
                )
            if not info.get("regions"):
                lines.append("  vmmap no devolvio regiones o no hubo permisos.")
            if not any(int(info.get(key) or 0) for key in ("internal", "external", "reusable", "compressed")):
                lines.append("  nota: memoria privada/compartida/comprimida no disponible via TASK_VM_INFO para este PID.")
            return lines
        if self.active_view == "fds":
            info = snapshot["fds"]["data"] or {}
            lines.append(f"PID={info.get('pid')} COUNT={info.get('count',0)} source={info.get('source', 'N/D')}")
            for entry in info.get("entries", [])[:10]:
                target = entry.get("target") or entry.get("name") or "-"
                lines.append(f"  fd={entry.get('fd')} type={entry.get('type','?')}")
                lines.extend(self._wrapped_field_lines("target", str(target)))
            if not info.get("entries"):
                lines.append("  Sin FDs visibles o lsof no tuvo permisos.")
            if info.get("source") == "libproc":
                lines.append("  nota: sockets y vnode paths se consultan con proc_pidfdinfo cuando macOS lo permite.")
            elif info.get("source") == "lsof":
                lines.append("  nota: usando lsof como fallback practico.")
            return lines
        if self.active_view == "threads":
            info = snapshot["threads"]["data"] or {}
            lines.append(
                f"PID={info.get('pid')} THREADS={info.get('thread_count',0)} RUNNING={info.get('running_threads',0)}"
            )
            for thread in info.get("threads", [])[:10]:
                name = thread.get("name") or "-"
                lines.append(
                    "  "
                    f"tid={thread['thread_id']} cpu={thread['cpu_percent']:.1f}% "
                    f"state={thread['run_state_name']} policy={thread.get('policy_name', thread['policy'])} pri={thread['priority']}"
                )
                lines.append(
                    "    "
                    f"utime={format_ns_duration(thread.get('user_time_ns'))} stime={format_ns_duration(thread.get('system_time_ns'))} "
                    f"name={name}"
                )
            if not info.get("threads"):
                lines.append("  Sin visibilidad de threads o sin permisos.")
            for note in info.get("notes", []):
                lines.extend(self._wrapped_note_lines(note))
            return lines
        if self.active_view == "senales":
            info = snapshot["senales"]["data"] or {}
            lines.extend(
                [
                    f"PID={info.get('pid')} blocked={format_signal_list(info.get('blocked'), bool(info.get('blocked_available')))}",
                    f"pending={format_signal_list(info.get('pending'), bool(info.get('pending_available')))}",
                    f"pending_group={format_signal_list(info.get('pending_group'), bool(info.get('pending_group_available')))}",
                    f"handlers={info.get('handlers','-')}",
                    f"source={info.get('source', 'N/D')}",
                ]
            )
            for note in info.get("notes", []):
                lines.extend(self._wrapped_note_lines(note))
            return lines
        if self.active_view == "scheduling":
            info = snapshot["scheduling"]["data"] or {}
            lines.extend(
                [
                    f"PID={format_value(info.get('pid'))} nice={format_value(info.get('nice'))} session={format_value(info.get('session_id'))} pgid={format_value(info.get('pgid'))}",
                    f"priority={format_value(info.get('priority'))} task_policy={info.get('task_policy_name') or format_value(info.get('task_policy'))} dominant_thread_policy={info.get('dominant_thread_policy_name') or format_value(info.get('dominant_thread_policy'))}",
                    f"ctx voluntary={format_value(info.get('voluntary_context_switches'))} involuntary={format_value(info.get('involuntary_context_switches'))} total={format_value(info.get('context_switches_total'))}",
                    f"syscalls_unix={format_value(info.get('syscalls_unix'))} syscalls_mach={format_value(info.get('syscalls_mach'))}",
                    f"utime={info.get('utime_ns')}ns stime={info.get('stime_ns')}ns qos={info.get('qos') or '-'}",
                    f"affinity={info.get('affinity')}",
                ]
            )
            for note in info.get("notes", []):
                lines.extend(self._wrapped_note_lines(note))
            return lines
        system_data = snapshot["sistema"]["data"] or {}
        cpu = system_data.get("cpu", {})
        memory = system_data.get("memory", {})
        top_cpu = system_data.get("top_cpu", [])[:3]
        top_memory = system_data.get("top_memory", [])[:3]
        swap = system_data.get("swap", {})
        process_counts = system_data.get("process_counts", {})
        lines.extend(
            [
                f"CPU user={cpu.get('user','-')}% system={cpu.get('system','-')}% idle={cpu.get('idle','-')}%",
                f"Load 1/5/15={system_data.get('loadavg',{}).get('1m')}/{system_data.get('loadavg',{}).get('5m')}/{system_data.get('loadavg',{}).get('15m')}  Cores={system_data.get('cores',{}).get('ncpu')}",
                f"Memory total={format_bytes(memory.get('total'))}",
                f"Memory free={format_bytes(memory.get('free'))} wired={format_bytes(memory.get('wired'))} active={format_bytes(memory.get('active'))} inactive={format_bytes(memory.get('inactive'))} compressed={format_bytes(memory.get('compressor'))}",
                f"Swap total={swap.get('total') or 'N/D'} used={swap.get('used') or 'N/D'} free={swap.get('free') or 'N/D'}",
                f"Processes total={process_counts.get('total', 'N/D')} by_state={format_state_counts(process_counts.get('by_state'))}",
                f"Boot time={format_timestamp(system_data.get('boot_time'))}  uptime={format_duration(system_data.get('uptime_seconds'))}",
                f"Top CPU: {self._compact_top_rows(top_cpu, 'cpu')}",
                f"Top Mem: {self._compact_top_rows(top_memory, 'rss')}",
            ]
        )
        return lines

    def _help_lines(self) -> list[str]:
        return [
            "Ayuda",
            "",
            "1-7 o r/m/f/t/s/p/g: cambiar de vista",
            "Flechas: mover seleccion",
            "[]: scroll del detalle | {}: pagina del detalle",
            "Enter: pin/unpin del PID seleccionado",
            "/: filtro por comando | u: filtro por usuario",
            "c: ordenar CPU/RSS/PID | +/-: cambiar intervalo",
            "F1, h o ?: abrir/cerrar ayuda",
            "q: salir limpio",
            "",
            "Notas:",
            "- La tabla superior siempre usa la vista Resumen.",
            "- Las vistas Memoria, FDs, Threads, Senales y Scheduling muestran detalle del PID seleccionado.",
            "- Si pineas un proceso con Enter, el detalle sigue ese PID aunque cambie el orden.",
        ]

    def _wrapped_note_lines(self, note: str, width: int = 92) -> list[str]:
        wrapped = textwrap.wrap(note, width=max(20, width - 8)) or [""]
        lines = [f"  nota: {wrapped[0]}"]
        lines.extend(f"        {part}" for part in wrapped[1:])
        return lines

    def _wrapped_field_lines(self, label: str, value: str, width: int = 92) -> list[str]:
        prefix = f"    {label}="
        wrapped = textwrap.wrap(value, width=max(20, width - len(prefix))) or ["-"]
        lines = [f"{prefix}{wrapped[0]}"]
        lines.extend(f"{' ' * len(prefix)}{part}" for part in wrapped[1:])
        return lines

    def _compact_top_rows(self, rows: list[dict[str, Any]], metric: str) -> str:
        if not rows:
            return "N/D"
        parts = []
        for idx, row in enumerate(rows[:3], start=1):
            if metric == "rss":
                value = format_bytes(row.get("rss"))
            else:
                value = f"{row.get('cpu', 0.0):.1f}%"
            parts.append(f"{idx}) pid={row.get('pid')} {value}")
        return " | ".join(parts)

    def _handle_input(self, rows: list[dict[str, Any]]) -> None:
        key = self.stdscr.getch()
        if key == -1:
            return
        if key in (curses.KEY_MOUSE, curses.KEY_RESIZE):
            if key == curses.KEY_RESIZE:
                self._next_snapshot_poll = 0.0
            return
        if key in (ord("q"), ord("Q")):
            self.shutdown_event.set()
            self.should_exit = True
            return
        if key in (ord("h"), ord("H"), ord("?"), curses.KEY_F1):
            self.show_help = not self.show_help
            return
        if self.show_help:
            if key in (ord("e"), ord("E"), ord("l"), ord("L"), ord("p"), ord("P")):
                return
            self.show_help = False
            return
        if key == curses.KEY_UP and rows:
            self.selected_index = max(0, self.selected_index - 1)
            self.detail_scroll = 0
            return
        if key == curses.KEY_DOWN and rows:
            self.selected_index = min(len(rows) - 1, self.selected_index + 1)
            self.detail_scroll = 0
            return
        if key == ord("["):
            self.detail_scroll = max(0, self.detail_scroll - 1)
            return
        if key == ord("]"):
            self.detail_scroll += 1
            return
        if key == ord("{"):
            self.detail_scroll = max(0, self.detail_scroll - 8)
            return
        if key == ord("}"):
            self.detail_scroll += 8
            return
        if key in (10, 13) and rows:
            pid = rows[self.selected_index]["pid"]
            self.pinned_pid = None if self.pinned_pid == pid else pid
            if self.pinned_pid is not None:
                self.selected_index = 0
            self.detail_scroll = 0
            return
        if key == ord("c"):
            self.sort_key = {"cpu": "rss", "rss": "pid", "pid": "cpu"}[self.sort_key]
            self.status_message = f"Orden actual: {self.sort_key}"
            self.detail_scroll = 0
            return
        if key in (ord("+"), ord("=")):
            self._change_interval(+0.5)
            return
        if key == ord("-"):
            self._change_interval(-0.5)
            return
        if key == ord("/"):
            self.command_filter = self._prompt("Filtro comando: ", self.command_filter)
            self.detail_scroll = 0
            return
        if key == ord("u"):
            self.user_filter = self._prompt("Filtro usuario: ", self.user_filter)
            self.detail_scroll = 0
            return
        try:
            char = chr(key).lower()
        except ValueError:
            return
        if char in VIEW_KEYS:
            self.active_view = VIEW_KEYS[char]
            self.detail_scroll = 0
            self.status_message = f"Vista activa: {VIEW_TITLES[self.active_view]}"

    def _change_interval(self, delta: float) -> None:
        value_proxy = self.interval_values[self.active_view]
        with value_proxy.get_lock():
            value_proxy.value = clamp_interval(self.active_view, float(value_proxy.value) + delta)
            self.status_message = f"Intervalo de {self.active_view}: {value_proxy.value:.1f}s"

    def _prompt(self, label: str, default: str) -> str:
        curses.echo()
        try:
            curses.curs_set(1)
        except curses.error:
            pass
        height, width = self.stdscr.getmaxyx()
        self.stdscr.nodelay(False)
        self._add_line(height - 1, 0, " " * max(1, width - 1), width)
        self._add_line(height - 1, 0, label, width)
        self.stdscr.refresh()
        try:
            value = self.stdscr.getstr(height - 1, len(label), max(1, width - len(label) - 2))
            text = value.decode("utf-8", "ignore").strip()
            return text
        finally:
            self.stdscr.nodelay(True)
            curses.noecho()
            try:
                curses.curs_set(0)
            except curses.error:
                pass

    def _add_line(self, y: int, x: int, text: str, width: int, style: int = 0) -> None:
        try:
            self.stdscr.addnstr(y, x, text, max(1, width - x - 1), style)
        except curses.error:
            pass


def run_display(
    stdscr: Any,
    snapshot_global: Any,
    interval_values: dict[str, Any],
    focus_pid_value: Any,
    shutdown_event: Any,
    signal_controller: Any,
    signal_handler: SignalHandlerFn,
    config: dict[str, Any],
    verbose_flag: Any,
) -> None:
    display = MonitorDisplay(
        stdscr,
        snapshot_global,
        interval_values,
        focus_pid_value,
        shutdown_event,
        signal_controller,
        signal_handler,
        config,
        verbose_flag,
    )
    display.loop()
