"""Servidor MCP (Model Context Protocol) integrado con el scraper de vehículos.

Expone la herramienta `search_vehicles` para que clientes MCP como Claude Desktop
puedan buscar vehículos en IAAI usando lenguaje natural.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server import Server
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool

from app.models.results import SearchResults
from app.models.search import SearchQuery
from app.viewmodels.scraper_viewmodel import ScraperViewModel

logger = logging.getLogger(__name__)

# Schema JSON para la herramienta MCP.
_SEARCH_VEHICLE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "marca": {
            "type": "string",
            "description": "Marca del vehículo (requerido). Ej: Honda, Toyota, Ford.",
        },
        "modelo": {
            "type": "string",
            "description": "Modelo del vehículo. Ej: Civic, Corolla, F-150.",
        },
        "anio": {
            "type": "integer",
            "description": "Año exacto del vehículo.",
        },
        "anio_min": {
            "type": "integer",
            "description": "Año mínimo (inclusive).",
        },
        "anio_max": {
            "type": "integer",
            "description": "Año máximo (inclusive).",
        },
        "precio_min": {
            "type": "number",
            "description": "Precio mínimo Buy Now en USD.",
        },
        "precio_max": {
            "type": "number",
            "description": "Precio máximo Buy Now en USD.",
        },
        "zip": {
            "type": "string",
            "description": "Código postal de EE.UU. para búsqueda por distancia.",
        },
        "radio_millas": {
            "type": "integer",
            "description": "Radio de búsqueda en millas desde el ZIP.",
        },
        "page_size": {
            "type": "integer",
            "description": "Cantidad de resultados por página (máximo 100).",
            "default": 50,
        },
    },
    "required": ["marca"],
}


def _format_results(results: SearchResults) -> str:
    """Convierte SearchResults a markdown legible para la IA."""
    if results.errores:
        errores = "\n".join(f"- ⚠️ {e}" for e in results.errores)
    else:
        errores = ""

    if not results.items:
        return f"No se encontraron vehículos.\n{errores}".strip()

    lines: list[str] = [f"**{results.total} vehículo(s) encontrado(s)**\n"]

    for v in results.items:
        lines.append(f"### {v.titulo}")
        if v.imagen_url:
            lines.append(f"![{v.titulo}]({v.imagen_url})")
        details: list[str] = []
        if v.anio:
            details.append(f"**Año:** {v.anio}")
        if v.precio is not None:
            details.append(f"**Precio:** ${v.precio:,.0f} {v.moneda or 'USD'}")
        else:
            details.append("**Precio:** no disponible (Buy Now)")
        if v.odometro:
            details.append(f"**Odómetro:** {v.odometro}")
        if v.motor:
            details.append(f"**Motor:** {v.motor}")
        if v.vin:
            details.append(f"**VIN:** {v.vin}")
        if v.sucursal:
            details.append(f"**Sucursal:** {v.sucursal}")
        if v.detalle_url:
            details.append(f"**[Ver detalle]({v.detalle_url})**")
        lines.append(" | ".join(details))
        lines.append("")

    if errores:
        lines.append("**Avisos:**")
        lines.append(errores)

    return "\n".join(lines)


async def _handle_list_tools(ctx=None, params=None) -> ListToolsResult:
    """Devuelve las herramientas disponibles para el cliente MCP."""
    return ListToolsResult(
        tools=[
            Tool(
                name="search_vehicles",
                description=(
                    "Busca vehículos en subastas de IAAI por marca, modelo, año, "
                    "rango de precio Buy Now y ubicación. Devuelve resultados con "
                    "imagen, precio, odómetro, motor, VIN y enlace al detalle."
                ),
                inputSchema=_SEARCH_VEHICLE_SCHEMA,
            )
        ]
    )


async def _handle_call_tool(ctx=None, params=None) -> CallToolResult:
    """Ejecuta la herramienta solicitada por el cliente MCP."""
    if params is None:
        params = {}
    if hasattr(params, "name"):
        name = params.name
        arguments = params.arguments or {}
    else:
        name = params.get("name")
        arguments = params.get("arguments") or {}

    if name != "search_vehicles":
        return CallToolResult(
            content=[TextContent(text=f"Herramienta desconocida: {name}")],
            is_error=True,
        )

    try:
        query = SearchQuery(**arguments)
    except Exception as exc:
        logger.warning("Parámetros inválidos en search_vehicles: %s", exc)
        return CallToolResult(
            content=[TextContent(text=f"Parámetros inválidos: {exc}")],
            is_error=True,
        )

    try:
        viewmodel = ScraperViewModel()
        results = await viewmodel.search(query)
    except Exception as exc:
        logger.exception("Error ejecutando search_vehicles via MCP")
        return CallToolResult(
            content=[TextContent(text=f"Error interno al buscar vehículos: {exc}")],
            is_error=True,
        )

    return CallToolResult(content=[TextContent(text=_format_results(results))])


# Instancia pública del servidor MCP.
mcp_server = Server(
    name="car-scraper",
    version="0.1.0",
    title="Buscador de vehículos IAAI",
    description="Busca vehículos en subastas de IAAI usando el scraper FastAPI.",
    on_list_tools=_handle_list_tools,
    on_call_tool=_handle_call_tool,
)
