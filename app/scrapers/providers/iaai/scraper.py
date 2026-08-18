"""Scraper concreto para IAAI.com (Insurance Auto Auctions).

Soporta autenticación OIDC, persistencia de sesión y fallback con Playwright
cuando Incapsula bloquea las peticiones directas.
"""

from __future__ import annotations

import html
import json
import logging
import re
from pathlib import Path
from typing import Any

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from app.config import settings
from app.models.search import SearchQuery
from app.models.vehicle import Vehicle
from app.scrapers.base_scraper import DEFAULT_HEADERS, BaseScraper

logger = logging.getLogger(__name__)

# onclick="ImageModalClicked('stock','id~US','vin','branch','year','make','model','series','..')"
_IMAGE_MODAL_RE = re.compile(
    r"ImageModalClicked\(\s*"
    r"'(?P<stock>[^']*)'\s*,\s*"
    r"'(?P<id>[^']*)'\s*,\s*"
    r"'(?P<vin>[^']*)'\s*,\s*"
    r"'(?P<branch>[^']*)'\s*,\s*"
    r"'(?P<year>[^']*)'\s*,\s*"
    r"'(?P<make>[^']*)'\s*,\s*"
    r"'(?P<model>[^']*)'\s*,\s*"
    r"'(?P<series>[^']*)'",
    re.IGNORECASE,
)
_ODOMETER_RE = re.compile(r"([\d,]+)\s*mi\b")
_ENGINE_RE = re.compile(r"(\d(?:\.\d)?L\s*[^,<]*?\d+\s*HP)", re.IGNORECASE)
_PRICE_RE = re.compile(r"\$([\d,]+(?:\.\d+)?)")
# Extrae el template de búsqueda embebido en la página /Search.
_GBP_QUERY_RE = re.compile(r'id="GBPSearchQuery"[^>]*value="([^"]*)"')


class ScraperBlockedError(RuntimeError):
    """Se lanza cuando el sitio responde con un reto anti-bot (Incapsula) en vez de datos."""


class IAAIScraper(BaseScraper):
    """Busca vehículos en IAAI vía el endpoint POST /Search."""

    name = "IAAI"

    def __init__(self, provider_settings: dict[str, Any] | None = None) -> None:
        super().__init__(provider_settings)
        self.name = self.provider_settings.get("name", "IAAI")
        self.base_url = self._base_url_from(self.provider_settings.get("url"))
        self.search_url = f"{self.base_url}/Search"
        self.login_url = f"{self.base_url}/Dashboard/Default"
        self.username = self.provider_settings.get("username")
        self.password = self.provider_settings.get("password")

    @staticmethod
    def _base_url_from(url: str | None) -> str:
        from urllib.parse import urlsplit

        if not url:
            return "https://www.iaai.com"
        parts = urlsplit(url)
        if parts.scheme and parts.netloc:
            return f"{parts.scheme}://{parts.netloc}"
        return url.rstrip("/")

    @property
    def has_login_credentials(self) -> bool:
        return bool(self.username and self.password)

    async def authenticate(self, page, context) -> bool:
        """Asegura que la sesión de Playwright esté autenticada en IAAI."""
        if not self.has_login_credentials:
            logger.info("[%s] Sin credenciales de login; se continúa sin autenticar.", self.name)
            return True

        logger.info("[%s] Verificando sesión en %s", self.name, self.search_url)
        await page.goto(self.search_url, wait_until="domcontentloaded", timeout=90_000)

        if await self._is_logged_in(page):
            logger.info("[%s] Sesión previa válida.", self.name)
            await self._save_storage_state(context)
            return True

        logger.warning("[%s] Sesión no válida; iniciando sesión con credenciales.", self.name)
        try:
            await self._do_login(page)
        except ScraperBlockedError as exc:
            logger.warning(
                "[%s] No fue posible iniciar sesión (%s). Continuando como usuario anónimo.",
                self.name,
                exc,
            )
            await page.goto(self.search_url, wait_until="domcontentloaded", timeout=90_000)
            return True

        await page.goto(self.search_url, wait_until="domcontentloaded", timeout=90_000)
        await self._save_storage_state(context)
        return True

    async def scratch(self, query: SearchQuery) -> list[Vehicle]:
        """Ejecuta la búsqueda y devuelve la lista de vehículos parseados."""
        if settings.force_playwright:
            logger.info("[%s] FORCE_PLAYWRIGHT=true: usando Playwright directamente.", self.name)
            return await self._scratch_playwright(query)

        try:
            return await self._scratch_httpx(query)
        except ScraperBlockedError as exc:
            logger.warning("[%s] httpx bloqueado: %s. Intentando Playwright.", self.name, exc)
            return await self._scratch_playwright(query)

    def _build_query(self, query: SearchQuery) -> dict:
        """Construye el payload JSON de búsqueda a partir de SearchQuery."""
        facets: list[dict] = []
        long_ranges: list[dict] = []

        anio_min, anio_max = query.rango_anio()
        if anio_min is not None and anio_max is not None:
            long_ranges.append({
                "From": str(anio_min),
                "Name": "Year",
                "To": str(anio_max),
            })

        if query.buy_now and (query.precio_min is not None or query.precio_max is not None):
            long_ranges.append({
                "From": str(int(query.precio_min or 0)),
                "Name": "MinimumBidAmount",
                "To": str(int(query.precio_max or 999_999)),
            })
            facets.append({"Group": "AuctionType", "Value": "Buy Now"})

        base_query = {
            "Searches": [
                {"FullSearch": query.to_full_search(), "Facets": facets, "LongRanges": long_ranges}
            ],
            "CurrentPage": query.page,
            "PageSize": query.page_size,
        }
        if query.zip and query.radio_millas:
            base_query["ZipCode"] = query.zip
            base_query["miles"] = query.radio_millas
            base_query["Miles"] = query.radio_millas

        return base_query

    async def _scratch_httpx(self, query: SearchQuery) -> list[Vehicle]:
        """Flujo principal usando httpx."""
        search_query = self._build_query(query)

        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS,
            timeout=settings.request_timeout,
            follow_redirects=True,
        ) as client:
            base_query = await self._fetch_query_template(client)
            base_query.update(search_query)

            headers = {
                **DEFAULT_HEADERS,
                "Content-Type": "application/json; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "*/*",
                "Referer": self.search_url,
                "Origin": self.base_url,
            }
            response = await client.post(
                self.search_url,
                content=json.dumps(base_query),
                headers=headers,
            )
            response.raise_for_status()
            html_body = response.text

        return self._parse_results(html_body)

    async def _fetch_query_template(self, client: httpx.AsyncClient) -> dict:
        """Descarga la página /Search y extrae el modelo de query base."""
        response = await client.get(self.search_url)
        response.raise_for_status()
        match = _GBP_QUERY_RE.search(response.text)
        if not match:
            if "Incapsula" in response.text and "table-row" not in response.text:
                raise ScraperBlockedError("IAAI bloqueó la petición (Incapsula).")
            raise ScraperBlockedError("No se encontró el template de búsqueda en /Search.")
        return json.loads(html.unescape(match.group(1)))

    async def _scratch_playwright(self, query: SearchQuery) -> list[Vehicle]:
        """Fallback/respaldo con Playwright: navegador headless real."""
        search_query = self._build_query(query)

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

                logger.info("[%s] Playwright cargando %s", self.name, self.search_url)
                response = await page.goto(
                    self.search_url, wait_until="domcontentloaded", timeout=90_000
                )
                if response is None:
                    raise ScraperBlockedError("Playwright: goto devolvió None.")

                await page.wait_for_selector("#GBPSearchQuery", state="attached", timeout=30_000)
                gbp_value = await page.input_value("#GBPSearchQuery")
                if not gbp_value:
                    raise ScraperBlockedError("Playwright: GBPSearchQuery está vacío.")
                base_query = json.loads(html.unescape(gbp_value))
                base_query.update(search_query)

                logger.info("[%s] Playwright ejecutando POST /Search", self.name)
                post_response = await page.evaluate(
                    """
                    async ({url, body}) => {
                        const res = await fetch(url, {
                            method: "POST",
                            headers: {
                                "Content-Type": "application/json; charset=UTF-8",
                                "X-Requested-With": "XMLHttpRequest",
                                "Accept": "*/*",
                                "Referer": url
                            },
                            body: JSON.stringify(body)
                        });
                        return await res.text();
                    }
                    """,
                    {"url": self.search_url, "body": base_query},
                )

                return self._parse_results(post_response)
            finally:
                await context.close()
                await browser.close()

    @staticmethod
    async def _is_logged_in(page) -> bool:
        """True si la página de búsqueda indica que el usuario está logueado."""
        page_html = await page.content()
        if 'title="Please log in as a buyer"' in page_html:
            return False
        if 'Please log in as a buyer' in page_html:
            return False
        try:
            if await page.input_value("#IsLoggedIn") == "True":
                return True
        except Exception:
            pass
        return bool(re.search(r'VIN:\s*[A-HJ-NPR-Z0-9]{17}', page_html))

    async def _do_login(self, page) -> None:
        """Ejecuta el login en IAAI usando su página OIDC en login.iaai.com."""
        logger.info("[%s] Playwright navegando a %s", self.name, self.login_url)
        await page.goto(self.login_url, wait_until="domcontentloaded", timeout=90_000)

        if "login.iaai.com" not in page.url and "signin-oidc" not in page.url:
            await page.wait_for_timeout(3_000)
            if "login.iaai.com" not in page.url and "signin-oidc" not in page.url:
                logger.info("[%s] Ya autenticado en %s.", self.name, page.url)
                return

        if "login.iaai.com" not in page.url:
            try:
                await page.wait_for_function(
                    "() => window.location.href.includes('login.iaai.com')",
                    timeout=30_000,
                )
            except Exception as exc:
                raise ScraperBlockedError(
                    f"No se redirigió a la página de login OIDC. URL actual: {page.url}"
                )

        logger.info("[%s] Página OIDC detectada: %s", self.name, page.url)

        try:
            await page.wait_for_selector("#Email", timeout=15_000)
            await page.wait_for_selector("#Password", timeout=15_000)
        except Exception as exc:
            raise ScraperBlockedError(f"No se encontraron campos #Email/#Password: {exc}")

        await page.fill("#Email", self.username)
        await page.fill("#Password", self.password)

        logger.info("[%s] Enviando credenciales...", self.name)
        await page.click('form#account button[type="submit"]')

        try:
            await page.wait_for_function(
                "() => !window.location.href.includes('login.iaai.com')",
                timeout=60_000,
            )
            if "signin-oidc" in page.url:
                await page.wait_for_function(
                    "() => !window.location.href.includes('signin-oidc')",
                    timeout=60_000,
                )
        except Exception as exc:
            error_visible = await page.is_visible("#lblErrorMessage")
            if error_visible:
                error_text = await page.inner_text("#lblErrorMessage")
                raise ScraperBlockedError(f"Login rechazado: {error_text.strip()}")
            raise ScraperBlockedError(f"No se completó la redirección OIDC: {exc}")

        logger.info("[%s] Login OIDC completado. URL actual: %s", self.name, page.url)

    def _parse_results(self, html_body: str) -> list[Vehicle]:
        """Parsea el HTML de resultados en una lista de Vehicle."""
        soup = BeautifulSoup(html_body, "lxml")
        rows = soup.select("div.table-row.table-row-border")

        if not rows and "Incapsula" in html_body:
            raise ScraperBlockedError("IAAI devolvió un reto anti-bot en lugar de resultados.")

        vehicles: list[Vehicle] = []
        for row in rows:
            vehicle = self._parse_row(row)
            if vehicle is not None:
                vehicles.append(vehicle)
        return vehicles

    def _parse_row(self, row) -> Vehicle | None:
        """Convierte una fila de resultado en un Vehicle."""
        link = row.select_one("h4.heading-7 a")
        titulo = link.get_text(strip=True) if link else None
        detalle_url = None
        if link and link.get("href"):
            detalle_url = self._absolute(link["href"])

        anio = marca = modelo = serie = vin = branch = None
        onclick_el = row.find(attrs={"onclick": _IMAGE_MODAL_RE})
        if onclick_el:
            m = _IMAGE_MODAL_RE.search(onclick_el["onclick"])
            if m:
                marca = m.group("make") or None
                modelo = m.group("model") or None
                serie = m.group("series") or None
                vin = m.group("vin") or None
                branch = m.group("branch") or None
                try:
                    anio = int(m.group("year"))
                except (TypeError, ValueError):
                    anio = None

        if not titulo and not marca:
            return None

        row_text = row.get_text(" ", strip=True)

        labels = self._extract_labels(row)
        dano_primario = labels.get("primary damage")
        dano_secundario = labels.get("secondary damage")
        estado = labels.get("sale status") or labels.get("status") or labels.get("title/sale doc")
        subasta = labels.get("auction")
        if not subasta:
            subasta = self._extract_value_from_text(row_text, "auction")

        odo_match = _ODOMETER_RE.search(row_text)
        odometro = odo_match.group(0) if odo_match else None

        eng_match = _ENGINE_RE.search(row_text)
        motor = eng_match.group(1).strip() if eng_match else None
        if not motor:
            motor = labels.get("engine")

        precio, moneda = self._parse_price(row)
        acv, acv_moneda = self._parse_acv(row)
        if acv_moneda:
            moneda = acv_moneda

        imagen_url = None
        img = row.select_one("img[data-src]")
        if img:
            imagen_url = img.get("data-src")

        return Vehicle(
            titulo=titulo or f"{anio or ''} {marca or ''} {modelo or ''}".strip(),
            anio=anio,
            marca=marca,
            modelo=modelo,
            precio=precio,
            acv=acv,
            moneda=moneda,
            odometro=odometro,
            vin=vin,
            motor=motor,
            dano_primario=dano_primario,
            dano_secundario=dano_secundario,
            tipo=serie,
            sucursal=branch,
            estado=estado,
            subasta=subasta,
            imagen_url=imagen_url,
            detalle_url=detalle_url,
            fuente=self.name,
        )

    @staticmethod
    def _extract_labels(row) -> dict[str, str]:
        """Extrae pares label/value de elementos tipo data-list."""
        labels: dict[str, str] = {}

        for item in row.select(".data-list__item, .data-list-group__item, dl > div"):
            label_el = item.select_one(
                ".data-list__label, .data-list-group__label, dt, .label"
            )
            value_el = item.select_one(
                ".data-list__value, .data-list-group__value, dd, .value"
            )

            if label_el and value_el:
                key = label_el.get_text(strip=True).rstrip(":").strip().lower()
                value = value_el.get_text(strip=True)
                if key and value:
                    labels[key] = value

            if value_el and value_el.has_attr("title"):
                title = value_el["title"].strip()
                if ":" in title:
                    parts = title.split(":", 1)
                    key = parts[0].strip().lower()
                    value = parts[1].strip()
                    if key and value and key not in labels:
                        labels[key] = value

        if not labels:
            for text in row.stripped_strings:
                if ":" in text:
                    parts = text.split(":", 1)
                    key = parts[0].strip().lower()
                    value = parts[1].strip()
                    if key and value and key not in labels:
                        labels[key] = value

        return labels

    @staticmethod
    def _extract_value_from_text(text: str, key: str) -> str | None:
        """Busca un patrón 'Key: value' en el texto completo de la fila."""
        pattern = re.compile(rf"{re.escape(key)}\s*:\s*([^,]+)", re.IGNORECASE)
        match = pattern.search(text)
        return match.group(1).strip() if match else None

    @staticmethod
    def _parse_price(row) -> tuple[float | None, str | None]:
        """Busca un enlace 'Buy Now $X' y devuelve (precio, moneda)."""
        for a in row.select("a"):
            text = a.get_text(" ", strip=True)
            if "Buy Now" in text:
                m = _PRICE_RE.search(text)
                if m:
                    precio = float(m.group(1).replace(",", ""))
                    moneda = "USD" if "USD" in text else None
                    return precio, moneda
        return None, "USD"

    @staticmethod
    def _parse_acv(row) -> tuple[float | None, str | None]:
        """Busca el valor ACV (Actual Cash Value) en la fila de resultados."""
        for item in row.select(".data-list__item"):
            label = item.select_one(".data-list__label")
            value = item.select_one(".data-list__value")
            if label and value and "ACV" in label.get_text(strip=True):
                m = _PRICE_RE.search(value.get_text(strip=True))
                if m:
                    return float(m.group(1).replace(",", "")), "USD"
        return None, None

    def _absolute(self, path: str) -> str:
        """Convierte una ruta relativa en URL absoluta."""
        if path.startswith("http"):
            return path
        return f"{self.base_url}{path}"
