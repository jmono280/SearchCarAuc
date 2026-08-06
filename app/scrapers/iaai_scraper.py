"""Scraper concreto para IAAI.com (Insurance Auto Auctions).

Incluye fallback con Playwright para cuando Imperva Incapsula bloquea httpx.
"""

from __future__ import annotations

import html
import json
import logging
import re

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
_ENGINE_RE = re.compile(r"(\d(?:\.\d)?L[^,<]*,[^,<]*,\s*\d+\s*HP)", re.IGNORECASE)
_PRICE_RE = re.compile(r"\$([\d,]+(?:\.\d+)?)")
# Extrae el template de búsqueda embebido en la página /Search.
_GBP_QUERY_RE = re.compile(r'id="GBPSearchQuery"[^>]*value="([^"]*)"')


class ScraperBlockedError(RuntimeError):
    """Se lanza cuando el sitio responde con un reto anti-bot (Incapsula) en vez de datos."""


class IAAIScraper(BaseScraper):
    """Busca vehículos en IAAI vía el endpoint POST /Search (mismo que usa el sitio)."""

    name = "IAAI"

    def __init__(self, page_size: int = 50) -> None:
        self.base_url = settings.iaai_base_url
        self.search_url = f"{self.base_url}/Search"
        self.page_size = page_size

    async def scratch(self, query: SearchQuery) -> list[Vehicle]:
        """Ejecuta la búsqueda y devuelve la lista de vehículos parseados.

        Intenta primero con httpx (rápido). Si Incapsula bloquea, cae en el
        fallback con Playwright (navegador headless real).
        """
        try:
            return await self._scratch_httpx(query)
        except ScraperBlockedError as exc:
            logger.warning("httpx bloqueado por Incapsula: %s. Intentando fallback con Playwright.", exc)
            return await self._scratch_playwright(query)

    def _build_query(self, query: SearchQuery) -> dict:
        """Construye el payload JSON de búsqueda a partir de SearchQuery."""
        facets: list[dict] = []
        long_ranges: list[dict] = []

        # Filtro: rango de año (usando año exacto si solo se envió `anio`).
        anio_min, anio_max = query.rango_anio()
        if anio_min is not None and anio_max is not None:
            long_ranges.append({
                "From": str(anio_min),
                "Name": "Year",
                "To": str(anio_max),
            })

        # Filtro: rango de precio (Buy Now).
        if query.precio_min is not None or query.precio_max is not None:
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
            # IAAI acepta tanto `miles` como `Miles`; usamos el que usa su JS.
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
            # 1) GET a /Search: obtiene cookies (Incapsula) y el template de la query.
            base_query = await self._fetch_query_template(client)

            # 2) Ajusta el template con los filtros del usuario.
            base_query.update(search_query)

            # 3) POST a /Search: devuelve el fragmento HTML con los resultados.
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
        """Descarga la página /Search y extrae el modelo de query base (GBPSearchQuery)."""
        response = await client.get(self.search_url)
        response.raise_for_status()
        match = _GBP_QUERY_RE.search(response.text)
        if not match:
            if "Incapsula" in response.text and "table-row" not in response.text:
                raise ScraperBlockedError("IAAI bloqueó la petición (Incapsula).")
            raise ScraperBlockedError("No se encontró el template de búsqueda en /Search.")
        return json.loads(html.unescape(match.group(1)))

    async def _scratch_playwright(self, query: SearchQuery) -> list[Vehicle]:
        """Fallback con Playwright: usa un navegador headless real para pasar Incapsula."""
        search_query = self._build_query(query)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=DEFAULT_HEADERS["User-Agent"],
            )
            page = await context.new_page()

            try:
                # 1) Carga /Search con navegador real (pasa el challenge de Incapsula).
                logger.info("Playwright: cargando %s", self.search_url)
                response = await page.goto(
                    self.search_url, wait_until="domcontentloaded", timeout=90_000
                )
                if response is None:
                    raise ScraperBlockedError("Playwright: goto devolvió None.")

                # Espera explícita al input oculto con el template de búsqueda.
                await page.wait_for_selector("#GBPSearchQuery", state="attached", timeout=30_000)
                gbp_value = await page.input_value("#GBPSearchQuery")
                if not gbp_value:
                    raise ScraperBlockedError("Playwright: GBPSearchQuery está vacío.")
                base_query = json.loads(html.unescape(gbp_value))
                base_query.update(search_query)

                # 2) Ejecuta el mismo POST que hace el sitio, pero desde el navegador.
                logger.info("Playwright: ejecutando POST /Search")
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

        # Datos estructurados desde el onclick de ImageModalClicked (confiables).
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

        odo_match = _ODOMETER_RE.search(row_text)
        odometro = odo_match.group(0) if odo_match else None

        eng_match = _ENGINE_RE.search(row_text)
        motor = eng_match.group(1).strip() if eng_match else None

        precio, moneda = self._parse_price(row)

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
            moneda=moneda,
            odometro=odometro,
            vin=vin,
            motor=motor,
            tipo=serie,
            sucursal=branch,
            imagen_url=imagen_url,
            detalle_url=detalle_url,
            fuente=self.name,
        )

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

    def _absolute(self, path: str) -> str:
        """Convierte una ruta relativa en URL absoluta."""
        if path.startswith("http"):
            return path
        return f"{self.base_url}{path}"
