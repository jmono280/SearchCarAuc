"""Scrapers del proyecto (capa Model/Servicios del MVVM)."""

from app.scrapers.base_scraper import BaseScraper
from app.scrapers.iaai_scraper import IAAIScraper, ScraperBlockedError

__all__ = ["BaseScraper", "IAAIScraper", "ScraperBlockedError"]
