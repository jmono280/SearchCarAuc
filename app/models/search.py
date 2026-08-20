"""Modelo de la consulta de búsqueda enviada por el usuario desde el formulario."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator


class SearchQuery(BaseModel):
    """Datos que llegan desde el formulario de la vista.

    Campos básicos: marca, modelo, año, tipo.
    Filtros avanzados: rango de año, rango de precio, ubicación + radio,
    paginación.
    """

    # Campos básicos
    marca: str = Field(..., min_length=1, description="Marca del vehículo, ej. Toyota")
    modelo: str | None = Field(default=None, description="Modelo del vehículo, ej. Corolla")
    anio: int | None = Field(
        default=None,
        ge=1900,
        le=2100,
        description="Año exacto del vehículo (legado; preferir anio_min/anio_max)",
    )
    tipo: str | None = Field(
        default=None,
        description="Tipo de auto: Cars, SUVs, PickupTrucks, etc.",
    )

    # Filtros avanzados
    anio_min: int | None = Field(
        default=None,
        ge=1900,
        le=2100,
        description="Año mínimo",
    )
    anio_max: int | None = Field(
        default=None,
        ge=1900,
        le=2100,
        description="Año máximo",
    )
    buy_now: bool = Field(
        default=False,
        description="True = filtrar solo vehículos con precio Buy Now/Comprar ahora",
    )
    precio_min: float | None = Field(
        default=None,
        ge=0,
        description="Precio mínimo (USD). Solo aplica cuando buy_now=True",
    )
    precio_max: float | None = Field(
        default=None,
        ge=0,
        description="Precio máximo (USD). Solo aplica cuando buy_now=True",
    )
    odometro_min: int | None = Field(
        default=None,
        ge=0,
        description="Odómetro mínimo en millas",
    )
    odometro_max: int | None = Field(
        default=None,
        ge=0,
        description="Odómetro máximo en millas",
    )
    zip: str | None = Field(
        default=None,
        min_length=5,
        max_length=10,
        description="Código postal (ZIP) de referencia para búsqueda por distancia",
    )
    radio_millas: int | None = Field(
        default=None,
        ge=1,
        le=5000,
        description="Radio de búsqueda en millas desde el ZIP",
    )

    # Paginación
    page: int = Field(
        default=1,
        ge=1,
        description="Número de página",
    )
    page_size: int = Field(
        default=50,
        ge=1,
        le=100,
        description="Resultados por página (máx. 100)",
    )

    @field_validator("marca", "modelo", "tipo", "zip", mode="before")
    @classmethod
    def _limpiar_texto(cls, v: object) -> object:
        """Recorta espacios y convierte cadenas vacías en None."""
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v

    @model_validator(mode="after")
    def _validar_rangos(self) -> "SearchQuery":
        """Garantiza coherencia entre rangos."""
        if self.anio_min is not None and self.anio_max is not None and self.anio_min > self.anio_max:
            raise ValueError("anio_min no puede ser mayor que anio_max")
        if self.precio_min is not None and self.precio_max is not None and self.precio_min > self.precio_max:
            raise ValueError("precio_min no puede ser mayor que precio_max")
        if self.odometro_min is not None and self.odometro_max is not None and self.odometro_min > self.odometro_max:
            raise ValueError("odometro_min no puede ser mayor que odometro_max")
        if (self.zip is None) != (self.radio_millas is None):
            raise ValueError("zip y radio_millas deben venir juntos o ninguno")
        return self

    def to_full_search(self) -> str:
        """Combina los campos básicos en un único texto libre para el parámetro FullSearch de IAAI.

        Ej: SearchQuery(marca="Toyota", modelo="Corolla", anio=2015) -> "2015 Toyota Corolla"
        """
        partes: list[str] = []
        if self.anio:
            partes.append(str(self.anio))
        if self.marca:
            partes.append(self.marca)
        if self.modelo:
            partes.append(self.modelo)
        return " ".join(partes).strip()

    def rango_anio(self) -> tuple[int | None, int | None]:
        """Resuelve el rango de año efectivo.

        Si se envió `anio` exacto (sin rango), se usa ese valor como mínimo y máximo.
        """
        if self.anio is not None and self.anio_min is None and self.anio_max is None:
            return self.anio, self.anio
        return self.anio_min, self.anio_max
