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


def hashear(entrada: HashearEntrada):
    datos = entrada.texto.encode("utf-8")

    for _ in range(entrada.iteraciones):
        datos = hashlib.sha256(datos).digest()

    return {
        "hash": datos.hex(),
        "iteraciones": entrada.iteraciones,
    }