"""Stub del scraper para OpenLane (plataforma de subastas de Cox Automotive)."""

from __future__ import annotations

import logging
from typing import Any

from app.models.search import SearchQuery
from app.models.vehicle import Vehicle
from app.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class OpenLaneScraper(BaseScraper):
    """Placeholder para OpenLane."""

    name = "OpenLane"

    def __init__(self, provider_settings: dict[str, Any] | None = None) -> None:
        super().__init__(provider_settings)
        self.name = self.provider_settings.get("name", "OpenLane")

    async def scratch(self, query: SearchQuery) -> list[Vehicle]:
        logger.warning(
            "[%s] Scraper no implementado. Configura la URL y credenciales para activarlo.",
            self.name,
        )
        return []
