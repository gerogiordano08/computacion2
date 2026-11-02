"""Utilidades compartidas por las mediciones, fuera de la aplicación."""

import json
import math
import os
import platform
import statistics
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def positivo(valor):
    numero = float(valor)
    if not math.isfinite(numero) or numero <= 0:
        raise ValueError("El valor debe ser positivo y finito")
    return numero


def entero_positivo(valor):
    numero = int(valor)
    if numero < 1:
        raise ValueError("El valor debe ser mayor que cero")
    return numero


def resumen(valores):
    """P95 mediante rango más próximo; conserva también las muestras crudas."""
    ordenados = sorted(valores)
    return {
        "muestras": valores,
        "promedio": statistics.mean(valores),
        "mediana": statistics.median(valores),
        "p95": ordenados[math.ceil(0.95 * len(ordenados)) - 1],
    }


def entorno():
    paquetes = {}
    for nombre in ("fastapi", "uvicorn", "httpx", "pydantic"):
        try:
            paquetes[nombre] = version(nombre)
        except PackageNotFoundError:
            paquetes[nombre] = "no instalado"

    datos = {
        "fecha_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "sistema": platform.platform(),
        "cpu_logicas_visibles": os.cpu_count(),
        "paquetes": paquetes,
    }
    for nombre in ("cpu.max", "memory.max"):
        archivo = Path("/sys/fs/cgroup") / nombre
        if archivo.is_file():
            datos[nombre] = archivo.read_text().strip()
    return datos


def guardar(datos, salida):
    salida = Path(salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(
        json.dumps(datos, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    print(f"Resultados guardados en {salida}")


@contextmanager
def servidor_descargas(demora):
    """HTTP real en loopback, con una demora fija por solicitud."""
    contenido = b"x" * 1024

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            # Corre en un thread del servidor de prueba, no en el event loop.
            time.sleep(demora)
            self.send_response(200)
            self.send_header("Content-Length", str(len(contenido)))
            self.end_headers()
            try:
                self.wfile.write(contenido)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    class Servidor(ThreadingHTTPServer):
        request_queue_size = 128
        daemon_threads = True

    servidor = Servidor(("127.0.0.1", 0), Handler)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    try:
        yield servidor.server_port
    finally:
        servidor.shutdown()
        servidor.server_close()
        hilo.join()


def hash_con_aviso(entrada, cancelacion):
    """Permite iniciar el GET cuando el hash medido ya está calculándose."""
    from src.tareas import hashear

    marca = Path(os.environ["MEDICION_MARCA_HASH"])
    marca.write_text(str(time.perf_counter()), encoding="utf-8")
    try:
        return hashear(entrada, cancelacion)
    finally:
        marca.with_suffix(".fin").write_text(
            str(time.perf_counter()), encoding="utf-8"
        )
