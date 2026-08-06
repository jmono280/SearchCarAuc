"""Stub del scraper para Manheim (coche de subastas mayorista EE.UU.).

Este archivo es un placeholder: la implementación real depende del flujo de
login y de la estructura HTML/API de Manheim. Para Atlanta, Georgia, el
proveedor relevante es Manheim Atlanta / Manheim.com.
"""

from __future__ import annotations

import logging
from typing import Any

from app.models.search import SearchQuery
from app.models.vehicle import Vehicle
from app.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class ManheimScraper(BaseScraper):
    """Placeholder para Manheim."""

    name = "Manheim"

    def __init__(self, provider_settings: dict[str, Any] | None = None) -> None:
        super().__init__(provider_settings)
        self.name = self.provider_settings.get("name", "Manheim")

    async def scratch(self, query: SearchQuery) -> list[Vehicle]:
        """Devuelve lista vacía con un error explicativo hasta implementar."""
        logger.warning(
            "[%s] Scraper no implementado. Configura la URL y credenciales para activarlo.",
            self.name,
        )
        return []
