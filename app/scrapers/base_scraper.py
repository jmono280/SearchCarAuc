"""Clase base abstracta para todos los scrapers (capa Model/Servicios del MVVM)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.search import SearchQuery
from app.models.vehicle import Vehicle

# Headers de un navegador real para reducir el riesgo de bloqueo anti-bot.
DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Connection": "keep-alive",
}


class BaseScraper(ABC):
    """Contrato que deben implementar todos los scrapers de sitios."""

    #: Nombre identificador del scraper (aparece como `fuente` en los Vehicle).
    name: str = "base"

    @abstractmethod
    async def scratch(self, query: SearchQuery) -> list[Vehicle]:
        """Ejecuta la búsqueda de forma asíncrona y devuelve la lista de vehículos.

        Debe ser implementado por cada scraper concreto. Se espera que use
        httpx de forma asíncrona y parsee el HTML resultante.
        """
        raise NotImplementedError
