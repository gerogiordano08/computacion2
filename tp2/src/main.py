import logging
import os
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, HTTPException

from .gestor import GestorTareas
from .modelos import (
    DescargarEntrada,
    EsperarEntrada,
    EstadoTarea,
    HashearEntrada,
    Tarea,
)


Entrada = DescargarEntrada | HashearEntrada | EsperarEntrada

logging.basicConfig(level=logging.INFO)

gestor = GestorTareas(
    cantidad_workers=int(os.getenv("CANTIDAD_WORKERS", "4")),
    procesos_cpu=int(os.getenv("PROCESOS_CPU", "2")),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await gestor.iniciar()

    try:
        yield
    finally:
        await gestor.detener()


app = FastAPI(lifespan=lifespan)


@app.post("/tareas", status_code=202)
async def post_tarea(entrada: Entrada):
    try:
        tarea = await gestor.crear_tarea(entrada)
    except RuntimeError as error:
        raise HTTPException(
            status_code=503,
            detail=str(error),
        ) from error

    return {
        "id": tarea.id,
        "estado": tarea.estado,
    }


@app.get("/tareas", response_model=list[Tarea])
async def get_tareas(estado: EstadoTarea | None = None):
    return gestor.listar_tareas(estado)


@app.get("/tareas/{tarea_id}", response_model=Tarea)
async def get_tarea(tarea_id: UUID):
    try:
        return gestor.obtener_tarea(tarea_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404,
            detail="Tarea no encontrada",
        ) from error


@app.delete("/tareas/{tarea_id}", response_model=Tarea)
async def delete_tarea(tarea_id: UUID):
    try:
        return await gestor.cancelar_tarea(tarea_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404,
            detail="Tarea no encontrada",
        ) from error


@app.get("/estadisticas")
async def get_estadisticas():
    return gestor.obtener_estadisticas()
