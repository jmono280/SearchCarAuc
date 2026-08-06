"""Re-export de IAAIScraper para compatibilidad con imports antiguos.

La implementación real ahora vive en app.scrapers.providers.iaai.
"""

from __future__ import annotations

from app.scrapers.providers.iaai.scraper import IAAIScraper

__all__ = ["IAAIScraper"]
