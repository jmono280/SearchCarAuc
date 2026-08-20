"""Scraper para OpenLane (app.openlane.com).

Implementación inicial basada en Playwright. OpenLane es una SPA React, por lo
que el scraper navega con un navegador real, inicia sesión si hay credenciales
y extrae los datos de los listados del marketplace usando heurísticas sobre el
HTML renderizado.

La implementación se irá afinando conforme conozcamos la estructura exacta de
la página de resultados.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from app.config import settings
from app.models.search import SearchQuery
from app.models.vehicle import Vehicle
from app.scrapers.base_scraper import DEFAULT_HEADERS, BaseScraper

logger = logging.getLogger(__name__)

_VIN_RE = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b")
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_PRICE_RE = re.compile(r"\$\s?[,\d]+")
_MILES_RE = re.compile(r"([,\d]+)\s*(mi|miles|mile)\b", re.IGNORECASE)


class OpenLaneScraper(BaseScraper):
    """Busca vehículos en OpenLane vía Playwright."""

    name = "OpenLane"

    def __init__(self, provider_settings: dict[str, Any] | None = None) -> None:
        super().__init__(provider_settings)
        self.name = self.provider_settings.get("name", "OpenLane")
        self.base_url = "https://app.openlane.com"
        self.search_url = self.provider_settings.get("url") or f"{self.base_url}/search?tab=marketplace"
        self.login_url = f"{self.base_url}/sign_in"
        self.username = self.provider_settings.get("username")
        self.password = self.provider_settings.get("password")

    @property
    def has_login_credentials(self) -> bool:
        return bool(self.username and self.password)

    async def authenticate(self, page, context) -> bool:
        """Asegura que Playwright esté autenticado en OpenLane."""
        if not self.has_login_credentials:
            logger.info("[%s] Sin credenciales de login; se continúa sin autenticar.", self.name)
            return True

        logger.info("[%s] Verificando sesión en %s", self.name, self.search_url)
        await page.goto(self.search_url, wait_until="domcontentloaded", timeout=120_000)

        if await self._is_logged_in(page):
            logger.info("[%s] Sesión previa válida.", self.name)
            await self._save_storage_state(context)
            return True

        logger.warning("[%s] Sesión no válida; iniciando sesión con credenciales.", self.name)
        await self._do_login(page)
        await page.goto(self.search_url, wait_until="domcontentloaded", timeout=120_000)
        await self._save_storage_state(context)
        return True

    async def _do_login(self, page) -> None:
        """Ejecuta el login en OpenLane detectando los campos automáticamente."""
        logger.info("[%s] Navegando a %s", self.name, self.login_url)
        await page.goto(self.login_url, wait_until="domcontentloaded", timeout=120_000)

        # OpenLane usa distintos selectores según la versión. Probamos varios.
        username_selectors = [
            'input[type="email"]',
            'input[name="email"]',
            'input[name="username"]',
            'input[id*="email" i]',
            'input[id*="user" i]',
            'input[placeholder*="email" i]',
            'input[placeholder*="user" i]',
        ]
        password_selectors = [
            'input[type="password"]',
            'input[name="password"]',
            'input[id*="password" i]',
        ]
        submit_selectors = [
            'button[type="submit"]',
            'button:has-text("Sign in")',
            'button:has-text("Log in")',
            'button:has-text("Continue")',
            'button:has-text("Submit")',
        ]

        user_sel = await self._first_visible_selector(page, username_selectors)
        pass_sel = await self._first_visible_selector(page, password_selectors)
        submit_sel = await self._first_visible_selector(page, submit_selectors)

        if not user_sel or not pass_sel:
            page_html = await page.content()
            debug_path = Path("/tmp/opencode/openlane_login_debug.html")
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            debug_path.write_text(page_html, encoding="utf-8")
            raise RuntimeError(
                f"[{self.name}] No se encontraron campos de login. "
                f"HTML guardado en {debug_path}"
            )

        logger.info("[%s] Rellenando credenciales", self.name)
        await page.fill(user_sel, self.username)
        await page.fill(pass_sel, self.password)

        if submit_sel:
            await page.click(submit_sel)
        else:
            await page.press(pass_sel, "Enter")

        # Esperamos redirección o carga de dashboard/resultados.
        await page.wait_for_load_state("networkidle", timeout=120_000)
        await page.wait_for_timeout(3000)

    @staticmethod
    async def _first_visible_selector(page, selectors: list[str]) -> str | None:
        """Devuelve el primer selector visible de la lista."""
        for selector in selectors:
            try:
                if await page.is_visible(selector, timeout=2000):
                    return selector
            except Exception:
                continue
        return None

    async def _is_logged_in(self, page) -> bool:
        """True si la página indica que el usuario está logueado."""
        url = page.url
        html_lower = (await page.content()).lower()

        # Si la URL sigue siendo /login o el texto pide login, no estamos logueados.
        if "/login" in url or "welcome back" in html_lower:
            return False
        if "sign in" in html_lower and "sign out" not in html_lower:
            return False

        # Indicadores de sesión activa.
        session_markers = ["logout", "sign out", "account", "profile", "dashboard"]
        return any(marker in html_lower for marker in session_markers)

    async def scratch(self, query: SearchQuery) -> list[Vehicle]:
        """Ejecuta la búsqueda y devuelve los vehículos encontrados."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            storage_state = str(self.storage_path) if self.storage_path.exists() else None
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=DEFAULT_HEADERS["User-Agent"],
                storage_state=storage_state,
            )
            page = await context.new_page()

            try:
                await self.authenticate(page, context)

                search_url = self._build_search_url(query)
                logger.info("[%s] Cargando resultados: %s", self.name, search_url)
                await page.goto(search_url, wait_until="networkidle", timeout=120_000)

                # Las SPAs necesitan tiempo para renderizar resultados.
                await page.wait_for_timeout(7000)

                html = await page.content()
                debug_path = self.storage_path.parent / "openlane_debug.html"
                debug_path.parent.mkdir(parents=True, exist_ok=True)
                debug_path.write_text(html, encoding="utf-8")
                logger.info("[%s] HTML de debug guardado en %s", self.name, debug_path)

                return self._parse_results(html)
            finally:
                await context.close()
                await browser.close()

    def _build_search_url(self, query: SearchQuery) -> str:
        """Construye la URL de búsqueda con los filtros básicos.

        OpenLane usa estos parámetros de query string (observados en la UI real):
        ``keywords``, ``min_year``, ``max_year``, ``min_mileage``,
        ``max_mileage``, ``min_price``, ``max_price``, ``radius``, ``zip``,
        ``tab``, ``saved_search_id``.

        Si la URL base ya contiene alguno de estos parámetros, los respetamos.
        """
        from urllib.parse import parse_qs

        parts = urlsplit(self.search_url)
        params: dict[str, Any] = {}
        if parts.query:
            for key, values in parse_qs(parts.query).items():
                params[key] = values[0]

        full = query.to_full_search().strip()
        if full:
            # OpenLane usa "keywords" para búsqueda libre.
            params.setdefault("keywords", full)

        anio_min, anio_max = query.rango_anio()
        if anio_min is not None:
            params.setdefault("min_year", str(anio_min))
        if anio_max is not None:
            params.setdefault("max_year", str(anio_max))
        if query.buy_now:
            if query.precio_min is not None:
                params.setdefault("min_price", str(int(query.precio_min)))
            if query.precio_max is not None:
                params.setdefault("max_price", str(int(query.precio_max)))
        # OpenLane parece ignorar max_mileage si no se envía min_mileage.
        # Siempre enviamos ambos para que el rango se aplique correctamente.
        if query.odometro_min is not None or query.odometro_max is not None:
            params.setdefault("min_mileage", str(int(query.odometro_min or 0)))
            params.setdefault("max_mileage", str(int(query.odometro_max or 999_999)))
        if query.zip:
            params.setdefault("zip", query.zip)
            params.setdefault("radius", str(query.radio_millas or 100))

        new_parts = parts._replace(query=urlencode(params))
        return urlunsplit(new_parts)

    def _parse_results(self, html: str) -> list[Vehicle]:
        """Parsea el HTML renderizado de OpenLane buscando listados de vehículos.

        La estructura actual (agosto 2026) usa tarjetas con clase
        ``unified-vehicle-card``. Cada tarjeta contiene el título, imagen,
        motor, millas, VIN oculto y precio actual.
        """
        soup = BeautifulSoup(html, "lxml")
        vehicles: list[Vehicle] = []
        seen_vins: set[str] = set()

        cards = soup.find_all(
            class_=lambda cls: cls and "unified-vehicle-card" in cls.split()
        )
        logger.info("[%s] Tarjetas de vehículo encontradas: %s", self.name, len(cards))

        for card in cards:
            vehicle = self._parse_card(card)
            if vehicle and vehicle.vin and vehicle.vin not in seen_vins:
                seen_vins.add(vehicle.vin)
                vehicles.append(vehicle)

        if not vehicles:
            # Fallback heurístico por si cambian las clases CSS.
            logger.warning(
                "[%s] No se parsearon tarjetas. Intentando fallback por VIN.", self.name
            )
            vehicles = self._parse_by_vin(soup)

        return vehicles

    def _parse_card(self, card) -> Vehicle | None:
        """Extrae un Vehicle de una tarjeta de OpenLane."""
        try:
            vin_div = card.find(
                class_=lambda cls: cls and "hidden-vin" in cls.split()
            )
            vin = vin_div.get_text(strip=True).upper() if vin_div else None
            if not vin:
                return None

            title = self._extract_title(card)
            year, make, model = self._split_title(title)
            motor = self._extract_motor(card)
            miles = self._extract_miles_card(card)
            price = self._extract_price_card(card)
            image = self._extract_vehicle_image(card)
            detail_url = self._extract_detail_url_card(card)

            return Vehicle(
                titulo=title or f"{year or ''} {make or ''} {model or ''}".strip(),
                anio=year,
                marca=make or self.name,
                modelo=model or "",
                precio=price,
                moneda="USD",
                odometro=miles,
                vin=vin,
                motor=motor,
                dano_primario=None,
                dano_secundario=None,
                tipo=None,
                sucursal=None,
                estado=None,
                subasta=None,
                imagen_url=image,
                detalle_url=detail_url,
                fuente=self.name,
            )
        except Exception as exc:
            logger.warning("[%s] Error parseando tarjeta: %s", self.name, exc)
            return None

    def _parse_by_vin(self, soup: BeautifulSoup) -> list[Vehicle]:
        """Fallback: busca VINs en el HTML y construye vehículos mínimos."""
        vehicles: list[Vehicle] = []
        seen_vins: set[str] = set()

        for vin_node in soup.find_all(string=_VIN_RE):
            vin = _VIN_RE.search(vin_node.string).group(0).upper()
            if vin in seen_vins:
                continue
            seen_vins.add(vin)

            card = vin_node.find_parent(class_=lambda cls: cls and "vehicle" in (cls or "").lower())
            if card is None:
                card = vin_node.find_parent("div")
            text = card.get_text(separator=" ", strip=True) if card else ""

            year = self._extract_year(text)
            make, model = self._extract_make_model(text)

            vehicles.append(
                Vehicle(
                    titulo=f"{year or ''} {make or ''} {model or ''}".strip(),
                    anio=year,
                    marca=make or self.name,
                    modelo=model or "",
                    precio=self._extract_price_card(card) if card else None,
                    moneda="USD",
                    odometro=self._extract_miles_card(card) if card else None,
                    vin=vin,
                    motor=None,
                    dano_primario=None,
                    dano_secundario=None,
                    tipo=None,
                    sucursal=None,
                    estado=None,
                    subasta=None,
                    imagen_url=None,
                    detalle_url=None,
                    fuente=self.name,
                )
            )

        return vehicles

    @staticmethod
    def _extract_title(card) -> str | None:
        """Extrae el título completo del vehículo."""
        # El título suele estar en un h5 dentro de un enlace.
        h5 = card.find("h5")
        if h5:
            return h5.get_text(strip=True)

        # Fallback: atributo title del contenedor del título.
        title_div = card.find(attrs={"title": _YEAR_RE})
        if title_div:
            return title_div.get("title")

        return None

    @staticmethod
    def _split_title(title: str | None) -> tuple[int | None, str | None, str | None]:
        """Divide "2024 Jeep Wrangler Sport 4XE" en año, marca, modelo."""
        if not title:
            return None, None, None

        match = re.match(r"^(\d{4})\s+([A-Za-z]+)\s+(.+)$", title.strip())
        if match:
            year = int(match.group(1))
            make = match.group(2)
            model = match.group(3)
            return year, make, model
        return None, None, None

    @staticmethod
    def _extract_motor(card) -> str | None:
        """Extrae la descripción del motor (primer subtítulo de la tarjeta)."""
        # El motor es el primer <p> con clases de subtítulo dentro de vehicle-card-subtitle.
        subtitle = card.find(class_=lambda cls: cls and "vehicle-card-subtitle" in cls.split())
        if subtitle:
            p = subtitle.find("p")
            if p:
                return p.get_text(strip=True)
        return None

    @staticmethod
    def _extract_miles_card(card) -> str | None:
        """Extrae las millas desde el atributo title "XX,XXX mi"."""
        miles_div = card.find(attrs={"title": _MILES_RE})
        if miles_div:
            match = _MILES_RE.search(miles_div.get("title", ""))
            if match:
                return f"{match.group(1)} mi"

        # Fallback por texto.
        match = _MILES_RE.search(card.get_text(separator=" ", strip=True))
        if match:
            return f"{match.group(1)} mi"
        return None

    @staticmethod
    def _extract_price_card(card) -> float | None:
        """Extrae el precio/Top bid de la tarjeta."""
        status = card.find(class_=lambda cls: cls and "marketplace-status" in cls.split())
        if status:
            text = status.get_text(separator=" ", strip=True)
            match = _PRICE_RE.search(text)
            if match:
                return float(match.group(0).replace("$", "").replace(",", "").strip())

        # Fallback: cualquier precio en la tarjeta.
        match = _PRICE_RE.search(card.get_text(separator=" ", strip=True))
        if match:
            return float(match.group(0).replace("$", "").replace(",", "").strip())
        return None

    @staticmethod
    def _extract_vehicle_image(card) -> str | None:
        """Extrae la URL de la imagen del vehículo (no el logo del vendedor)."""
        for img in card.find_all("img"):
            alt = (img.get("alt") or "").lower()
            if alt == "user-info":
                continue
            src = img.get("src") or img.get("data-src")
            if src:
                return src
        return None

    @staticmethod
    def _extract_detail_url_card(card) -> str | None:
        """Extrae el link al detalle del vehículo."""
        for link in card.find_all("a", href=True):
            href = link["href"]
            if "/vehicle_detail/" in href:
                if href.startswith("http"):
                    return href
                return f"https://app.openlane.com{href}"
        return None

    @staticmethod
    def _extract_year(text: str) -> int | None:
        match = _YEAR_RE.search(text)
        if match:
            year = int(match.group(0))
            if 1900 <= year <= 2030:
                return year
        return None

    @staticmethod
    def _extract_make_model(text: str) -> tuple[str | None, str | None]:
        match = re.search(
            r"\b(19|20)\d{2}\b\s+([A-Za-z][A-Za-z0-9]+(?:\s+[A-Za-z][A-Za-z0-9]+){0,3})",
            text,
        )
        if match:
            raw = match.group(2).strip()
            parts = raw.split(None, 1)
            if len(parts) == 2:
                return parts[0], parts[1]
            return raw, None
        return None, None
