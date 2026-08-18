"""Modelo para filtros de búsqueda guardados.

Un "filtro guardado" persiste los criterios de búsqueda (`SearchQuery`) con un
nombre, de forma que el usuario pueda reutilizarlos y ejecutar la búsqueda
nuevamente sin rellenar el formulario. NO almacena los resultados.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field

from app.models.search import SearchQuery


class SavedSearch(BaseModel):
    """Filtro de búsqueda guardado."""

    id: str = Field(default_factory=lambda: str(uuid4()), description="Identificador único")
    nombre: str = Field(..., min_length=1, description="Nombre descriptivo del filtro")
    query: SearchQuery = Field(..., description="Criterios de búsqueda a persistir")
    creado_en: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Fecha de creación (UTC)",
    )
    actualizado_en: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Fecha de última modificación (UTC)",
    )


class SavedSearchCreate(BaseModel):
    """Payload para crear un filtro guardado."""

    nombre: str = Field(..., min_length=1)
    query: SearchQuery


class SavedSearchUpdate(BaseModel):
    """Payload para actualizar un filtro guardado."""

    nombre: str | None = None
    query: SearchQuery | None = None
