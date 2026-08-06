"""Modelo del resultado unificado de una búsqueda (todos los scrapers)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.vehicle import Vehicle


class SearchResults(BaseModel):
    """Resultado consolidado que el ViewModel entrega a la vista.

    Nunca debe fallar: los errores por scraper se acumulan en `errores`
    para que el frontend pueda seguir pintando los resultados que sí llegaron.
    """

    items: list[Vehicle] = Field(default_factory=list, description="Vehículos encontrados")
    total: int = Field(default=0, description="Cantidad de vehículos devueltos")
    errores: list[str] = Field(
        default_factory=list,
        description="Mensajes de error por scraper que falló",
    )

    def add_items(self, items: list[Vehicle]) -> None:
        """Agrega vehículos y recalcula el total."""
        self.items.extend(items)
        self.total = len(self.items)

    def add_error(self, mensaje: str) -> None:
        """Registra un error sin interrumpir la búsqueda."""
        self.errores.append(mensaje)
