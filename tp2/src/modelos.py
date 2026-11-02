from datetime import datetime, timezone
from uuid import UUID, uuid4
from enum import Enum

from typing import Annotated, Literal

from pydantic import BaseModel, Field, HttpUrl

class EstadoTarea(str, Enum):
    PENDIENTE = "pendiente"
    EJECUTANDO = "ejecutando"
    COMPLETADA = "completada"
    FALLIDA = "fallida"
    CANCELADA = "cancelada"


class DescargarEntrada(BaseModel):
    tipo: Literal["descargar"]
    urls: list[HttpUrl] = Field(min_length=1)
    timeout: float = Field(default=30, gt=0, allow_inf_nan=False)


class HashearEntrada(BaseModel):
    tipo: Literal["hashear"]
    texto: str
    iteraciones: int = Field(gt=0)
    timeout: float = Field(default=30, gt=0, allow_inf_nan=False)


class EsperarEntrada(BaseModel):
    tipo: Literal["esperar"]
    segundos: float = Field(ge=0, allow_inf_nan=False)
    timeout: float = Field(default=30, gt=0, allow_inf_nan=False)


class Tarea(BaseModel):
        id: UUID = Field(default_factory=uuid4)
        entrada: DescargarEntrada | HashearEntrada | EsperarEntrada
        estado: EstadoTarea = EstadoTarea.PENDIENTE

        creada_en: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

        iniciada_en: datetime | None = None
        finalizada_en: datetime | None = None

        resultado: dict | None = None
        error: str | None = None

