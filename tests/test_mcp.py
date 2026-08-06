"""Test de conexión MCP vía SSE al servidor car-scraper.

Uso:
    .venv/bin/python tests/test_mcp.py

Requiere que el servidor FastAPI esté corriendo en http://localhost:8000
"""
from __future__ import annotations

import asyncio
import sys

from mcp.client.session import ClientSession
from mcp.client.sse import sse_client


MCP_URL = "http://localhost:8000/mcp/sse"


async def main() -> int:
    print(f"Conectando a {MCP_URL}...")

    async with sse_client(MCP_URL) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            print("Conexión MCP inicializada.\n")

            tools = await session.list_tools()
            print("Herramientas disponibles:")
            for tool in tools.tools:
                print(f"  - {tool.name}: {tool.description[:80]}...")

            print("\nLlamando search_vehicles(marca='Honda', modelo='Civic', ...)")
            result = await session.call_tool(
                "search_vehicles",
                {
                    "marca": "Honda",
                    "modelo": "Civic",
                    "anio_min": 2015,
                    "anio_max": 2016,
                    "page_size": 3,
                },
            )

            print("\nResultado del MCP:")
            for content in result.content:
                if hasattr(content, "text"):
                    print(content.text)

            if result.is_error:
                print("\n⚠️ La herramienta reportó error.", file=sys.stderr)
                return 1

    print("\n✅ MCP funciona correctamente.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
