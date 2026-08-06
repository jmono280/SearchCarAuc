"""Modelos Pydantic del proyecto (capa Model del patrón MVVM)."""

from app.models.results import SearchResults
from app.models.search import SearchQuery
from app.models.vehicle import Vehicle

__all__ = ["SearchQuery", "Vehicle", "SearchResults"]
