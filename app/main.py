"""Punto de entrada FastAPI (capa View/Controller del MVVM).

Sirve el formulario HTML en `/`, expone el endpoint de búsqueda en `/api/search`
y monta un servidor MCP en `/mcp/sse` para clientes como Claude Desktop.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Route

from app.mcp_server import mcp_server
from app.models.results import SearchResults
from app.models.search import SearchQuery
from app.viewmodels.scraper_viewmodel import ScraperViewModel

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"

app = FastAPI(title="Car Scraper MVVM", version="0.1.0")


def get_viewmodel() -> ScraperViewModel:
    """Crea un ViewModel nuevo por petición (estado de búsqueda aislado)."""
    return ScraperViewModel()


@app.get("/")
async def index() -> FileResponse:
    """Sirve la vista única (formulario + tabla de resultados)."""
    return FileResponse(TEMPLATES_DIR / "index.html")


@app.post("/api/search", response_model=SearchResults)
async def search(query: SearchQuery) -> SearchResults:
    """Recibe la consulta del formulario y devuelve los resultados unificados."""
    viewmodel = get_viewmodel()
    return await viewmodel.search(query)


# --- Servidor MCP (montado como sub-aplicación Starlette) ---

# Transporte SSE para el servidor MCP.
# El endpoint POST de mensajes será `/messages?session_id=...` dentro del mount.
mcp_transport = SseServerTransport("/messages")


class _McpSseAsgi:
    """ASGI handler para el endpoint SSE del servidor MCP."""

    async def __call__(self, scope, receive, send):
        async with mcp_transport.connect_sse(scope, receive, send) as (
            read_stream,
            write_stream,
        ):
            await mcp_server.run(
                read_stream,
                write_stream,
                mcp_server.create_initialization_options(),
            )


class _McpMessagesAsgi:
    """ASGI handler para el endpoint POST de mensajes del servidor MCP."""

    async def __call__(self, scope, receive, send):
        await mcp_transport.handle_post_message(scope, receive, send)


mcp_app = Starlette(
    routes=[
        Route("/sse", endpoint=_McpSseAsgi(), methods=["GET"]),
        Route("/messages", endpoint=_McpMessagesAsgi(), methods=["POST"]),
    ]
)

# Monta el MCP server bajo el prefijo /mcp.
app.mount("/mcp", mcp_app)
