"""Modelo de un vehículo individual devuelto por un scraper."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Vehicle(BaseModel):
    """Representa un vehículo unificado, independiente del sitio de origen."""

    titulo: str = Field(..., description="Título completo, ej. '2012 DODGE JOURNEY CREW'")
    anio: int | None = Field(default=None, description="Año del vehículo")
    marca: str | None = Field(default=None, description="Marca")
    modelo: str | None = Field(default=None, description="Modelo")

    precio: float | None = Field(default=None, description="Precio Buy Now si está disponible")
    moneda: str | None = Field(default="USD", description="Moneda del precio")

    odometro: str | None = Field(default=None, description="Odómetro, ej. '173,064 mi'")
    vin: str | None = Field(default=None, description="VIN (puede venir enmascarado)")
    motor: str | None = Field(default=None, description="Descripción del motor")
    dano_primario: str | None = Field(default=None, description="Daño primario")
    tipo: str | None = Field(default=None, description="Tipo de vehículo")
    sucursal: str | None = Field(default=None, description="Sucursal/branch de la subasta")

    imagen_url: str | None = Field(default=None, description="URL de la imagen principal")
    detalle_url: str | None = Field(default=None, description="URL a la página de detalle")

    fuente: str = Field(default="IAAI", description="Sitio de origen del dato")
