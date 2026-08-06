"""Configuración de la aplicación cargada desde variables de entorno (.env)."""

from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings del proyecto.

    Lee el archivo `.env` de la raíz. Las variables sensibles o específicas del
    sitio objetivo deben configurarse siempre en el entorno y nunca quedar
    hardcodeadas en el código.

    La configuración de proveedores sigue el prefijo ``{PROVIDER}_``:
    ``IAAI_ENABLED``, ``IAAI_URL``, ``IAAI_USERNAME``, etc.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Timeout en segundos para las peticiones de scraping.
    request_timeout: float = 20.0
    # true = usa Playwright directamente sin intentar httpx primero.
    force_playwright: bool = False

    # ------------------------------------------------------------------
    # Proveedor: IAAI
    # ------------------------------------------------------------------
    iaai_enabled: bool = True
    iaai_url: str = "https://www.iaai.com/Search"
    iaai_username: str | None = Field(
        default=None,
        validation_alias=AliasChoices("IAAI_USERNAME", "user_ai_ai"),
    )
    iaai_password: str | None = Field(
        default=None,
        validation_alias=AliasChoices("IAAI_PASSWORD", "psw"),
    )
    iaai_name: str = "IAAI"

    # ------------------------------------------------------------------
    # Proveedor: Manheim
    # ------------------------------------------------------------------
    manheim_enabled: bool = False
    manheim_url: str | None = None
    manheim_username: str | None = None
    manheim_password: str | None = None
    manheim_name: str = "Manheim"

    # ------------------------------------------------------------------
    # Proveedor: ACV Auctions
    # ------------------------------------------------------------------
    acv_enabled: bool = False
    acv_url: str | None = None
    acv_username: str | None = None
    acv_password: str | None = None
    acv_name: str = "ACV"

    # ------------------------------------------------------------------
    # Proveedor: OpenLane
    # ------------------------------------------------------------------
    openlane_enabled: bool = False
    openlane_url: str | None = None
    openlane_username: str | None = None
    openlane_password: str | None = None
    openlane_name: str = "OpenLane"

    def provider_settings(self, provider: str) -> dict:
        """Devuelve la configuración de un proveedor como diccionario.

        Args:
            provider: Nombre clave del proveedor: ``iaai``, ``manheim``, ``acv``,
                ``openlane``.
        """
        provider = provider.lower()
        return {
            "enabled": getattr(self, f"{provider}_enabled"),
            "url": getattr(self, f"{provider}_url"),
            "username": getattr(self, f"{provider}_username"),
            "password": getattr(self, f"{provider}_password"),
            "name": getattr(self, f"{provider}_name"),
        }

    @property
    def enabled_providers(self) -> list[str]:
        """Lista de proveedores habilitados."""
        providers = ["iaai", "manheim", "acv", "openlane"]
        return [p for p in providers if getattr(self, f"{p}_enabled")]


settings = Settings()
