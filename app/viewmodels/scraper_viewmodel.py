"""ViewModel: orquesta los scrapers y unifica los resultados para la vista."""

from __future__ import annotations

import asyncio
import logging

from app.models.results import SearchResults
from app.models.search import SearchQuery
from app.scrapers.base_scraper import BaseScraper
from app.scrapers.iaai_scraper import IAAIScraper

logger = logging.getLogger(__name__)


class ScraperViewModel:
    """Mantiene el estado de la búsqueda actual y coordina los scrapers.

    Dispara todos los scrapers en paralelo con asyncio.gather y captura los
    errores por scraper para que la vista nunca reciba una excepción sin manejar.
    """

    def __init__(self, scrapers: list[BaseScraper] | None = None) -> None:
        # Por ahora solo IAAI; la arquitectura permite agregar más scrapers.
        self.scrapers: list[BaseScraper] = scrapers or [IAAIScraper()]
        self.last_query: SearchQuery | None = None
        self.last_results: SearchResults | None = None

    async def search(self, query: SearchQuery) -> SearchResults:
        """Ejecuta la búsqueda en todos los scrapers de forma concurrente."""
        self.last_query = query
        results = SearchResults()

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
