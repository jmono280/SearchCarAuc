"""Stub del scraper para ACV Auctions (subastas mayoristas de vehículos EE.UU.)."""

from __future__ import annotations

import logging
from typing import Any

from app.models.search import SearchQuery
from app.models.vehicle import Vehicle
from app.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class ACVScraper(BaseScraper):
    """Placeholder para ACV Auctions."""

    name = "ACV"

    def __init__(self, provider_settings: dict[str, Any] | None = None) -> None:
        super().__init__(provider_settings)
        self.name = self.provider_settings.get("name", "ACV")

    async def scratch(self, query: SearchQuery) -> list[Vehicle]:
        logger.warning(
            "[%s] Scraper no implementado. Configura la URL y credenciales para activarlo.",
            self.name,
        )
        return []
