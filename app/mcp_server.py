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
from app.models.saved_search import SavedSearchCreate
from app.models.search import SearchQuery
from app.repositories.saved_search_repository import SavedSearchRepository
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
        "buy_now": {
            "type": "boolean",
            "description": "True para filtrar solo vehículos con precio Buy Now/Comprar ahora y habilitar precio_min/precio_max.",
            "default": False,
        },
        "odometro_min": {
            "type": "integer",
            "description": "Odómetro mínimo en millas.",
        },
        "odometro_max": {
            "type": "integer",
            "description": "Odómetro máximo en millas.",
        },
        "page_size": {
            "type": "integer",
            "description": "Cantidad de resultados por página (máximo 100).",
            "default": 50,
        },
    },
    "required": ["marca"],
}

_SAVE_FILTER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "nombre": {
            "type": "string",
            "description": "Nombre descriptivo para guardar este filtro. Ej: Honda Civic 2015-2016.",
        },
        **_SEARCH_VEHICLE_SCHEMA["properties"],
    },
    "required": ["nombre", "marca"],
}

_RUN_FILTER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "filter_id": {
            "type": "string",
            "description": "ID del filtro guardado a ejecutar.",
        },
    },
    "required": ["filter_id"],
}

_DELETE_FILTER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "filter_id": {
            "type": "string",
            "description": "ID del filtro guardado a eliminar.",
        },
    },
    "required": ["filter_id"],
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
        if v.acv is not None:
            details.append(f"**ACV:** ${v.acv:,.0f} {v.moneda or 'USD'}")
        if v.odometro:
            details.append(f"**Odómetro:** {v.odometro}")
        if v.motor:
            details.append(f"**Motor:** {v.motor}")
        if v.vin:
            details.append(f"**VIN:** {v.vin}")
        if v.dano_primario:
            details.append(f"**Daño primario:** {v.dano_primario}")
        if v.dano_secundario:
            details.append(f"**Daño secundario:** {v.dano_secundario}")
        if v.estado:
            details.append(f"**Estado:** {v.estado}")
        if v.subasta:
            details.append(f"**Subasta:** {v.subasta}")
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
            ),
            Tool(
                name="list_filters",
                description="Lista los filtros de búsqueda guardados por el usuario.",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="save_filter",
                description=(
                    "Guarda un filtro de búsqueda con un nombre para reutilizarlo "
                    "posteriormente. NO guarda resultados, solo los criterios."
                ),
                inputSchema=_SAVE_FILTER_SCHEMA,
            ),
            Tool(
                name="run_filter",
                description=(
                    "Ejecuta un filtro de búsqueda guardado y devuelve resultados "
                    "frescos de los proveedores habilitados."
                ),
                inputSchema=_RUN_FILTER_SCHEMA,
            ),
            Tool(
                name="delete_filter",
                description="Elimina un filtro de búsqueda guardado por su ID.",
                inputSchema=_DELETE_FILTER_SCHEMA,
            ),
        ]
    )


async def _run_search(arguments: dict[str, Any]) -> CallToolResult:
    """Ejecuta search_vehicles y devuelve los resultados formateados."""
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


async def _list_filters() -> CallToolResult:
    """Lista los filtros guardados."""
    try:
        filtros = await SavedSearchRepository.list_all()
    except Exception as exc:
        logger.exception("Error listando filtros via MCP")
        return CallToolResult(
            content=[TextContent(text=f"Error interno al listar filtros: {exc}")],
            is_error=True,
        )

    if not filtros:
        return CallToolResult(content=[TextContent(text="No hay filtros guardados.")])

    lines = ["**Filtros guardados:**"]
    for f in filtros:
        q = f.query
        resumen = f"{q.marca}"
        if q.modelo:
            resumen += f" {q.modelo}"
        if q.anio_min is not None and q.anio_max is not None:
            resumen += f" ({q.anio_min}-{q.anio_max})"
        elif q.anio is not None:
            resumen += f" ({q.anio})"
        lines.append(f"- `{f.id}` — **{f.nombre}**: {resumen}")
    return CallToolResult(content=[TextContent(text="\n".join(lines))])


async def _save_filter(arguments: dict[str, Any]) -> CallToolResult:
    """Guarda un filtro nuevo a partir de los criterios recibidos."""
    args = dict(arguments)
    nombre = args.pop("nombre", None)
    if not nombre:
        return CallToolResult(
            content=[TextContent(text="El campo 'nombre' es requerido.")],
            is_error=True,
        )

    try:
        query = SearchQuery(**args)
    except Exception as exc:
        logger.warning("Parámetros inválidos en save_filter: %s", exc)
        return CallToolResult(
            content=[TextContent(text=f"Parámetros inválidos: {exc}")],
            is_error=True,
        )

    try:
        saved = await SavedSearchRepository.create(
            SavedSearchCreate(nombre=nombre, query=query)
        )
    except Exception as exc:
        logger.exception("Error guardando filtro via MCP")
        return CallToolResult(
            content=[TextContent(text=f"Error interno al guardar el filtro: {exc}")],
            is_error=True,
        )

    return CallToolResult(
        content=[TextContent(text=f"Filtro guardado: `{saved.id}` — {saved.nombre}")]
    )


async def _run_filter(arguments: dict[str, Any]) -> CallToolResult:
    """Ejecuta un filtro guardado y devuelve resultados frescos."""
    filter_id = arguments.get("filter_id")
    if not filter_id:
        return CallToolResult(
            content=[TextContent(text="El campo 'filter_id' es requerido.")],
            is_error=True,
        )

    try:
        filt = await SavedSearchRepository.get(filter_id)
    except Exception as exc:
        logger.exception("Error obteniendo filtro via MCP")
        return CallToolResult(
            content=[TextContent(text=f"Error interno al obtener el filtro: {exc}")],
            is_error=True,
        )

    if not filt:
        return CallToolResult(
            content=[TextContent(text=f"No se encontró el filtro `{filter_id}`.")],
            is_error=True,
        )

    try:
        viewmodel = ScraperViewModel()
        results = await viewmodel.search(filt.query)
    except Exception as exc:
        logger.exception("Error ejecutando filtro guardado via MCP")
        return CallToolResult(
            content=[TextContent(text=f"Error interno al ejecutar el filtro: {exc}")],
            is_error=True,
        )

    return CallToolResult(content=[TextContent(text=_format_results(results))])


async def _delete_filter(arguments: dict[str, Any]) -> CallToolResult:
    """Elimina un filtro guardado por su ID."""
    filter_id = arguments.get("filter_id")
    if not filter_id:
        return CallToolResult(
            content=[TextContent(text="El campo 'filter_id' es requerido.")],
            is_error=True,
        )

    try:
        deleted = await SavedSearchRepository.delete(filter_id)
    except Exception as exc:
        logger.exception("Error eliminando filtro via MCP")
        return CallToolResult(
            content=[TextContent(text=f"Error interno al eliminar el filtro: {exc}")],
            is_error=True,
        )

    if not deleted:
        return CallToolResult(
            content=[TextContent(text=f"No se encontró el filtro `{filter_id}`.")],
            is_error=True,
        )

    return CallToolResult(
        content=[TextContent(text=f"Filtro `{filter_id}` eliminado correctamente.")]
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

    if name == "search_vehicles":
        return await _run_search(arguments)
    if name == "list_filters":
        return await _list_filters()
    if name == "save_filter":
        return await _save_filter(arguments)
    if name == "run_filter":
        return await _run_filter(arguments)
    if name == "delete_filter":
        return await _delete_filter(arguments)

    return CallToolResult(
        content=[TextContent(text=f"Herramienta desconocida: {name}")],
        is_error=True,
    )


# Instancia pública del servidor MCP.
mcp_server = Server(
    name="car-scraper",
    version="0.1.0",
    title="Buscador de vehículos IAAI",
    description="Busca vehículos en subastas de IAAI usando el scraper FastAPI.",
    on_list_tools=_handle_list_tools,
    on_call_tool=_handle_call_tool,
)
