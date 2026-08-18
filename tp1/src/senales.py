from __future__ import annotations

import os
import signal
from typing import Iterable


HANDLED_SIGNALS = [
    signal.SIGINT,
    signal.SIGTERM,
    signal.SIGHUP,
    signal.SIGUSR1,
    signal.SIGUSR2,
]

if hasattr(signal, "SIGWINCH"):
    HANDLED_SIGNALS.append(signal.SIGWINCH)


class SignalController:
    def __init__(self) -> None:
        self.read_fd, self.write_fd = os.pipe()
        os.set_blocking(self.read_fd, False)
        os.set_blocking(self.write_fd, False)
        self._installed: list[signal.Signals] = []

    def install(self, handled: Iterable[signal.Signals] = HANDLED_SIGNALS) -> None:
        for signum in handled:
            signal.signal(signum, self._handler)
            self._installed.append(signum)

    def _handler(self, signum: int, _frame: object) -> None:
        try:
            os.write(self.write_fd, bytes([signum & 0xFF]))
        except OSError:
            pass

    def drain(self) -> list[int]:
        received: list[int] = []
        while True:
            try:
                chunk = os.read(self.read_fd, 128)
            except BlockingIOError:
                break
            if not chunk:
                break
            received.extend(chunk)
        return received

    def close(self) -> None:
        try:
            os.close(self.read_fd)
        except OSError:
            pass
        try:
            os.close(self.write_fd)
        except OSError:
            pass


def install_signal_controller() -> SignalController:
    controller = SignalController()
    controller.install()
    return controller
