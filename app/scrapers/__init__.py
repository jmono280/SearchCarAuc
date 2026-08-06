"""Scrapers del proyecto (capa Model/Servicios del MVVM)."""

from app.scrapers.base_scraper import BaseScraper
from app.scrapers.providers.acv.scraper import ACVScraper
from app.scrapers.providers.iaai.scraper import IAAIScraper, ScraperBlockedError
from app.scrapers.providers.manheim.scraper import ManheimScraper
from app.scrapers.providers.openlane.scraper import OpenLaneScraper

__all__ = [
    "BaseScraper",
    "IAAIScraper",
    "ScraperBlockedError",
    "ManheimScraper",
    "ACVScraper",
    "OpenLaneScraper",
]
