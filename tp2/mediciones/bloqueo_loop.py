"""Mide GET /tareas durante un hash con y sin executor en APIs aisladas."""

import argparse
import asyncio
import functools
import os
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import httpx

from .comun import entero_positivo, entorno, guardar, hash_con_aviso
from .comun import positivo, resumen


def servir(args):
    """La variante bloqueante existe únicamente en este servidor experimental."""
    import uvicorn
    import src.gestor as modulo_gestor
    from src.main import app, gestor
    from src.modelos import HashearEntrada

    os.environ["MEDICION_MARCA_HASH"] = args.marca
    modulo_gestor.hashear = hash_con_aviso

    if args.modo == "sin_executor":
        original = gestor._ejecutar

        async def ejecutar(entrada):
            if isinstance(entrada, HashearEntrada):
                cancelacion = await asyncio.to_thread(gestor.manager.Event)
                # Bloqueo intencional exigido por la medición del TP.
                return hash_con_aviso(entrada, cancelacion)
            return await original(entrada)

        gestor._ejecutar = ejecutar

    gestor.iniciar = functools.partial(
        gestor.iniciar, directorio=args.directorio
    )
    gestor.detener = functools.partial(
        gestor.detener, plazo=1, directorio=args.directorio
    )
    uvicorn.run(app, host="127.0.0.1", port=args.puerto, access_log=False)


def esperar_arranque(cliente, proceso, timeout):
    limite = time.perf_counter() + timeout
    while time.perf_counter() < limite:
        if proceso.poll() is not None:
            raise RuntimeError("El servidor experimental terminó antes de arrancar")
        try:
            respuesta = cliente.get("/estadisticas", timeout=0.5)
            respuesta.raise_for_status()
            return
        except httpx.TransportError:
            time.sleep(0.02)
    raise TimeoutError("El servidor experimental no arrancó")


def esperar_fin(cliente, tarea_id, timeout):
    limite = time.perf_counter() + timeout
    while time.perf_counter() < limite:
        respuesta = cliente.get(f"/tareas/{tarea_id}")
        respuesta.raise_for_status()
        tarea = respuesta.json()
        if tarea["estado"] == "completada":
            return tarea
        if tarea["estado"] in ("fallida", "cancelada"):
            raise RuntimeError(f"El hash no terminó correctamente: {tarea}")
        time.sleep(0.01)
    raise TimeoutError("El hash no terminó dentro del límite de la medición")


def medir_modo(args, modo):
    muestras = []
    with tempfile.TemporaryDirectory(prefix="tp2_bloqueo_") as temporal:
        carpeta = Path(temporal)
        marca = carpeta / "hash.inicio"
        with socket.socket() as socket_libre:
            socket_libre.bind(("127.0.0.1", 0))
            puerto = socket_libre.getsockname()[1]

        comando = [
            sys.executable, "-m", "mediciones.bloqueo_loop", "--servidor",
            "--modo", modo, "--puerto", str(puerto),
            "--directorio", temporal, "--marca", str(marca),
        ]
        # El arranque del proceso, del manager y del pool queda fuera del GET.
        with (carpeta / "servidor.log").open("w+") as log:
            proceso = subprocess.Popen(
                comando, stdout=log, stderr=subprocess.STDOUT,
                env=dict(os.environ, CANTIDAD_WORKERS="4", PROCESOS_CPU="2"),
            )
            try:
                with httpx.Client(
                    base_url=f"http://127.0.0.1:{puerto}",
                    timeout=args.timeout, trust_env=False,
                ) as cliente:
                    esperar_arranque(cliente, proceso, args.timeout)
                    # Calentamos el pool y la conexión antes de medir.
                    respuesta = cliente.post("/tareas", json={
                        "tipo": "hashear", "texto": "medicion",
                        "iteraciones": 1000, "timeout": args.timeout,
                    })
                    respuesta.raise_for_status()
                    esperar_fin(cliente, respuesta.json()["id"], args.timeout)
                    cliente.get("/tareas").raise_for_status()

                    for numero in range(args.repeticiones):
                        marca.unlink(missing_ok=True)
                        marca.with_suffix(".fin").unlink(missing_ok=True)
                        respuesta = cliente.post("/tareas", json={
                            "tipo": "hashear", "texto": "medicion",
                            "iteraciones": args.iteraciones,
                            "timeout": args.timeout,
                        })
                        respuesta.raise_for_status()
                        tarea_id = respuesta.json()["id"]

                        limite = time.perf_counter() + args.timeout
                        while not marca.exists():
                            if proceso.poll() is not None:
                                raise RuntimeError("El servidor experimental terminó")
                            if time.perf_counter() >= limite:
                                raise TimeoutError("El hash no comenzó")
                            time.sleep(0.002)

                        # La marca se escribe dentro del cálculo, no al encolarlo.
                        if marca.with_suffix(".fin").exists():
                            raise RuntimeError(
                                "El hash terminó antes del GET; aumentá --iteraciones"
                            )

                        inicio = time.perf_counter()
                        respuesta = cliente.get("/tareas")
                        latencia = time.perf_counter() - inicio
                        respuesta.raise_for_status()
                        estado_al_responder = next(
                            t["estado"] for t in respuesta.json()
                            if t["id"] == tarea_id
                        )
                        tarea = esperar_fin(cliente, tarea_id, args.timeout)
                        inicio_hash = float(marca.read_text())
                        fin_hash = float(marca.with_suffix(".fin").read_text())
                        if not inicio_hash <= inicio < fin_hash:
                            raise RuntimeError(
                                "El GET no coincidió con el hash; aumentá --iteraciones"
                            )

                        duracion = (
                            datetime.fromisoformat(tarea["finalizada_en"])
                            - datetime.fromisoformat(tarea["iniciada_en"])
                        ).total_seconds()
                        muestras.append({
                            "repeticion": numero + 1,
                            "get_segundos": latencia,
                            "hash_segundos": fin_hash - inicio_hash,
                            "ejecucion_tarea_segundos": duracion,
                            "estado_al_responder_get": estado_al_responder,
                            "hash": tarea["resultado"]["hash"],
                        })
                        print(f"{modo}, repetición {numero + 1}: GET = {latencia:.6f} s")
            except BaseException:
                log.flush()
                log.seek(0)
                print(log.read(), file=sys.stderr)
                raise
            finally:
                proceso.terminate()
                try:
                    proceso.wait(timeout=args.timeout + 5)
                except subprocess.TimeoutExpired:
                    proceso.kill()
                    proceso.wait()

    return {
        "muestras": muestras,
        "latencia_get_segundos": resumen([m["get_segundos"] for m in muestras]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iteraciones", type=entero_positivo, default=5_000_000)
    parser.add_argument("--repeticiones", type=entero_positivo, default=3)
    parser.add_argument("--timeout", type=positivo, default=120)
    parser.add_argument("--salida", default="mediciones/resultados/bloqueo_loop.json")
    parser.add_argument("--servidor", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--modo", choices=("sin_executor", "con_executor"), help=argparse.SUPPRESS)
    parser.add_argument("--puerto", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--directorio", help=argparse.SUPPRESS)
    parser.add_argument("--marca", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.servidor:
        servir(args)
        return

    datos = {
        "medicion": "bloqueo_loop",
        "entorno": entorno(),
        "condiciones": {
            "iteraciones": args.iteraciones,
            "repeticiones": args.repeticiones,
            "workers": 4,
            "procesos_cpu_configurados": 2,
            "timeout_segundos": args.timeout,
            "alcance": "Dos APIs aisladas; no modifica la API principal",
            "sin_executor": "Mismo hash y señal, ejecutado en el event loop",
            "sincronizacion": "GET enviado después de la marca de inicio del cálculo",
        },
        "sin_executor": medir_modo(args, "sin_executor"),
        "con_executor": medir_modo(args, "con_executor"),
    }
    hashes = {
        muestra["hash"]
        for modo in ("sin_executor", "con_executor")
        for muestra in datos[modo]["muestras"]
    }
    if len(hashes) != 1:
        raise RuntimeError("Los resultados del hash difieren entre escenarios")
    guardar(datos, args.salida)


if __name__ == "__main__":
    main()
