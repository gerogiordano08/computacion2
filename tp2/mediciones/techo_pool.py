"""Aumenta la carga de hashes y registra tiempos, throughput y latencia HTTP."""

import argparse
import asyncio
import time
from datetime import datetime

import httpx

from .comun import entero_positivo, entorno, guardar, positivo, resumen


def segundos(antes, despues):
    return (
        datetime.fromisoformat(despues) - datetime.fromisoformat(antes)
    ).total_seconds()


async def lote(cliente, cliente_sondeo, cantidad, entrada, args):
    ids = []
    muestras_get = []
    comenzaron = asyncio.Event()
    terminar_sondeo = asyncio.Event()

    async def una():
        inicio = time.perf_counter()
        respuesta = await cliente.post("/tareas", json=entrada)
        latencia_post = time.perf_counter() - inicio
        respuesta.raise_for_status()
        identificador = respuesta.json()["id"]
        ids.append(identificador)
        comenzaron.set()

        while True:
            respuesta = await cliente.get(f"/tareas/{identificador}")
            respuesta.raise_for_status()
            tarea = respuesta.json()
            if tarea["estado"] in ("completada", "fallida", "cancelada"):
                return {
                    "id": identificador,
                    "estado": tarea["estado"],
                    "error": tarea["error"],
                    "latencia_post_segundos": latencia_post,
                    "cliente_total_segundos": time.perf_counter() - inicio,
                    "cola_segundos": segundos(tarea["creada_en"], tarea["iniciada_en"])
                    if tarea["iniciada_en"] else None,
                    "ejecucion_segundos": segundos(tarea["iniciada_en"], tarea["finalizada_en"])
                    if tarea["iniciada_en"] else None,
                    "total_servidor_segundos": segundos(
                        tarea["creada_en"], tarea["finalizada_en"]
                    ),
                }
            await asyncio.sleep(args.intervalo)

    async def sondear_api():
        await comenzaron.wait()
        while not terminar_sondeo.is_set():
            inicio_get = time.perf_counter()
            try:
                respuesta = await cliente_sondeo.get("/tareas")
                duracion_get = time.perf_counter() - inicio_get
                activas = None
                if respuesta.status_code == 200:
                    activas = sum(
                        t["id"] in ids
                        and t["estado"] in ("pendiente", "ejecutando")
                        for t in respuesta.json()
                    )
                muestras_get.append({
                    "segundos": duracion_get,
                    "codigo": respuesta.status_code,
                    "tareas_del_lote_activas_al_responder": activas,
                })
            except httpx.HTTPError as error:
                muestras_get.append({
                    "segundos": time.perf_counter() - inicio_get,
                    "codigo": None,
                    "error": str(error),
                })
            try:
                await asyncio.wait_for(
                    terminar_sondeo.wait(), timeout=args.intervalo_get
                )
            except TimeoutError:
                pass

    inicio = time.perf_counter()
    sondeo = asyncio.create_task(sondear_api())
    trabajos = [asyncio.create_task(una()) for _ in range(cantidad)]
    try:
        async with asyncio.timeout(args.limite_lote):
            filas = await asyncio.gather(*trabajos, return_exceptions=True)
        duracion = time.perf_counter() - inicio
        terminar_sondeo.set()
        await sondeo
        for fila in filas:
            if isinstance(fila, BaseException):
                raise fila
        return {
            "duracion_lote_segundos": duracion,
            "completadas_por_segundo": sum(f["estado"] == "completada" for f in filas) / duracion,
            "errores": sum(f["estado"] != "completada" for f in filas),
            "latencia_total_segundos": resumen([f["cliente_total_segundos"] for f in filas]),
            "cola_segundos": resumir_si_hay([
                f["cola_segundos"] for f in filas
                if f["cola_segundos"] is not None
            ]),
            "ejecucion_segundos": resumir_si_hay([
                f["ejecucion_segundos"] for f in filas
                if f["ejecucion_segundos"] is not None
            ]),
            "latencia_get_segundos": resumir_si_hay([
                m["segundos"] for m in muestras_get if m["codigo"] == 200
            ]),
            "errores_get": sum(m["codigo"] != 200 for m in muestras_get),
            "muestras_get": muestras_get,
            "tareas": filas,
        }
    finally:
        terminar_sondeo.set()
        comenzaron.set()
        await sondeo
        # Si se interrumpe una medición, no dejamos sus tareas calculando.
        for trabajo in trabajos:
            if not trabajo.done():
                trabajo.cancel()
        await asyncio.gather(*trabajos, return_exceptions=True)
        for identificador in ids:
            respuesta = await cliente.get(f"/tareas/{identificador}")
            respuesta.raise_for_status()
            if respuesta.json()["estado"] in ("pendiente", "ejecutando"):
                respuesta = await cliente.delete(f"/tareas/{identificador}")
                respuesta.raise_for_status()


def resumir_si_hay(valores):
    return resumen(valores) if valores else None


def formatear_resumen(datos, campo="promedio", escala=1):
    return f"{datos[campo] * escala:.3f}" if datos else "n/a"


async def medir(args):
    entrada = {"tipo": args.tipo, "timeout": args.timeout_tarea}
    if args.tipo == "esperar":
        entrada["segundos"] = args.segundos
    else:
        entrada.update(texto="medicion", iteraciones=args.iteraciones)

    limites = httpx.Limits(max_connections=max(100, max(args.cargas)))
    async with httpx.AsyncClient(
        base_url=args.base_url, timeout=30, limits=limites, trust_env=False
    ) as cliente, httpx.AsyncClient(
        base_url=args.base_url, timeout=30, trust_env=False,
        limits=httpx.Limits(max_connections=1),
    ) as cliente_sondeo:
        respuesta = await cliente.get("/estadisticas")
        respuesta.raise_for_status()
        inicial = respuesta.json()
        if inicial["por_estado"]["pendiente"] or inicial["workers_ocupados"]:
            raise RuntimeError("Esperá a que la API quede sin tareas activas antes de medir")

        # Calentamiento del servidor y del executor, fuera de los lotes medidos.
        calentamiento = dict(entrada)
        if args.tipo == "hashear":
            calentamiento["iteraciones"] = 1000
        await lote(
            cliente, cliente_sondeo,
            min(inicial["cantidad_workers"], max(args.cargas)),
            calentamiento, args,
        )

        # Referencia sin trabajos activos, usando la misma conexión de sondeo.
        latencias_sin_carga = []
        for _ in range(5):
            inicio = time.perf_counter()
            respuesta = await cliente_sondeo.get("/tareas")
            latencias_sin_carga.append(time.perf_counter() - inicio)
            respuesta.raise_for_status()

        niveles = []
        for cantidad in args.cargas:
            repeticiones = []
            for numero in range(args.repeticiones):
                resultado = await lote(
                    cliente, cliente_sondeo, cantidad, entrada, args
                )
                repeticiones.append(resultado)
                print(
                    f"{cantidad:4} tareas, repetición {numero + 1}: "
                    f"lote={resultado['duracion_lote_segundos']:.3f}s, "
                    f"cola media={formatear_resumen(resultado['cola_segundos'])}s, "
                    "GET p95="
                    f"{formatear_resumen(resultado['latencia_get_segundos'], 'p95', 1000)}ms, "
                    f"completadas/s={resultado['completadas_por_segundo']:.2f}, "
                    f"errores tareas/GET={resultado['errores']}/{resultado['errores_get']}"
                )
            tareas = [t for r in repeticiones for t in r["tareas"]]
            gets = [m for r in repeticiones for m in r["muestras_get"]]
            niveles.append({
                "cantidad_tareas": cantidad,
                "repeticiones": repeticiones,
                "duracion_lote_segundos": resumen([
                    r["duracion_lote_segundos"] for r in repeticiones
                ]),
                "completadas_por_segundo": resumen([
                    r["completadas_por_segundo"] for r in repeticiones
                ]),
                "latencia_total_segundos": resumen([
                    t["cliente_total_segundos"] for t in tareas
                ]),
                "cola_segundos": resumir_si_hay([
                    t["cola_segundos"] for t in tareas
                    if t["cola_segundos"] is not None
                ]),
                "ejecucion_segundos": resumir_si_hay([
                    t["ejecucion_segundos"] for t in tareas
                    if t["ejecucion_segundos"] is not None
                ]),
                "latencia_get_segundos": resumir_si_hay([
                    m["segundos"] for m in gets if m["codigo"] == 200
                ]),
                "errores": sum(r["errores"] for r in repeticiones),
                "errores_get": sum(r["errores_get"] for r in repeticiones),
            })

    datos = {
        "medicion": "techo_pool",
        "entorno_generador": entorno(),
        "condiciones": {
            "base_url": args.base_url,
            "entrada": entrada,
            "cargas": args.cargas,
            "repeticiones": args.repeticiones,
            "workers_configurados": inicial["cantidad_workers"],
            "intervalo_consulta_segundos": args.intervalo,
            "intervalo_get_segundos": args.intervalo_get,
            "limite_lote_segundos": args.limite_lote,
            "tareas_previas_en_historial": inicial["total"],
            "nota": "Anotar también procesos CPU y recursos Docker del servidor",
        },
        "latencia_get_sin_carga_segundos": resumen(latencias_sin_carga),
        "niveles": niveles,
    }
    print("\nResumen de todas las repeticiones por carga:")
    print("Tareas | Total medio s | Total p95 s | Cola media s | Ejec. media s | GET p95 ms | Completadas/s | Errores tareas/GET")
    for nivel in niveles:
        print(
            f"{nivel['cantidad_tareas']:6} | "
            f"{formatear_resumen(nivel['latencia_total_segundos'])} | "
            f"{formatear_resumen(nivel['latencia_total_segundos'], 'p95')} | "
            f"{formatear_resumen(nivel['cola_segundos'])} | "
            f"{formatear_resumen(nivel['ejecucion_segundos'])} | "
            f"{formatear_resumen(nivel['latencia_get_segundos'], 'p95', 1000)} | "
            f"{nivel['completadas_por_segundo']['mediana']:.2f} | "
            f"{nivel['errores']}/{nivel['errores_get']}"
        )
    guardar(datos, args.salida)
    if any(n["errores"] or n["errores_get"] for n in niveles):
        raise SystemExit(
            "Hubo tareas fallidas: revisar los errores del JSON "
            "antes de interpretar capacidad"
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--tipo", choices=("esperar", "hashear"), default="hashear")
    parser.add_argument("--cargas", type=entero_positivo, nargs="+", default=[1, 2, 4, 8, 16, 32])
    parser.add_argument("--repeticiones", type=entero_positivo, default=3)
    parser.add_argument("--segundos", type=positivo, default=0.25)
    parser.add_argument("--iteraciones", type=entero_positivo, default=1_000_000)
    parser.add_argument("--timeout-tarea", type=positivo, default=60)
    parser.add_argument("--limite-lote", type=positivo, default=120)
    parser.add_argument("--intervalo", type=positivo, default=0.02)
    parser.add_argument("--intervalo-get", type=positivo, default=0.1)
    parser.add_argument("--salida", default="mediciones/resultados/techo_pool.json")
    args = parser.parse_args()
    args.cargas = sorted(set(args.cargas))
    asyncio.run(medir(args))


if __name__ == "__main__":
    main()
