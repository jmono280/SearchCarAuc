"""Clase base abstracta para todos los scrapers (capa Model/Servicios del MVVM)."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from app.models.search import SearchQuery
from app.models.vehicle import Vehicle

# Directorio base para persistir sesiones. Puede sobreescribirse con la
# variable de entorno SCRAPER_SESSION_DIR (útil en desarrollo local).
_DEFAULT_SESSION_DIR = Path(os.environ.get("SCRAPER_SESSION_DIR", "/app/data"))

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
    """Contrato que deben implementar todos los scrapers de sitios.

    Cada proveedor (IAAI, Manheim, ACV, OpenLane...) extiende esta clase.
    Puede opcionalmente implementar ``authenticate`` si el sitio requiere login.
    """

    #: Nombre identificador del scraper (aparece como `fuente` en los Vehicle).
    name: str = "base"

    def __init__(self, provider_settings: dict[str, Any] | None = None) -> None:
        """Inicializa el scraper con la configuración específica del proveedor.

        Args:
            provider_settings: Configuración leída desde ``Settings`` para este
                proveedor (enabled, url, username, password, api_key, etc.).
        """
        self.provider_settings = provider_settings or {}
        self.storage_path = _DEFAULT_SESSION_DIR / (
            f"{self.name.lower().replace(' ', '_')}_session.json"
        )

    @property
    def enabled(self) -> bool:
        """True si el proveedor está habilitado en la configuración."""
        return bool(self.provider_settings.get("enabled", True))

    @property
    def is_configured(self) -> bool:
        """True si el proveedor tiene URL configurada."""
        return bool(self.provider_settings.get("url"))

    async def authenticate(self, page, context) -> bool:
        """Opcional: asegura que el navegador Playwright esté autenticado.

        Los scrapers que requieran login deben sobrescribir este método.
        Por defecto no hace nada y devuelve True.

        Args:
            page: Página de Playwright.
            context: Contexto de Playwright (para guardar cookies al final).

        Returns:
            True si la autenticación fue exitosa o no era necesaria.
        """
        return True

    @abstractmethod
    async def scratch(self, query: SearchQuery) -> list[Vehicle]:
        """Ejecuta la búsqueda de forma asíncrona y devuelve la lista de vehículos.

        Debe ser implementado por cada scraper concreto.
        """
        raise NotImplementedError
