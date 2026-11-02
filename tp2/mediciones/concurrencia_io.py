"""Compara la función descargar secuencial y concurrente, sin API ni cola."""

import argparse
import asyncio
import time

from src.modelos import DescargarEntrada
from src.tareas import descargar

from .comun import entero_positivo, entorno, guardar, positivo, resumen
from .comun import servidor_descargas


async def medir(args, urls):
    muestras = {"secuencial": [], "concurrente": []}
    entradas_individuales = [
        DescargarEntrada(tipo="descargar", urls=[url]) for url in urls
    ]
    entrada_conjunta = DescargarEntrada(tipo="descargar", urls=urls)
    await descargar(entradas_individuales[0])

    for repeticion in range(args.repeticiones):
        # Alternamos el orden para reducir el sesgo de ejecutar uno primero.
        modos = ("secuencial", "concurrente")
        if repeticion % 2:
            modos = tuple(reversed(modos))

        for modo in modos:
            inicio = time.perf_counter()
            async with asyncio.timeout(args.timeout):
                if modo == "secuencial":
                    resultados = []
                    for entrada in entradas_individuales:
                        resultados.append(await descargar(entrada))
                else:
                    resultados = [await descargar(entrada_conjunta)]

            duracion = time.perf_counter() - inicio
            filas = [fila for resultado in resultados for fila in resultado["descargas"]]
            if len(filas) != len(urls) or any(
                "error" in fila or fila["codigo"] >= 400 for fila in filas
            ):
                raise RuntimeError(f"Descargas incompletas o fallidas: {filas}")

            muestras[modo].append(duracion)
            print(f"Repetición {repeticion + 1}: {modo} = {duracion:.4f} s")

    secuencial = resumen(muestras["secuencial"])
    concurrente = resumen(muestras["concurrente"])
    datos = {
        "medicion": "concurrencia_io",
        "entorno": entorno(),
        "condiciones": {
            "cantidad_descargas": len(urls),
            "repeticiones": args.repeticiones,
            "origen": "externo" if args.url else "servidor local controlado",
            "urls": urls,
            "demora_local_segundos": None if args.url else args.demora,
            "limite_escenario_segundos": args.timeout,
            "alcance": "Función descargar del proyecto, sin API ni cola",
            "secuencial": "Una llamada a descargar por URL, esperando cada resultado",
            "concurrente": "Una llamada a descargar con todas las URLs",
            "nota": (
                "Incluye creación de clientes: uno por llamada a descargar. "
                "HTTPX conserva su timeout de red predeterminado."
            ),
        },
        "secuencial_segundos": secuencial,
        "concurrente_segundos": concurrente,
        "speedup_medianas": secuencial["mediana"] / concurrente["mediana"],
    }
    print(f"Speedup: {datos['speedup_medianas']:.2f}x")
    guardar(datos, args.salida)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cantidad", type=entero_positivo, default=20)
    parser.add_argument("--repeticiones", type=entero_positivo, default=3)
    parser.add_argument("--demora", type=positivo, default=0.2)
    parser.add_argument("--timeout", type=positivo, default=30, help="Límite total por escenario")
    parser.add_argument("--url", action="append", help="Repetible; reemplaza el servidor local")
    parser.add_argument("--salida", default="mediciones/resultados/concurrencia_io.json")
    args = parser.parse_args()

    if args.url:
        urls = [args.url[i % len(args.url)] for i in range(args.cantidad)]
        asyncio.run(medir(args, urls))
    else:
        with servidor_descargas(args.demora) as puerto:
            urls = [f"http://127.0.0.1:{puerto}/archivo/{i}" for i in range(args.cantidad)]
            asyncio.run(medir(args, urls))


if __name__ == "__main__":
    main()
