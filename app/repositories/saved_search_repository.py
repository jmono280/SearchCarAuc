"""Repositorio de filtros guardados basado en JSON local.

Persiste los filtros en un archivo dentro del directorio de datos de la app
(compatible con el volumen Docker `/app/data` usado para las sesiones de
Playwright). NO almacena resultados de busqueda, solo los criterios.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models.saved_search import SavedSearch, SavedSearchCreate, SavedSearchUpdate

logger = logging.getLogger(__name__)

# Reutiliza el mismo directorio de datos que las sesiones de Playwright.
# En Docker el compose mapea SCRAPER_SESSION_DIR=/app/data.
_DATA_DIR = Path(os.environ.get("SCRAPER_SESSION_DIR", "./data"))
_FILE_PATH = _DATA_DIR / "saved_searches.json"
_lock = asyncio.Lock()


class SavedSearchRepository:
    """CRUD asincrono de filtros guardados sobre archivo JSON."""

    @staticmethod
    def _ensure_dir() -> None:
        """Crea el directorio de datos si no existe."""
        _FILE_PATH.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _load_raw() -> list[dict[str, Any]]:
        """Lee el archivo JSON o devuelve lista vacia si no existe o esta corrupto."""
        if not _FILE_PATH.exists():
            return []
        try:
            with open(_FILE_PATH, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "Error leyendo filtros guardados de %s: %s. Se empezara con lista vacia.",
                _FILE_PATH,
                exc,
            )
            return []

    @staticmethod
    def _save_raw(data: list[dict[str, Any]]) -> None:
        """Escribe el archivo JSON de forma atomica."""
        SavedSearchRepository._ensure_dir()
        tmp_path = _FILE_PATH.with_suffix(".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
            tmp_path.replace(_FILE_PATH)
        except OSError as exc:
            logger.warning("Error escribiendo filtros guardados en %s: %s", _FILE_PATH, exc)
            raise

    @classmethod
    async def list_all(cls) -> list[SavedSearch]:
        """Devuelve todos los filtros guardados ordenados por fecha de creacion."""
        async with _lock:
            raw = cls._load_raw()
        items = [SavedSearch.model_validate(item) for item in raw]
        items.sort(key=lambda s: s.creado_en)
        return items

    @classmethod
    async def get(cls, search_id: str) -> SavedSearch | None:
        """Busca un filtro por su ID."""
        async with _lock:
            raw = cls._load_raw()
            for item in raw:
                if item.get("id") == search_id:
                    return SavedSearch.model_validate(item)
        return None

    @classmethod
    async def create(cls, data: SavedSearchCreate) -> SavedSearch:
        """Crea un nuevo filtro guardado."""
        now = datetime.now(timezone.utc)
        saved = SavedSearch(
            nombre=data.nombre,
            query=data.query,
            creado_en=now,
            actualizado_en=now,
        )
        async with _lock:
            raw = cls._load_raw()
            raw.append(saved.model_dump(mode="json"))
            cls._save_raw(raw)
        return saved

    @classmethod
    async def update(cls, search_id: str, data: SavedSearchUpdate) -> SavedSearch | None:
        """Actualiza nombre y/o query de un filtro existente."""
        async with _lock:
            raw = cls._load_raw()
            for item in raw:
                if item.get("id") == search_id:
                    if data.nombre is not None:
                        item["nombre"] = data.nombre
                    if data.query is not None:
                        item["query"] = data.query.model_dump(mode="json")
                    item["actualizado_en"] = datetime.now(timezone.utc).isoformat()
                    cls._save_raw(raw)
                    return SavedSearch.model_validate(item)
        return None

    @classmethod
    async def delete(cls, search_id: str) -> bool:
        """Elimina un filtro por ID. Devuelve True si existia."""
        async with _lock:
            raw = cls._load_raw()
            new_raw = [item for item in raw if item.get("id") != search_id]
            if len(new_raw) != len(raw):
                cls._save_raw(new_raw)
                return True
        return False
