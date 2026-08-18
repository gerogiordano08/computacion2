from __future__ import annotations

import ctypes
import ctypes.util
import errno
import os
import pwd
import re
import resource
import signal
import socket
import subprocess
import time
from typing import Any


LIBPROC = ctypes.CDLL(ctypes.util.find_library("proc") or "libproc.dylib", use_errno=True)
LIBC = ctypes.CDLL(ctypes.util.find_library("c") or "libc.dylib", use_errno=True)

PROC_ALL_PIDS = 1
PROC_PIDLISTFDS = 1
PROC_PIDTASKALLINFO = 2
PROC_PIDTBSDINFO = 3
PROC_PIDTASKINFO = 4
PROC_PIDTHREADINFO = 5
PROC_PIDLISTTHREADS = 6
PROC_PIDVNODEPATHINFO = 9
RUSAGE_INFO_V4 = 4
TH_USAGE_SCALE = 1000
HOST_CPU_LOAD_INFO = 3
HOST_VM_INFO64 = 4
HOST_CPU_LOAD_INFO_COUNT = 4
TASK_VM_INFO = 22
THREAD_BASIC_INFO = 3
THREAD_EXTENDED_POLICY = 1
THREAD_PRECEDENCE_POLICY = 3
PROC_PIDFDVNODEPATHINFO = 2
PROC_PIDFDSOCKETINFO = 3
CTL_KERN = 1
KERN_PROCARGS2 = 49


class ProcBsdInfo(ctypes.Structure):
    _fields_ = [
        ("pbi_flags", ctypes.c_uint32),
        ("pbi_status", ctypes.c_uint32),
        ("pbi_xstatus", ctypes.c_uint32),
        ("pbi_pid", ctypes.c_uint32),
        ("pbi_ppid", ctypes.c_uint32),
        ("pbi_uid", ctypes.c_uint32),
        ("pbi_gid", ctypes.c_uint32),
        ("pbi_ruid", ctypes.c_uint32),
        ("pbi_rgid", ctypes.c_uint32),
        ("pbi_svuid", ctypes.c_uint32),
        ("pbi_svgid", ctypes.c_uint32),
        ("rfu_1", ctypes.c_uint32),
        ("pbi_comm", ctypes.c_char * 16),
        ("pbi_name", ctypes.c_char * 32),
        ("pbi_nfiles", ctypes.c_uint32),
        ("pbi_pgid", ctypes.c_uint32),
        ("pbi_pjobc", ctypes.c_uint32),
        ("e_tdev", ctypes.c_uint32),
        ("e_tpgid", ctypes.c_uint32),
        ("pbi_nice", ctypes.c_int32),
        ("pbi_start_tvsec", ctypes.c_uint64),
        ("pbi_start_tvusec", ctypes.c_uint64),
    ]


class ProcTaskInfo(ctypes.Structure):
    _fields_ = [
        ("pti_virtual_size", ctypes.c_uint64),
        ("pti_resident_size", ctypes.c_uint64),
        ("pti_total_user", ctypes.c_uint64),
        ("pti_total_system", ctypes.c_uint64),
        ("pti_threads_user", ctypes.c_uint64),
        ("pti_threads_system", ctypes.c_uint64),
        ("pti_policy", ctypes.c_int32),
        ("pti_faults", ctypes.c_int32),
        ("pti_pageins", ctypes.c_int32),
        ("pti_cow_faults", ctypes.c_int32),
        ("pti_messages_sent", ctypes.c_int32),
        ("pti_messages_received", ctypes.c_int32),
        ("pti_syscalls_mach", ctypes.c_int32),
        ("pti_syscalls_unix", ctypes.c_int32),
        ("pti_csw", ctypes.c_int32),
        ("pti_threadnum", ctypes.c_int32),
        ("pti_numrunning", ctypes.c_int32),
        ("pti_priority", ctypes.c_int32),
    ]


class ProcThreadInfo(ctypes.Structure):
    _fields_ = [
        ("pth_user_time", ctypes.c_uint64),
        ("pth_system_time", ctypes.c_uint64),
        ("pth_cpu_usage", ctypes.c_int32),
        ("pth_policy", ctypes.c_int32),
        ("pth_run_state", ctypes.c_int32),
        ("pth_flags", ctypes.c_int32),
        ("pth_sleep_time", ctypes.c_int32),
        ("pth_curpri", ctypes.c_int32),
        ("pth_priority", ctypes.c_int32),
        ("pth_maxpriority", ctypes.c_int32),
        ("pth_name", ctypes.c_char * 64),
    ]


class TimeValue(ctypes.Structure):
    _fields_ = [
        ("seconds", ctypes.c_int32),
        ("microseconds", ctypes.c_int32),
    ]


class ThreadBasicInfo(ctypes.Structure):
    _fields_ = [
        ("user_time", TimeValue),
        ("system_time", TimeValue),
        ("cpu_usage", ctypes.c_int32),
        ("policy", ctypes.c_int32),
        ("run_state", ctypes.c_int32),
        ("flags", ctypes.c_int32),
        ("suspend_count", ctypes.c_int32),
        ("sleep_time", ctypes.c_int32),
    ]


class ThreadExtendedPolicy(ctypes.Structure):
    _fields_ = [("timeshare", ctypes.c_int32)]


class ThreadPrecedencePolicy(ctypes.Structure):
    _fields_ = [("importance", ctypes.c_int32)]


class RusageInfoV4(ctypes.Structure):
    _fields_ = [
        ("ri_uuid", ctypes.c_uint8 * 16),
        ("ri_user_time", ctypes.c_uint64),
        ("ri_system_time", ctypes.c_uint64),
        ("ri_pkg_idle_wkups", ctypes.c_uint64),
        ("ri_interrupt_wkups", ctypes.c_uint64),
        ("ri_pageins", ctypes.c_uint64),
        ("ri_wired_size", ctypes.c_uint64),
        ("ri_resident_size", ctypes.c_uint64),
        ("ri_phys_footprint", ctypes.c_uint64),
        ("ri_proc_start_abstime", ctypes.c_uint64),
        ("ri_proc_exit_abstime", ctypes.c_uint64),
        ("ri_child_user_time", ctypes.c_uint64),
        ("ri_child_system_time", ctypes.c_uint64),
        ("ri_child_pkg_idle_wkups", ctypes.c_uint64),
        ("ri_child_interrupt_wkups", ctypes.c_uint64),
        ("ri_child_pageins", ctypes.c_uint64),
        ("ri_child_elapsed_abstime", ctypes.c_uint64),
        ("ri_diskio_bytesread", ctypes.c_uint64),
        ("ri_diskio_byteswritten", ctypes.c_uint64),
        ("ri_cpu_time_qos_default", ctypes.c_uint64),
        ("ri_cpu_time_qos_maintenance", ctypes.c_uint64),
        ("ri_cpu_time_qos_background", ctypes.c_uint64),
        ("ri_cpu_time_qos_utility", ctypes.c_uint64),
        ("ri_cpu_time_qos_legacy", ctypes.c_uint64),
        ("ri_cpu_time_qos_user_initiated", ctypes.c_uint64),
        ("ri_cpu_time_qos_user_interactive", ctypes.c_uint64),
        ("ri_billed_system_time", ctypes.c_uint64),
        ("ri_serviced_system_time", ctypes.c_uint64),
        ("ri_logical_writes", ctypes.c_uint64),
        ("ri_lifetime_max_phys_footprint", ctypes.c_uint64),
        ("ri_instructions", ctypes.c_uint64),
        ("ri_cycles", ctypes.c_uint64),
        ("ri_billed_energy", ctypes.c_uint64),
        ("ri_serviced_energy", ctypes.c_uint64),
        ("ri_interval_max_phys_footprint", ctypes.c_uint64),
        ("ri_runnable_time", ctypes.c_uint64),
    ]


class TaskVMInfo(ctypes.Structure):
    _fields_ = [
        ("virtual_size", ctypes.c_uint64),
        ("region_count", ctypes.c_int32),
        ("page_size", ctypes.c_int32),
        ("resident_size", ctypes.c_uint64),
        ("resident_size_peak", ctypes.c_uint64),
        ("device", ctypes.c_uint64),
        ("device_peak", ctypes.c_uint64),
        ("internal", ctypes.c_uint64),
        ("internal_peak", ctypes.c_uint64),
        ("external", ctypes.c_uint64),
        ("external_peak", ctypes.c_uint64),
        ("reusable", ctypes.c_uint64),
        ("reusable_peak", ctypes.c_uint64),
        ("purgeable_volatile_pmap", ctypes.c_uint64),
        ("purgeable_volatile_resident", ctypes.c_uint64),
        ("purgeable_volatile_virtual", ctypes.c_uint64),
        ("compressed", ctypes.c_uint64),
        ("compressed_peak", ctypes.c_uint64),
        ("compressed_lifetime", ctypes.c_uint64),
        ("phys_footprint", ctypes.c_uint64),
        ("min_address", ctypes.c_uint64),
        ("max_address", ctypes.c_uint64),
        ("_rest", ctypes.c_int64 * 27),
        ("limit_bytes_remaining", ctypes.c_uint64),
        ("decompressions", ctypes.c_int32),
        ("_pad", ctypes.c_int32),
        ("ledger_swapins", ctypes.c_int64),
        ("ledger_tag_neural_nofootprint_total", ctypes.c_int64),
        ("ledger_tag_neural_nofootprint_peak", ctypes.c_int64),
    ]


class ProcFDInfo(ctypes.Structure):
    _fields_ = [
        ("proc_fd", ctypes.c_int32),
        ("proc_fdtype", ctypes.c_uint32),
    ]


class ProcFileInfo(ctypes.Structure):
    _fields_ = [
        ("fi_openflags", ctypes.c_uint32),
        ("fi_status", ctypes.c_uint32),
        ("fi_offset", ctypes.c_int64),
        ("fi_type", ctypes.c_int32),
        ("fi_guardflags", ctypes.c_uint32),
    ]


class VInfoStat(ctypes.Structure):
    _fields_ = [
        ("vst_dev", ctypes.c_uint32),
        ("vst_mode", ctypes.c_uint16),
        ("vst_nlink", ctypes.c_uint16),
        ("vst_ino", ctypes.c_uint64),
        ("vst_uid", ctypes.c_uint32),
        ("vst_gid", ctypes.c_uint32),
        ("vst_atime", ctypes.c_int64),
        ("vst_atimensec", ctypes.c_int64),
        ("vst_mtime", ctypes.c_int64),
        ("vst_mtimensec", ctypes.c_int64),
        ("vst_ctime", ctypes.c_int64),
        ("vst_ctimensec", ctypes.c_int64),
        ("vst_birthtime", ctypes.c_int64),
        ("vst_birthtimensec", ctypes.c_int64),
        ("vst_size", ctypes.c_int64),
        ("vst_blocks", ctypes.c_int64),
        ("vst_blksize", ctypes.c_int32),
        ("vst_flags", ctypes.c_uint32),
        ("vst_gen", ctypes.c_uint32),
        ("vst_rdev", ctypes.c_uint32),
        ("vst_qspare", ctypes.c_int64 * 2),
    ]


class Fsid(ctypes.Structure):
    _fields_ = [("val", ctypes.c_int32 * 2)]


class VnodeInfo(ctypes.Structure):
    _fields_ = [
        ("vi_stat", VInfoStat),
        ("vi_type", ctypes.c_int32),
        ("vi_pad", ctypes.c_int32),
        ("vi_fsid", Fsid),
    ]


class VnodeInfoPath(ctypes.Structure):
    _fields_ = [
        ("vip_vi", VnodeInfo),
        ("vip_path", ctypes.c_char * 1024),
    ]


class VnodeFDInfoWithPath(ctypes.Structure):
    _fields_ = [
        ("pfi", ProcFileInfo),
        ("pvip", VnodeInfoPath),
    ]


class In4In6Addr(ctypes.Structure):
    _fields_ = [
        ("i46a_pad32", ctypes.c_uint32 * 3),
        ("i46a_addr4", ctypes.c_uint8 * 4),
    ]


class InSockInfo(ctypes.Structure):
    _fields_ = [
        ("insi_fport", ctypes.c_int32),
        ("insi_lport", ctypes.c_int32),
        ("insi_gencnt", ctypes.c_uint64),
        ("insi_flags", ctypes.c_uint32),
        ("insi_flow", ctypes.c_uint32),
        ("insi_vflag", ctypes.c_uint8),
        ("insi_ip_ttl", ctypes.c_uint8),
        ("_pad", ctypes.c_uint16),
        ("_rfu_1", ctypes.c_uint32),
        ("insi_faddr", In4In6Addr),
        ("insi_laddr", In4In6Addr),
        ("_rest", ctypes.c_uint8 * 40),
    ]


class SockBufInfo(ctypes.Structure):
    _fields_ = [
        ("sbi_cc", ctypes.c_uint32),
        ("sbi_hiwat", ctypes.c_uint32),
        ("sbi_mbcnt", ctypes.c_uint32),
        ("sbi_mbmax", ctypes.c_uint32),
        ("sbi_lowat", ctypes.c_uint32),
        ("sbi_flags", ctypes.c_int16),
        ("sbi_timeo", ctypes.c_int16),
    ]


class SocketInfo(ctypes.Structure):
    _fields_ = [
        ("_soi_stat", VInfoStat),
        ("soi_so", ctypes.c_uint64),
        ("soi_pcb", ctypes.c_uint64),
        ("soi_type", ctypes.c_int32),
        ("soi_protocol", ctypes.c_int32),
        ("soi_family", ctypes.c_int32),
        ("soi_options", ctypes.c_int16),
        ("soi_linger", ctypes.c_int16),
        ("soi_state", ctypes.c_int16),
        ("soi_qlen", ctypes.c_int16),
        ("soi_incqlen", ctypes.c_int16),
        ("soi_qlimit", ctypes.c_int16),
        ("soi_timeo", ctypes.c_int16),
        ("soi_error", ctypes.c_uint16),
        ("soi_oobmark", ctypes.c_uint32),
        ("soi_rcv", SockBufInfo),
        ("soi_snd", SockBufInfo),
        ("soi_kind", ctypes.c_int32),
        ("_rfu_1", ctypes.c_uint32),
        ("soi_proto", InSockInfo),
    ]


class SocketFDInfo(ctypes.Structure):
    _fields_ = [
        ("pfi", ProcFileInfo),
        ("psi", SocketInfo),
    ]


class HostCpuLoadInfo(ctypes.Structure):
    _fields_ = [("cpu_ticks", ctypes.c_uint32 * 4)]


class VMStatistics64(ctypes.Structure):
    _fields_ = [
        ("free_count", ctypes.c_uint32),
        ("active_count", ctypes.c_uint32),
        ("inactive_count", ctypes.c_uint32),
        ("wire_count", ctypes.c_uint32),
        ("zero_fill_count", ctypes.c_uint64),
        ("reactivations", ctypes.c_uint64),
        ("pageins", ctypes.c_uint64),
        ("pageouts", ctypes.c_uint64),
        ("faults", ctypes.c_uint64),
        ("cow_faults", ctypes.c_uint64),
        ("lookups", ctypes.c_uint64),
        ("hits", ctypes.c_uint64),
        ("purges", ctypes.c_uint64),
        ("purgeable_count", ctypes.c_uint32),
        ("speculative_count", ctypes.c_uint32),
        ("decompressions", ctypes.c_uint64),
        ("compressions", ctypes.c_uint64),
        ("swapins", ctypes.c_uint64),
        ("swapouts", ctypes.c_uint64),
        ("compressor_page_count", ctypes.c_uint32),
        ("throttled_count", ctypes.c_uint32),
        ("external_page_count", ctypes.c_uint32),
        ("internal_page_count", ctypes.c_uint32),
        ("total_uncompressed_pages_in_compressor", ctypes.c_uint64),
        ("swapped_count", ctypes.c_uint64),
        ("total_tag_storage_pages", ctypes.c_uint64),
        ("nontag_pageable_tag_storage_pages", ctypes.c_uint64),
        ("nontag_wired_tag_storage_pages", ctypes.c_uint64),
        ("free_tag_storage_pages", ctypes.c_uint64),
        ("tag_storing_tag_storage_pages", ctypes.c_uint64),
        ("total_tagged_pages", ctypes.c_uint64),
        ("resident_tagged_pages", ctypes.c_uint64),
        ("compressed_tagged_pages", ctypes.c_uint64),
        ("tagged_compressions", ctypes.c_uint64),
        ("tagged_decompressions", ctypes.c_uint64),
        ("compressed_tag_storage_bytes", ctypes.c_uint64),
    ]


LIBPROC.proc_listpids.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_int]
LIBPROC.proc_listpids.restype = ctypes.c_int
LIBPROC.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
LIBPROC.proc_pidinfo.restype = ctypes.c_int
LIBPROC.proc_pidfdinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
LIBPROC.proc_pidfdinfo.restype = ctypes.c_int
LIBPROC.proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
LIBPROC.proc_pidpath.restype = ctypes.c_int
LIBPROC.proc_pid_rusage.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
LIBPROC.proc_pid_rusage.restype = ctypes.c_int
LIBC.getloadavg.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.c_int]
LIBC.getloadavg.restype = ctypes.c_int
LIBC.mach_host_self.restype = ctypes.c_uint
LIBC.host_statistics.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
LIBC.host_statistics.restype = ctypes.c_int
LIBC.host_statistics64.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
LIBC.host_statistics64.restype = ctypes.c_int
LIBC.task_info.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
LIBC.task_info.restype = ctypes.c_int
LIBC.task_threads.argtypes = [ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_uint)]
LIBC.task_threads.restype = ctypes.c_int
LIBC.thread_info.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
LIBC.thread_info.restype = ctypes.c_int
LIBC.thread_policy_get.argtypes = [
    ctypes.c_uint,
    ctypes.c_int,
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_uint),
    ctypes.POINTER(ctypes.c_int),
]
LIBC.thread_policy_get.restype = ctypes.c_int
LIBC.mach_task_self.restype = ctypes.c_uint
LIBC.task_for_pid.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.POINTER(ctypes.c_uint)]
LIBC.task_for_pid.restype = ctypes.c_int
LIBC.vm_deallocate.argtypes = [ctypes.c_uint, ctypes.c_uint64, ctypes.c_uint64]
LIBC.vm_deallocate.restype = ctypes.c_int
LIBC.sysctlbyname.argtypes = [
    ctypes.c_char_p,
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_size_t),
    ctypes.c_void_p,
    ctypes.c_size_t,
]
LIBC.sysctlbyname.restype = ctypes.c_int
LIBC.sysctl.argtypes = [
    ctypes.POINTER(ctypes.c_int),
    ctypes.c_uint,
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_size_t),
    ctypes.c_void_p,
    ctypes.c_size_t,
]
LIBC.sysctl.restype = ctypes.c_int
LIBC.getpriority.argtypes = [ctypes.c_int, ctypes.c_uint]
LIBC.getpriority.restype = ctypes.c_int

_USERNAME_CACHE: dict[int, str] = {}


def _decode_c_string(value: bytes | ctypes.Array[Any]) -> str:
    raw = bytes(value)
    return raw.split(b"\x00", 1)[0].decode("utf-8", "ignore")


def _command_output(command: list[str], timeout: float = 2.0) -> tuple[str | None, str | None]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, str(exc)
    if completed.returncode != 0 and not completed.stdout:
        return None, completed.stderr.strip() or f"exit {completed.returncode}"
    return completed.stdout, None


def _sysctl_raw(name: str) -> bytes:
    encoded = name.encode("utf-8")
    size = ctypes.c_size_t(0)
    if LIBC.sysctlbyname(encoded, None, ctypes.byref(size), None, 0) != 0:
        raise OSError(ctypes.get_errno(), os.strerror(ctypes.get_errno()))
    buffer = (ctypes.c_ubyte * size.value)()
    if LIBC.sysctlbyname(encoded, buffer, ctypes.byref(size), None, 0) != 0:
        raise OSError(ctypes.get_errno(), os.strerror(ctypes.get_errno()))
    return bytes(buffer[: size.value])


def sysctl_uint(name: str) -> int | None:
    try:
        raw = _sysctl_raw(name)
    except OSError:
        return None
    if not raw:
        return None
    return int.from_bytes(raw, "little", signed=False)


def sysctl_text(name: str) -> str | None:
    try:
        raw = _sysctl_raw(name)
    except OSError:
        return None
    return raw.rstrip(b"\x00").decode("utf-8", "ignore")


def boot_time_seconds() -> int | None:
    try:
        raw = _sysctl_raw("kern.boottime")
    except OSError:
        return None
    if len(raw) < 8:
        return None
    return int.from_bytes(raw[:8], "little", signed=True)


def username_for_uid(uid: int) -> str:
    cached = _USERNAME_CACHE.get(uid)
    if cached is not None:
        return cached
    try:
        name = pwd.getpwuid(uid).pw_name
    except KeyError:
        name = str(uid)
    _USERNAME_CACHE[uid] = name
    return name


def status_to_name(status: int) -> str:
    return {
        1: "SIDL",
        2: "SRUN",
        3: "SSLEEP",
        4: "SSTOP",
        5: "SZOMB",
        6: "SWAIT",
        7: "SLOCK",
    }.get(status, f"UNKNOWN({status})")


def status_to_code(status: int) -> str:
    return {
        1: "I",
        2: "R",
        3: "S",
        4: "T",
        5: "Z",
        6: "W",
        7: "L",
    }.get(status, "?")


def process_state_from_ps_stat(stat: str) -> tuple[str, str] | None:
    """Convert the primary BSD ``ps stat`` character into the Darwin labels.

    ``proc_pidinfo(..., PROC_PIDTBSDINFO, ...)`` is still used for the BSD
    identity fields, but on current macOS releases its pbi_status value is not
    reliable for every process visible to an unprivileged caller.  ``ps``
    exposes the kernel's public, user-facing state, so it is the authoritative
    source for the state shown by the monitor.
    """
    primary = stat.strip()[:1].upper()
    return {
        "I": ("I", "SIDL"),
        "R": ("R", "SRUN"),
        "S": ("S", "SSLEEP"),
        "T": ("T", "SSTOP"),
        "Z": ("Z", "SZOMB"),
        "U": ("W", "SWAIT"),
        "D": ("L", "SLOCK"),
    }.get(primary)


def get_process_states_via_ps() -> dict[int, tuple[str, str]]:
    """Return visible process states with one bounded ``ps`` invocation."""
    stdout, _error = _command_output(["/bin/ps", "-axo", "pid=,stat="], timeout=1.5)
    if not stdout:
        return {}
    states: dict[int, tuple[str, str]] = {}
    for line in stdout.splitlines():
        fields = line.split()
        if len(fields) < 2:
            continue
        try:
            pid = int(fields[0])
        except ValueError:
            continue
        state = process_state_from_ps_stat(fields[1])
        if state:
            states[pid] = state
    return states


def thread_state_to_name(run_state: int) -> str:
    return {
        1: "RUNNING",
        2: "STOPPED",
        3: "WAITING",
        4: "UNINTERRUPTIBLE",
        5: "HALTED",
    }.get(run_state, f"UNKNOWN({run_state})")


def policy_to_name(policy: int | None) -> str | None:
    if policy is None:
        return None
    return {
        1: "POLICY_TIMESHARE",
        2: "POLICY_RR",
        4: "POLICY_FIFO",
    }.get(policy, f"POLICY_{policy}")


def dominant_qos_label(rusage: dict[str, Any] | None) -> str | None:
    if not rusage:
        return None
    buckets = {
        "default": rusage.get("ri_cpu_time_qos_default", 0),
        "maintenance": rusage.get("ri_cpu_time_qos_maintenance", 0),
        "background": rusage.get("ri_cpu_time_qos_background", 0),
        "utility": rusage.get("ri_cpu_time_qos_utility", 0),
        "legacy": rusage.get("ri_cpu_time_qos_legacy", 0),
        "user_initiated": rusage.get("ri_cpu_time_qos_user_initiated", 0),
        "user_interactive": rusage.get("ri_cpu_time_qos_user_interactive", 0),
    }
    label, value = max(buckets.items(), key=lambda item: item[1])
    return label if value else None


def calculate_cpu_percent(
    previous_total_ns: int | None,
    previous_monotonic: float | None,
    current_total_ns: int,
    current_monotonic: float,
) -> float:
    if previous_total_ns is None or previous_monotonic is None:
        return 0.0
    delta_cpu = current_total_ns - previous_total_ns
    delta_wall = current_monotonic - previous_monotonic
    if delta_cpu < 0 or delta_wall <= 0:
        return 0.0
    return max(0.0, (delta_cpu / (delta_wall * 1_000_000_000.0)) * 100.0)


def list_pids() -> list[int]:
    size = LIBPROC.proc_listpids(PROC_ALL_PIDS, 0, None, 0)
    if size <= 0:
        return []
    count = size // ctypes.sizeof(ctypes.c_int)
    buffer = (ctypes.c_int * count)()
    written = LIBPROC.proc_listpids(PROC_ALL_PIDS, 0, buffer, size)
    if written <= 0:
        return []
    valid = written // ctypes.sizeof(ctypes.c_int)
    return [int(pid) for pid in buffer[:valid] if pid > 0]


def get_process_bsd_info(pid: int) -> dict[str, Any] | None:
    info = ProcBsdInfo()
    expected = ctypes.sizeof(info)
    written = LIBPROC.proc_pidinfo(pid, PROC_PIDTBSDINFO, 0, ctypes.byref(info), expected)
    if written != expected:
        return None
    return {
        "pid": int(info.pbi_pid),
        "ppid": int(info.pbi_ppid),
        "uid": int(info.pbi_uid),
        "gid": int(info.pbi_gid),
        "ruid": int(info.pbi_ruid),
        "rgid": int(info.pbi_rgid),
        "svuid": int(info.pbi_svuid),
        "svgid": int(info.pbi_svgid),
        "status": int(info.pbi_status),
        "status_name": status_to_name(int(info.pbi_status)),
        "state_code": status_to_code(int(info.pbi_status)),
        "flags": int(info.pbi_flags),
        "command": _decode_c_string(info.pbi_comm),
        "registered_name": _decode_c_string(info.pbi_name),
        "nfiles": int(info.pbi_nfiles),
        "pgid": int(info.pbi_pgid),
        "nice": int(info.pbi_nice),
        "start_time": float(info.pbi_start_tvsec) + (float(info.pbi_start_tvusec) / 1_000_000.0),
    }


def get_process_task_info(pid: int) -> dict[str, Any] | None:
    info = ProcTaskInfo()
    expected = ctypes.sizeof(info)
    written = LIBPROC.proc_pidinfo(pid, PROC_PIDTASKINFO, 0, ctypes.byref(info), expected)
    if written != expected:
        return None
    return {
        "virtual_size": int(info.pti_virtual_size),
        "resident_size": int(info.pti_resident_size),
        "total_user": int(info.pti_total_user),
        "total_system": int(info.pti_total_system),
        "threads_user": int(info.pti_threads_user),
        "threads_system": int(info.pti_threads_system),
        "policy": int(info.pti_policy),
        "faults": int(info.pti_faults),
        "pageins": int(info.pti_pageins),
        "cow_faults": int(info.pti_cow_faults),
        "messages_sent": int(info.pti_messages_sent),
        "messages_received": int(info.pti_messages_received),
        "syscalls_mach": int(info.pti_syscalls_mach),
        "syscalls_unix": int(info.pti_syscalls_unix),
        "context_switches": int(info.pti_csw),
        "thread_count": int(info.pti_threadnum),
        "running_threads": int(info.pti_numrunning),
        "priority": int(info.pti_priority),
    }


def get_process_rusage(pid: int) -> dict[str, Any] | None:
    info = RusageInfoV4()
    if LIBPROC.proc_pid_rusage(pid, RUSAGE_INFO_V4, ctypes.byref(info)) != 0:
        return None
    data: dict[str, Any] = {}
    for field_name, _ in info._fields_:
        value = getattr(info, field_name)
        if field_name == "ri_uuid":
            continue
        data[field_name] = int(value)
    data["total_cpu_ns"] = data.get("ri_user_time", 0) + data.get("ri_system_time", 0)
    data["dominant_qos"] = dominant_qos_label(data)
    return data


def get_process_path(pid: int) -> str | None:
    buffer = ctypes.create_string_buffer(4096)
    written = LIBPROC.proc_pidpath(pid, buffer, ctypes.sizeof(buffer))
    if written <= 0:
        return None
    return _decode_c_string(buffer.raw)


def parse_procargs_bytes(raw: bytes) -> list[str]:
    if len(raw) < 4:
        return []
    argc = int.from_bytes(raw[:4], "little", signed=True)
    if argc <= 0:
        return []
    cursor = 4
    while cursor < len(raw) and raw[cursor] != 0:
        cursor += 1
    while cursor < len(raw) and raw[cursor] == 0:
        cursor += 1
    args: list[str] = []
    while cursor < len(raw) and len(args) < argc:
        end = raw.find(b"\x00", cursor)
        if end == -1:
            break
        if end > cursor:
            args.append(raw[cursor:end].decode("utf-8", "ignore"))
        cursor = end + 1
    return args


def get_process_args(pid: int) -> list[str]:
    mib = (ctypes.c_int * 3)(CTL_KERN, KERN_PROCARGS2, pid)
    size = ctypes.c_size_t(0)
    if LIBC.sysctl(mib, 3, None, ctypes.byref(size), None, 0) != 0:
        return []
    if size.value <= 0:
        return []
    buffer = (ctypes.c_ubyte * size.value)()
    if LIBC.sysctl(mib, 3, buffer, ctypes.byref(size), None, 0) != 0:
        return []
    return parse_procargs_bytes(bytes(buffer[: size.value]))


def build_summary_entry(
    pid: int,
    cpu_state: dict[int, tuple[int, float]],
    current_monotonic: float,
    include_details: bool = False,
) -> dict[str, Any] | None:
    bsd = get_process_bsd_info(pid)
    if not bsd:
        return None
    task = get_process_task_info(pid) or {}
    rusage = get_process_rusage(pid) or {}
    total_cpu_ns = int(rusage.get("total_cpu_ns", 0))
    previous_total_ns, previous_monotonic = cpu_state.get(pid, (None, None))
    cpu_percent = calculate_cpu_percent(previous_total_ns, previous_monotonic, total_cpu_ns, current_monotonic)
    cpu_state[pid] = (total_cpu_ns, current_monotonic)
    display_command = bsd["registered_name"] or bsd["command"]
    path = None
    args: list[str] = []
    if include_details:
        path = get_process_path(pid)
        args = get_process_args(pid)
    command = path or display_command
    return {
        "pid": pid,
        "ppid": bsd["ppid"],
        "uid": bsd["uid"],
        "gid": bsd["gid"],
        "user": username_for_uid(bsd["uid"]),
        "state": bsd["state_code"],
        "state_name": bsd["status_name"],
        "cpu": round(cpu_percent, 1),
        "rss": int(task.get("resident_size") or rusage.get("ri_resident_size") or 0),
        "virtual_size": int(task.get("virtual_size") or 0),
        "threads": int(task.get("thread_count") or 0),
        "command": command,
        "basename": os.path.basename(command) if command else bsd["command"],
        "args": args,
        "path": path,
        "pgid": bsd["pgid"],
        "nice": bsd["nice"],
        "start_time": bsd["start_time"],
        "faults": int(task.get("faults") or 0),
        "pageins": int(task.get("pageins") or rusage.get("ri_pageins") or 0),
    }


def get_task_port(pid: int) -> int | None:
    task = ctypes.c_uint(0)
    result = LIBC.task_for_pid(LIBC.mach_task_self(), pid, ctypes.byref(task))
    if result != 0 or task.value == 0:
        return None
    return int(task.value)


def get_task_vm_info(pid: int) -> dict[str, Any] | None:
    task_port = get_task_port(pid)
    if task_port is None:
        return None
    info = TaskVMInfo()
    count = ctypes.c_uint(ctypes.sizeof(info) // ctypes.sizeof(ctypes.c_int))
    result = LIBC.task_info(task_port, TASK_VM_INFO, ctypes.byref(info), ctypes.byref(count))
    if result != 0:
        return None
    return {
        "virtual_size": int(info.virtual_size),
        "region_count": int(info.region_count),
        "page_size": int(info.page_size),
        "resident_size": int(info.resident_size),
        "resident_size_peak": int(info.resident_size_peak),
        "internal": int(info.internal),
        "external": int(info.external),
        "reusable": int(info.reusable),
        "compressed": int(info.compressed),
        "compressed_peak": int(info.compressed_peak),
        "compressed_lifetime": int(info.compressed_lifetime),
        "phys_footprint": int(info.phys_footprint),
        "device": int(info.device),
        "decompressions": int(info.decompressions),
    }


def get_focused_pid(pids: list[int], focus_pid: int) -> int | None:
    if focus_pid and focus_pid in pids:
        return focus_pid
    if pids:
        return pids[0]
    return None


def parse_lsof_output(text: str) -> dict[str, Any]:
    process: dict[str, Any] = {"pid": None, "command": None, "entries": []}
    current: dict[str, Any] | None = None
    for raw_line in text.splitlines():
        if not raw_line:
            continue
        prefix, value = raw_line[0], raw_line[1:]
        if prefix == "p":
            process["pid"] = int(value) if value.isdigit() else value
        elif prefix == "c":
            process["command"] = value
        elif prefix == "f":
            current = {"fd": value}
            process["entries"].append(current)
        elif current is not None and prefix == "t":
            current["type"] = value
        elif current is not None and prefix == "n":
            current["name"] = value
            current["target"] = value
    process["count"] = len(process["entries"])
    return process


def inspect_file_descriptors(pid: int) -> dict[str, Any]:
    native_entries = inspect_file_descriptors_native(pid)
    if native_entries["entries"]:
        return native_entries
    stdout, error = _command_output(["/usr/sbin/lsof", "-nP", f"-p{pid}", "-Fpcfnt"], timeout=2.5)
    if stdout is None:
        return {
            "pid": pid,
            "count": 0,
            "entries": [],
            "error": error or "lsof unavailable",
        }
    parsed = parse_lsof_output(stdout)
    parsed["pid"] = pid
    parsed["error"] = None
    parsed["source"] = "lsof"
    return parsed


def fd_type_name(fd_type: int) -> str:
    return {
        1: "VNODE",
        2: "SOCKET",
        3: "PSHM",
        4: "PSEM",
        5: "KQUEUE",
        6: "PIPE",
        7: "FSEVENTS",
        9: "NETPOLICY",
        10: "CHANNEL",
        11: "NEXUS",
    }.get(fd_type, f"TYPE_{fd_type}")


def _sockaddr_to_text(addr: In4In6Addr, vflag: int) -> str:
    if vflag == 1:
        return socket.inet_ntoa(bytes(addr.i46a_addr4))
    if vflag == 2:
        return ":".join(f"{value:02x}" for value in bytes(addr))
    return "unknown"


def inspect_file_descriptors_native(pid: int) -> dict[str, Any]:
    initial = 128
    entries: list[dict[str, Any]] = []
    count = initial
    while count <= 4096:
        buffer = (ProcFDInfo * count)()
        size = ctypes.sizeof(buffer)
        written = LIBPROC.proc_pidinfo(pid, PROC_PIDLISTFDS, 0, ctypes.byref(buffer), size)
        if written <= 0:
            return {"pid": pid, "count": 0, "entries": [], "error": "native fd list unavailable"}
        actual = written // ctypes.sizeof(ProcFDInfo)
        if actual < count or count >= 4096:
            for fdinfo in buffer[:actual]:
                entry = {
                    "fd": int(fdinfo.proc_fd),
                    "type": fd_type_name(int(fdinfo.proc_fdtype)),
                    "name": "-",
                    "target": "-",
                }
                if int(fdinfo.proc_fdtype) == 1:
                    vnode = VnodeFDInfoWithPath()
                    result = LIBPROC.proc_pidfdinfo(
                        pid,
                        int(fdinfo.proc_fd),
                        PROC_PIDFDVNODEPATHINFO,
                        ctypes.byref(vnode),
                        ctypes.sizeof(vnode),
                    )
                    if result > 0:
                        entry["name"] = _decode_c_string(vnode.pvip.vip_path)
                        entry["target"] = entry["name"]
                elif int(fdinfo.proc_fdtype) == 2:
                    sockinfo = SocketFDInfo()
                    result = LIBPROC.proc_pidfdinfo(
                        pid,
                        int(fdinfo.proc_fd),
                        PROC_PIDFDSOCKETINFO,
                        ctypes.byref(sockinfo),
                        ctypes.sizeof(sockinfo),
                    )
                    if result > 0:
                        proto = sockinfo.psi.soi_proto
                        local = _sockaddr_to_text(proto.insi_laddr, int(proto.insi_vflag))
                        remote = _sockaddr_to_text(proto.insi_faddr, int(proto.insi_vflag))
                        entry["target"] = (
                            f"{socket.AddressFamily(sockinfo.psi.soi_family).name if sockinfo.psi.soi_family in socket.AddressFamily._value2member_map_ else sockinfo.psi.soi_family}/"
                            f"{sockinfo.psi.soi_protocol} "
                            f"{local}:{int(proto.insi_lport)}->{remote}:{int(proto.insi_fport)}"
                        )
                        entry["name"] = entry["target"]
                entries.append(entry)
            return {"pid": pid, "count": len(entries), "entries": entries, "error": None, "source": "libproc"}
        count *= 2
    return {"pid": pid, "count": 0, "entries": [], "error": "fd enumeration overflow"}


def parse_vmmap_output(text: str, limit: int = 15) -> dict[str, Any]:
    regions: list[dict[str, Any]] = []
    summary: dict[str, str] = {}
    parsed_region_count = 0
    region_pattern = re.compile(
        r"^(?P<name>.{1,35}?)\s+(?P<start>[0-9A-Fa-f]+)-(?P<end>[0-9A-Fa-f]+)\s+\[(?P<size>[^\]]+)\]\s+(?P<prot>\S+)"
    )
    summary_pattern = re.compile(r"^(?P<label>[A-Za-z0-9 _/()\-]+):\s*(?P<value>.+)$")
    for line in text.splitlines():
        match = region_pattern.match(line.rstrip())
        if match:
            parsed_region_count += 1
            if len(regions) < limit:
                regions.append(
                    {
                        "region": match.group("name").strip(),
                        "start": match.group("start"),
                        "end": match.group("end"),
                        "size": match.group("size").strip(),
                        "protection": match.group("prot"),
                    }
                )
            continue
        summary_match = summary_pattern.match(line.strip())
        if summary_match and len(summary) < 20:
            label = summary_match.group("label").strip()
            if label not in summary:
                summary[label] = summary_match.group("value").strip()
    return {"regions": regions, "summary": summary, "parsed_region_count": parsed_region_count}


def inspect_memory(pid: int) -> dict[str, Any]:
    task = get_process_task_info(pid) or {}
    rusage = get_process_rusage(pid) or {}
    task_vm = get_task_vm_info(pid) or {}
    stdout, error = _command_output(["/usr/bin/vmmap", str(pid)], timeout=2.5)
    parsed_vmmap = parse_vmmap_output(stdout) if stdout else {"regions": [], "summary": {}, "parsed_region_count": 0}
    task_vm_region_count = int(task_vm.get("region_count") or 0)
    vmmap_region_count = int(parsed_vmmap.get("parsed_region_count") or 0)
    return {
        "pid": pid,
        "virtual_size": int(task_vm.get("virtual_size") or task.get("virtual_size") or 0),
        "resident_size": int(task_vm.get("resident_size") or task.get("resident_size") or rusage.get("ri_resident_size") or 0),
        "phys_footprint": int(task_vm.get("phys_footprint") or rusage.get("ri_phys_footprint") or 0),
        "wired_size": int(rusage.get("ri_wired_size") or 0),
        "pageins": int(task.get("pageins") or rusage.get("ri_pageins") or 0),
        "faults": int(task.get("faults") or 0),
        "internal": int(task_vm.get("internal") or 0),
        "external": int(task_vm.get("external") or 0),
        "reusable": int(task_vm.get("reusable") or 0),
        "compressed": int(task_vm.get("compressed") or 0),
        "region_count": task_vm_region_count or vmmap_region_count,
        "task_vm_region_count": task_vm_region_count,
        "vmmap_region_count": vmmap_region_count,
        "compressed_hint": parsed_vmmap["summary"].get("compressed"),
        "regions": parsed_vmmap["regions"],
        "vmmap_summary": parsed_vmmap["summary"],
        "error": error,
    }


def list_thread_ids(pid: int, expected_threads: int | None = None) -> list[int]:
    count = max(expected_threads or 1, 1)
    while count <= 2048:
        buffer = (ctypes.c_uint64 * count)()
        size = ctypes.sizeof(buffer)
        written = LIBPROC.proc_pidinfo(pid, PROC_PIDLISTTHREADS, 0, ctypes.byref(buffer), size)
        if written < 0:
            return []
        ids = written // ctypes.sizeof(ctypes.c_uint64)
        if ids < count or count >= 2048:
            return [int(thread_id) for thread_id in buffer[:ids] if thread_id]
        count *= 2
    return []


def inspect_threads(pid: int) -> dict[str, Any]:
    task = get_process_task_info(pid) or {}
    task_port = get_task_port(pid)
    if task_port is None:
        if not task:
            return {"pid": pid, "threads": [], "thread_count": 0, "error": "task port unavailable"}
        return inspect_threads_proc_fallback(pid, task)
    thread_list = ctypes.c_void_p()
    thread_count = ctypes.c_uint(0)
    result = LIBC.task_threads(task_port, ctypes.byref(thread_list), ctypes.byref(thread_count))
    if result != 0 or not thread_list.value:
        if not task:
            return {"pid": pid, "threads": [], "thread_count": 0, "error": "task threads unavailable"}
        return inspect_threads_proc_fallback(pid, task)
    threads: list[dict[str, Any]] = []
    error: str | None = None
    ports = ctypes.cast(thread_list.value, ctypes.POINTER(ctypes.c_uint))
    try:
        for index in range(int(thread_count.value)):
            thread_port = int(ports[index])
            basic = ThreadBasicInfo()
            basic_count = ctypes.c_uint(ctypes.sizeof(basic) // ctypes.sizeof(ctypes.c_int))
            if LIBC.thread_info(thread_port, THREAD_BASIC_INFO, ctypes.byref(basic), ctypes.byref(basic_count)) != 0:
                error = "partial thread visibility"
                continue
            extended = ThreadExtendedPolicy()
            extended_count = ctypes.c_uint(ctypes.sizeof(extended) // ctypes.sizeof(ctypes.c_int))
            get_default = ctypes.c_int(0)
            LIBC.thread_policy_get(
                thread_port,
                THREAD_EXTENDED_POLICY,
                ctypes.byref(extended),
                ctypes.byref(extended_count),
                ctypes.byref(get_default),
            )
            precedence = ThreadPrecedencePolicy()
            precedence_count = ctypes.c_uint(ctypes.sizeof(precedence) // ctypes.sizeof(ctypes.c_int))
            get_default_2 = ctypes.c_int(0)
            LIBC.thread_policy_get(
                thread_port,
                THREAD_PRECEDENCE_POLICY,
                ctypes.byref(precedence),
                ctypes.byref(precedence_count),
                ctypes.byref(get_default_2),
            )
            threads.append(
                {
                    "thread_id": thread_port,
                    "cpu_percent": round((max(int(basic.cpu_usage), 0) / TH_USAGE_SCALE) * 100.0, 1),
                    "policy": int(basic.policy),
                    "policy_name": policy_to_name(int(basic.policy)),
                    "run_state": int(basic.run_state),
                    "run_state_name": thread_state_to_name(int(basic.run_state)),
                    "flags": int(basic.flags),
                    "sleep_time": int(basic.sleep_time),
                    "current_priority": int(precedence.importance),
                    "priority": int(precedence.importance),
                    "max_priority": None,
                    "user_time_ns": (int(basic.user_time.seconds) * 1_000_000_000) + (int(basic.user_time.microseconds) * 1_000),
                    "system_time_ns": (int(basic.system_time.seconds) * 1_000_000_000) + (int(basic.system_time.microseconds) * 1_000),
                    "name": "",
                    "timeshare": bool(extended.timeshare),
                }
            )
    finally:
        LIBC.vm_deallocate(LIBC.mach_task_self(), int(thread_list.value), int(thread_count.value) * ctypes.sizeof(ctypes.c_uint))
    return {
        "pid": pid,
        "thread_count": int(task.get("thread_count") or len(threads)),
        "running_threads": int(task.get("running_threads") or 0),
        "threads": threads,
        "error": error,
    }


def inspect_threads_proc_fallback(pid: int, task: dict[str, Any]) -> dict[str, Any]:
    thread_ids = list_thread_ids(pid, task.get("thread_count"))
    threads: list[dict[str, Any]] = []
    error: str | None = None
    for thread_id in thread_ids:
        info = ProcThreadInfo()
        expected = ctypes.sizeof(info)
        written = LIBPROC.proc_pidinfo(pid, PROC_PIDTHREADINFO, thread_id, ctypes.byref(info), expected)
        if written != expected:
            error = "partial thread visibility"
            continue
        threads.append(
            {
                "thread_id": thread_id,
                "cpu_percent": round((max(info.pth_cpu_usage, 0) / TH_USAGE_SCALE) * 100.0, 1),
                "policy": int(info.pth_policy),
                "policy_name": policy_to_name(int(info.pth_policy)),
                "run_state": int(info.pth_run_state),
                "run_state_name": thread_state_to_name(int(info.pth_run_state)),
                "flags": int(info.pth_flags),
                "sleep_time": int(info.pth_sleep_time),
                "current_priority": int(info.pth_curpri),
                "priority": int(info.pth_priority),
                "max_priority": int(info.pth_maxpriority),
                "user_time_ns": int(info.pth_user_time),
                "system_time_ns": int(info.pth_system_time),
                "name": _decode_c_string(info.pth_name),
            }
        )
    return {
        "pid": pid,
        "thread_count": int(task.get("thread_count") or len(threads)),
        "running_threads": int(task.get("running_threads") or 0),
        "threads": threads,
        "error": error,
        "notes": ["task_for_pid no disponible; usando proc_pidinfo como fallback"],
    }


def inspect_signals(pid: int) -> dict[str, Any]:
    note = (
        "macOS no expone de forma portable los handlers ni todas las mascaras "
        "de senales de otros procesos desde userland; esta vista documenta esa limitacion."
    )
    ps_info = inspect_signals_via_ps(pid)
    ps_available = ps_info.get("error") is None
    if pid != os.getpid():
        return {
            "pid": pid,
            "blocked": ps_info.get("blocked", []),
            "pending": ps_info.get("pending", []),
            "blocked_available": ps_available,
            "pending_available": ps_available,
            "pending_group": None,
            "pending_group_available": False,
            "handlers": "no disponible para otros procesos",
            "error": ps_info.get("error"),
            "source": "ps sig/sigmask" if ps_available else "no disponible",
            "notes": [note, "Se usan columnas de ps para pending/sigmask cuando estan disponibles."],
        }
    blocked = sorted(sig.name for sig in signal.pthread_sigmask(signal.SIG_BLOCK, []))
    pending = sorted(sig.name for sig in signal.sigpending())
    return {
        "pid": pid,
        "blocked": blocked or ps_info.get("blocked", []),
        "pending": pending or ps_info.get("pending", []),
        "blocked_available": True,
        "pending_available": True,
        "pending_group": None,
        "pending_group_available": False,
        "handlers": "no disponible para inspeccion externa",
        "error": ps_info.get("error"),
        "source": "pthread/sigpending del monitor + ps fallback",
        "notes": [note, "Para el propio monitor se muestra la mascara actual del hilo principal."],
    }


def _hex_signals_to_names(hex_mask: str) -> list[str]:
    cleaned = hex_mask.strip()
    if not cleaned or cleaned == "0":
        return []
    try:
        value = int(cleaned, 16)
    except ValueError:
        return [cleaned]
    names: list[str] = []
    for sig in signal.Signals:
        if value & (1 << (sig.value - 1)):
            names.append(sig.name)
    return names


def inspect_signals_via_ps(pid: int) -> dict[str, Any]:
    stdout, error = _command_output(
        ["/bin/ps", "-o", "pid=,sig=,sigmask=", "-p", str(pid)],
        timeout=1.5,
    )
    if stdout is None:
        return {"blocked": [], "pending": [], "error": error or "ps unavailable"}
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        return {"blocked": [], "pending": [], "error": "ps returned no rows"}
    parts = lines[-1].split()
    if len(parts) < 3:
        return {"blocked": [], "pending": [], "error": "ps returned unexpected format"}
    return {
        "pending": _hex_signals_to_names(parts[1]),
        "blocked": _hex_signals_to_names(parts[2]),
        "error": None,
    }


def parse_ps_scheduling_output(text: str) -> dict[str, int | None]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return {"session_id": None, "voluntary_context_switches": None, "involuntary_context_switches": None}
    parts = lines[-1].split()
    if len(parts) < 4:
        return {"session_id": None, "voluntary_context_switches": None, "involuntary_context_switches": None}
    return {
        "session_id": _int_or_none(parts[1]),
        "voluntary_context_switches": _int_or_none(parts[2]),
        "involuntary_context_switches": _int_or_none(parts[3]),
    }


def _int_or_none(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


def inspect_scheduling_via_ps(pid: int) -> dict[str, Any]:
    stdout, error = _command_output(
        ["/bin/ps", "-o", "pid=,sess=,nvcsw=,nivcsw=", "-p", str(pid)],
        timeout=1.5,
    )
    if stdout is None:
        return {
            "session_id": None,
            "voluntary_context_switches": None,
            "involuntary_context_switches": None,
            "error": error or "ps unavailable",
        }
    parsed = parse_ps_scheduling_output(stdout)
    parsed["error"] = None
    return parsed


def inspect_scheduling(pid: int) -> dict[str, Any]:
    bsd = get_process_bsd_info(pid) or {}
    task = get_process_task_info(pid) or {}
    rusage = get_process_rusage(pid) or {}
    try:
        nice_value = os.getpriority(os.PRIO_PROCESS, pid)
    except (PermissionError, ProcessLookupError, OSError):
        nice_value = bsd.get("nice")
    ps_sched = inspect_scheduling_via_ps(pid)
    threads = inspect_threads(pid)
    thread_policies = [item["policy"] for item in threads.get("threads", [])]
    dominant_policy = None
    if thread_policies:
        dominant_policy = max(set(thread_policies), key=thread_policies.count)
    notes: list[str] = []
    if ps_sched.get("error"):
        notes.append(
            "No se pudieron separar voluntary/involuntary context switches via ps; "
            "se muestra pti_csw como total disponible desde libproc."
        )
    elif ps_sched.get("voluntary_context_switches") is None or ps_sched.get("involuntary_context_switches") is None:
        notes.append(
            "ps no entrego nvcsw/nivcsw para este proceso; "
            "se muestra pti_csw como total disponible desde libproc."
        )
    notes.extend(threads.get("notes", []))
    return {
        "pid": pid,
        "nice": nice_value,
        "session_id": ps_sched.get("session_id"),
        "pgid": bsd.get("pgid"),
        "task_policy": task.get("policy"),
        "task_policy_name": policy_to_name(task.get("policy")),
        "dominant_thread_policy": dominant_policy,
        "dominant_thread_policy_name": policy_to_name(dominant_policy),
        "priority": task.get("priority"),
        "context_switches_total": task.get("context_switches"),
        "voluntary_context_switches": ps_sched.get("voluntary_context_switches"),
        "involuntary_context_switches": ps_sched.get("involuntary_context_switches"),
        "syscalls_unix": task.get("syscalls_unix"),
        "syscalls_mach": task.get("syscalls_mach"),
        "utime_ns": rusage.get("ri_user_time"),
        "stime_ns": rusage.get("ri_system_time"),
        "interrupt_wakeups": rusage.get("ri_interrupt_wkups"),
        "idle_wakeups": rusage.get("ri_pkg_idle_wkups"),
        "qos": rusage.get("dominant_qos"),
        "affinity": "no expuesto por macOS para procesos no privilegiados",
        "error": threads.get("error"),
        "notes": notes,
    }


def parse_vm_stat_output(text: str) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    page_size_match = re.search(r"page size of (\d+) bytes", text)
    if page_size_match:
        parsed["page_size"] = int(page_size_match.group(1))
    for line in text.splitlines():
        match = re.match(r'("?[^":]+"?):\s+([0-9]+)\.', line)
        if not match:
            continue
        key = match.group(1).strip('"').lower().replace(" ", "_").replace("-", "_")
        parsed[key] = int(match.group(2))
    return parsed


def parse_swapusage_text(text: str | None) -> dict[str, str | None]:
    if not text:
        return {"raw": None, "total": None, "used": None, "free": None}
    matches = dict(re.findall(r"(total|used|free) = ([^ ]+)", text))
    return {
        "raw": text,
        "total": matches.get("total"),
        "used": matches.get("used"),
        "free": matches.get("free"),
    }


def cpu_percentages_from_ticks(current: list[int], previous: list[int] | None) -> dict[str, float]:
    if previous and len(previous) == len(current):
        deltas = [max(curr - prev, 0) for curr, prev in zip(current, previous)]
    else:
        deltas = current
    total = sum(deltas) or 1
    return {
        "user": round((deltas[0] / total) * 100.0, 1),
        "system": round((deltas[1] / total) * 100.0, 1),
        "idle": round((deltas[2] / total) * 100.0, 1),
        "nice": round((deltas[3] / total) * 100.0, 1),
        "raw_ticks": current,
    }


def get_cpu_ticks() -> list[int]:
    host = LIBC.mach_host_self()
    info = HostCpuLoadInfo()
    count = ctypes.c_uint(HOST_CPU_LOAD_INFO_COUNT)
    result = LIBC.host_statistics(host, HOST_CPU_LOAD_INFO, ctypes.byref(info), ctypes.byref(count))
    if result != 0:
        return [0, 0, 0, 0]
    return [int(value) for value in info.cpu_ticks]


def get_vm_stats() -> dict[str, Any]:
    host = LIBC.mach_host_self()
    info = VMStatistics64()
    count = ctypes.c_uint(ctypes.sizeof(info) // ctypes.sizeof(ctypes.c_int))
    result = LIBC.host_statistics64(host, HOST_VM_INFO64, ctypes.byref(info), ctypes.byref(count))
    if result != 0:
        return {}
    page_size = resource.getpagesize()
    return {
        "page_size": page_size,
        "free": int(info.free_count) * page_size,
        "active": int(info.active_count) * page_size,
        "inactive": int(info.inactive_count) * page_size,
        "wired": int(info.wire_count) * page_size,
        "speculative": int(info.speculative_count) * page_size,
        "purgeable": int(info.purgeable_count) * page_size,
        "compressor": int(info.compressor_page_count) * page_size,
        "file_backed": int(info.external_page_count) * page_size,
        "anonymous": int(info.internal_page_count) * page_size,
        "faults": int(info.faults),
        "pageins": int(info.pageins),
        "pageouts": int(info.pageouts),
        "swapins": int(info.swapins),
        "swapouts": int(info.swapouts),
        "compressions": int(info.compressions),
        "decompressions": int(info.decompressions),
    }


def summarize_rows_for_system(summary_rows: list[dict[str, Any]], limit: int = 3) -> dict[str, Any]:
    by_cpu = sorted(summary_rows, key=lambda item: (-item["cpu"], -item["rss"], item["pid"]))[:limit]
    by_mem = sorted(summary_rows, key=lambda item: (-item["rss"], -item["cpu"], item["pid"]))[:limit]
    state_counts: dict[str, int] = {}
    for row in summary_rows:
        state_name = row.get("state_name", "UNKNOWN")
        state_counts[state_name] = state_counts.get(state_name, 0) + 1
    return {
        "top_cpu": by_cpu,
        "top_memory": by_mem,
        "state_counts": state_counts,
    }


def get_system_snapshot(
    pids: list[int],
    previous_cpu_ticks: list[int] | None,
    summary_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ticks = get_cpu_ticks()
    cpu = cpu_percentages_from_ticks(ticks, previous_cpu_ticks)
    vm_stats = get_vm_stats()
    loads = os.getloadavg()
    boot_time = boot_time_seconds()
    swap_text = sysctl_text("vm.swapusage")
    vm_stat_stdout, vm_stat_error = _command_output(["/usr/bin/vm_stat"], timeout=1.5)
    system_summary = summarize_rows_for_system(summary_rows or [])
    return {
        "cpu": cpu,
        "loadavg": {
            "1m": round(loads[0], 2),
            "5m": round(loads[1], 2),
            "15m": round(loads[2], 2),
        },
        "cores": {
            "ncpu": sysctl_uint("hw.ncpu"),
            "activecpu": sysctl_uint("hw.activecpu"),
        },
        "memory": {
            "total": sysctl_uint("hw.memsize"),
            **vm_stats,
        },
        "swap": parse_swapusage_text(swap_text),
        "boot_time": boot_time,
        "uptime_seconds": max(0, int(time.time() - boot_time)) if boot_time else None,
        "process_counts": {
            "total": len(summary_rows) if summary_rows is not None else len(pids),
            "by_state": system_summary["state_counts"],
        },
        "vm_stat": parse_vm_stat_output(vm_stat_stdout or "") if vm_stat_stdout else {},
        "vm_stat_error": vm_stat_error,
        "top_cpu": system_summary["top_cpu"],
        "top_memory": system_summary["top_memory"],
    }
