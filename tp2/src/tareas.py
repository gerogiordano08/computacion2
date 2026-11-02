from .modelos import EsperarEntrada, DescargarEntrada, HashearEntrada
import httpx
import asyncio
import hashlib

async def esperar(entrada: EsperarEntrada):
    await asyncio.sleep(entrada.segundos)
    return { "segundos": entrada.segundos}


async def descargar(entrada: DescargarEntrada):
    async with httpx.AsyncClient() as cliente:
        respuestas = await asyncio.gather(
            *(cliente.get(str(url)) for url in entrada.urls),
            return_exceptions=True,
        )

    resultado = {"descargas": []}

    for url, respuesta in zip(entrada.urls, respuestas):
        if isinstance(respuesta, httpx.RequestError):
            resultado["descargas"].append({
                "url": str(url),
                "error": str(respuesta),
                "tipo_error": type(respuesta).__name__,
            })
        elif isinstance(respuesta, BaseException):
            raise respuesta
        else:
            resultado["descargas"].append({
                "url": str(url),
                "codigo": respuesta.status_code,
                "tamano": len(respuesta.content),
                "duracion": respuesta.elapsed.total_seconds(),
            })
    return resultado        


class HashCancelado(Exception):
    pass


def hashear(entrada: HashearEntrada, cancelacion):
    datos = entrada.texto.encode("utf-8")

    for numero in range(entrada.iteraciones):
        if numero % 10_000 == 0 and cancelacion.is_set():
            raise HashCancelado("Cálculo cancelado")

        datos = hashlib.sha256(datos).digest()

    if cancelacion.is_set():
        raise HashCancelado("Cálculo cancelado")

    return {
        "hash": datos.hex(),
        "iteraciones": entrada.iteraciones,
    }