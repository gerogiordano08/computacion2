import asyncio
import logging
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from uuid import UUID

from .modelos import (
    DescargarEntrada,
    EsperarEntrada,
    EstadoTarea,
    HashearEntrada,
    Tarea,
)
from .tareas import descargar, esperar, hashear, HashCancelado


logger = logging.getLogger(__name__)

Entrada = DescargarEntrada | HashearEntrada | EsperarEntrada


class GestorTareas:
    def __init__(
        self,
        cantidad_workers: int = 4,
        procesos_cpu: int = 2,
    ):
        if cantidad_workers < 1 or procesos_cpu < 1:
            raise ValueError("Las cantidades deben ser mayores que cero")

        self.cantidad_workers = cantidad_workers
        self.procesos_cpu = procesos_cpu
        self.manager = None

        self.tareas: dict[UUID, Tarea] = {}
        self.cola: asyncio.Queue[UUID] = asyncio.Queue()
        self.workers: list[asyncio.Task] = []
        self.ejecuciones_activas: dict[UUID, asyncio.Task] = {}

        self.executor: ProcessPoolExecutor | None = None
        self.aceptando_tareas = False

    async def iniciar(self):
        if self.executor is not None:
            raise RuntimeError("El gestor ya está iniciado")

        contexto = multiprocessing.get_context("spawn")

        self.manager = await asyncio.to_thread(contexto.Manager)

        self.executor = ProcessPoolExecutor(
            max_workers=self.procesos_cpu,
            mp_context=contexto,
        )

        for numero in range(self.cantidad_workers):
            worker = asyncio.create_task(
                self._worker(),
                name=f"worker-{numero}",
            )
            self.workers.append(worker)

        self.aceptando_tareas = True

    async def crear_tarea(self, entrada: Entrada) -> Tarea:
        if not self.aceptando_tareas:
            raise RuntimeError("El gestor no acepta nuevas tareas")

        tarea = Tarea(entrada=entrada)
        self.tareas[tarea.id] = tarea
        self.cola.put_nowait(tarea.id)

        return tarea

    def obtener_tarea(self, tarea_id: UUID) -> Tarea:
        return self.tareas[tarea_id]

    def listar_tareas(
        self,
        estado: EstadoTarea | None = None,
    ) -> list[Tarea]:
        return [
            tarea
            for tarea in self.tareas.values()
            if estado is None or tarea.estado == estado
        ]

    async def _ejecutar(self, entrada: Entrada) -> dict:
        if isinstance(entrada, EsperarEntrada):
            return await esperar(entrada)

        if isinstance(entrada, DescargarEntrada):
            return await descargar(entrada)

        if isinstance(entrada, HashearEntrada):
            if self.executor is None or self.manager is None:
                raise RuntimeError("El executor no está iniciado")

            cancelacion = await asyncio.to_thread(self.manager.Event)
            loop = asyncio.get_running_loop()

            futuro = loop.run_in_executor(
                self.executor,
                hashear,
                entrada,
                cancelacion,
            )

            try:
                return await asyncio.shield(futuro)

            except asyncio.CancelledError:
                await asyncio.to_thread(cancelacion.set)

                try:
                    await asyncio.shield(futuro)
                except HashCancelado:
                    pass
                except Exception:
                    logger.exception(
                        "Error del proceso mientras se cancelaba el hash"
                    )

                raise

        raise TypeError("Tipo de tarea no soportado")

    async def _worker(self):
        while True:
            tarea_id = await self.cola.get()
            tarea = self.tareas[tarea_id]

            try:
                # Puede haberse cancelado mientras esperaba en la cola.
                if tarea.estado == EstadoTarea.CANCELADA:
                    continue

                tarea.estado = EstadoTarea.EJECUTANDO
                tarea.iniciada_en = datetime.now(timezone.utc)

                ejecucion = asyncio.create_task(
                    self._ejecutar(tarea.entrada)
                )
                self.ejecuciones_activas[tarea.id] = ejecucion

                try:
                    tarea.resultado = await ejecucion
                    tarea.estado = EstadoTarea.COMPLETADA

                except asyncio.CancelledError:
                    tarea.estado = EstadoTarea.CANCELADA

                    # Si cancelaron al propio worker, debe terminar.
                    if asyncio.current_task().cancelling():
                        raise

                except Exception as error:
                    tarea.estado = EstadoTarea.FALLIDA
                    tarea.error = f"{type(error).__name__}: {error}"
                    logger.exception("Falló la tarea %s", tarea.id)

                finally:
                    tarea.finalizada_en = datetime.now(timezone.utc)
                    self.ejecuciones_activas.pop(tarea.id, None)

            finally:
                self.cola.task_done()
            
    def obtener_estadisticas(self) -> dict:
        totales = {
            estado.value: 0
            for estado in EstadoTarea
        }
        duraciones = []

        for tarea in self.tareas.values():
            totales[tarea.estado.value] += 1

            if (
                tarea.iniciada_en is not None
                and tarea.finalizada_en is not None
            ):
                duracion = (
                    tarea.finalizada_en - tarea.iniciada_en
                ).total_seconds()

                duraciones.append(duracion)

        promedio = (
            sum(duraciones) / len(duraciones)
            if duraciones
            else 0
        )

        return {
            "total": len(self.tareas),
            "por_estado": totales,
            "tiempo_promedio_segundos": promedio,
            "workers_ocupados": totales[
                EstadoTarea.EJECUTANDO.value
            ],
            "cantidad_workers": self.cantidad_workers,
        }

    async def detener(self):
        self.aceptando_tareas = False

        # En esta versión esperamos todas las tareas sin límite.
        await self.cola.join()

        for worker in self.workers:
            worker.cancel()

        await asyncio.gather(
            *self.workers,
            return_exceptions=True,
        )
        self.workers.clear()

        if self.executor is not None:
            await asyncio.to_thread(
                self.executor.shutdown,
                wait=True,
            )
            self.executor = None
        if self.manager is not None:
            await asyncio.to_thread(self.manager.shutdown)
            self.manager = None


    async def cancelar_tarea(self, tarea_id: UUID) -> Tarea:
        tarea = self.obtener_tarea(tarea_id)

        if tarea.estado == EstadoTarea.PENDIENTE:
            tarea.estado = EstadoTarea.CANCELADA
            tarea.finalizada_en = datetime.now(timezone.utc)

        elif tarea.estado == EstadoTarea.EJECUTANDO:
            ejecucion = self.ejecuciones_activas[tarea_id]
            if not ejecucion.done() and not ejecucion.cancelling():
                ejecucion.cancel()

            await asyncio.gather(
                ejecucion,
                return_exceptions=True,
            )

        return tarea