"""ViewModel: orquesta los scrapers y unifica los resultados para la vista."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.config import settings
from app.models.results import SearchResults
from app.models.search import SearchQuery
from app.scrapers.base_scraper import BaseScraper
from app.scrapers.providers.acv import ACVScraper
from app.scrapers.providers.iaai import IAAIScraper
from app.scrapers.providers.manheim import ManheimScraper
from app.scrapers.providers.openlane import OpenLaneScraper

logger = logging.getLogger(__name__)

# Registro de scrapers disponibles por nombre clave.
_PROVIDER_REGISTRY: dict[str, type[BaseScraper]] = {
    "iaai": IAAIScraper,
    "manheim": ManheimScraper,
    "acv": ACVScraper,
    "openlane": OpenLaneScraper,
}


def build_scrapers() -> list[BaseScraper]:
    """Construye una lista de scrapers habilitados según la configuración."""
    scrapers: list[BaseScraper] = []
    for provider_key in settings.enabled_providers:
        scraper_cls = _PROVIDER_REGISTRY.get(provider_key)
        if not scraper_cls:
            logger.warning("Proveedor desconocido: %s", provider_key)
            continue

        provider_cfg = settings.provider_settings(provider_key)
        if not provider_cfg.get("url") and provider_key != "iaai":
            logger.warning(
                "[%s] Proveedor habilitado pero sin URL configurada; se omite.",
                provider_key,
            )
            continue

        scrapers.append(scraper_cls(provider_cfg))

    return scrapers


class ScraperViewModel:
    """Mantiene el estado de la búsqueda actual y coordina los scrapers.

    Dispara todos los scrapers en paralelo con asyncio.gather y captura los
    errores por scraper para que la vista nunca reciba una excepción sin manejar.
    """

    def __init__(self, scrapers: list[BaseScraper] | None = None) -> None:
        self.scrapers: list[BaseScraper] = scrapers or build_scrapers()
        self.last_query: SearchQuery | None = None
        self.last_results: SearchResults | None = None

    async def search(self, query: SearchQuery) -> SearchResults:
        """Ejecuta la búsqueda en todos los scrapers de forma concurrente."""
        self.last_query = query
        results = SearchResults()

        if not self.scrapers:
            results.add_error("No hay scrapers habilitados.")
            return results

        tasks = [scraper.scratch(query) for scraper in self.scrapers]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        for scraper, outcome in zip(self.scrapers, outcomes):
            if isinstance(outcome, Exception):
                mensaje = f"{scraper.name}: {outcome.__class__.__name__}: {outcome}"
                logger.warning("Scraper falló: %s", mensaje)
                results.add_error(mensaje)
            else:
                results.add_items(outcome)

        self.last_results = results
        return results
