"""Configuración de la aplicación cargada desde variables de entorno (.env)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings del proyecto.

    Lee el archivo .env de la raíz. `URL` es la URL de búsqueda de prueba de IAAI.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    url: str = "https://www.iaai.com/Search"
    request_timeout: float = 20.0

    @property
    def iaai_base_url(self) -> str:
        """Devuelve el esquema + host del sitio IAAI, ej. 'https://www.iaai.com'."""
        from urllib.parse import urlsplit

        parts = urlsplit(self.url)
        if parts.scheme and parts.netloc:
            return f"{parts.scheme}://{parts.netloc}"
        return "https://www.iaai.com"


settings = Settings()
