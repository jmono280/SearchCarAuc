# 🚗 Car Scraper MVVM

Scraper web de automóviles en subastas mayoristas de EE.UU., construido con **FastAPI** y arquitectura **MVVM** (Model-View-ViewModel). Soporta múltiples proveedores (IAAI, Manheim, ACV Auctions, OpenLane) con login por proveedor y persistencia de sesión. Expone una API REST, una interfaz web y un servidor **MCP** (Model Context Protocol) para que asistentes de IA puedan buscar vehículos con lenguaje natural.

> Proyecto para Automania.us / portfolio. El scraper demuestra manejo de arquitectura limpia, scraping resiliente, anti-bot bypass con Playwright y exposición de herramientas para IA vía MCP.

---

## ✨ Features

- **Búsqueda unificada de vehículos** en subastas por marca, modelo, año, rango de precio y ubicación (ZIP + radio).
- **API REST** con validación Pydantic v2 y modelos tipados.
- **Interfaz web responsive** con formulario de búsqueda y tabla comparativa.
- **Servidor MCP** para integración con clientes MCP (Claude Desktop, OpenCode, etc.).
- **Scraper resiliente**: flujo principal con `httpx` + fallback con **Playwright** cuando el sitio bloquea requests automatizados.
- **Multi-proveedor**: arquitectura plug-in para agregar IAAI, Manheim, ACV Auctions, OpenLane y otros.
- **Login por proveedor**: cada scraper maneja su propia autenticación y persistencia de sesión.
- **Arquitectura MVVM**: separación clara entre Modelos, ViewModel y Vistas/Controllers.
- **Concurrencia con `asyncio.gather`** para ejecutar múltiples scrapers en paralelo.

---

## 🛠️ Tech Stack

| Capa | Tecnología |
|------|------------|
| Backend | FastAPI |
| Validación de datos | Pydantic v2 + pydantic-settings |
| Scraping | httpx, BeautifulSoup4, lxml, Playwright |
| Concurrencia | asyncio |
| Protocolo IA | MCP (Model Context Protocol) |
| Servidor | Uvicorn |

---

## 🏗️ Arquitectura

```
app/
├── config.py                 # Configuración desde .env
├── main.py                   # FastAPI: web UI, API REST, MCP SSE
├── mcp_server.py             # Servidor MCP con tool search_vehicles
├── models/
│   ├── search.py             # SearchQuery (validación + filtros)
│   ├── vehicle.py            # Vehicle (modelo unificado)
│   └── results.py            # SearchResults + helpers
├── scrapers/
│   ├── base_scraper.py       # BaseScraper (ABC) + auth + headers reales
│   ├── iaai_scraper.py       # Re-export de compatibilidad
│   └── providers/
│       ├── iaai/             # IAAIScraper + login OIDC + parser
│       ├── manheim/          # ManheimScraper (placeholder)
│       ├── acv/              # ACVScraper (placeholder)
│       └── openlane/         # OpenLaneScraper (placeholder)
├── templates/
│   └── index.html            # UI web vanilla JS
└── viewmodels/
    └── scraper_viewmodel.py  # ScraperViewModel: orquesta scrapers
```

### Flujo de scraping

1. `GET /Search` → establece cookies anti-bot y extrae el template de búsqueda.
2. Construye el payload JSON con filtros: `FullSearch`, rangos de año/precio, ZIP + radio, paginación.
3. `POST /Search` → obtiene el HTML de resultados.
4. Parsea filas con BeautifulSoup, extrayendo datos estructurados desde `onclick`, títulos, precios, odómetro, motor, VIN e imágenes.
5. Si `httpx` es bloqueado, activa el fallback con Playwright para ejecutar la petición como un navegador real.

---

## 🚀 Cómo ejecutar

### 1. Clonar e instalar dependencias

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium
```

### 2. Configurar variables de entorno

Crear un archivo `.env` en la raíz (usa `.env.example` como template):

```dotenv
request_timeout=30
FORCE_PLAYWRIGHT=true

# IAAI (implementado)
IAAI_URL=https://www.iaai.com/Search
IAAI_USERNAME=tu_usuario@ejemplo.com
IAAI_PASSWORD=tu_password

# Manheim (placeholder)
MANHEIM_ENABLED=false
# MANHEIM_URL=https://www.manheim.com/members/inventory/search
# MANHEIM_USERNAME=tu_usuario
# MANHEIM_PASSWORD=tu_password

# ACV Auctions (placeholder)
ACV_ENABLED=false
# ACV_URL=https://www.acvauctions.com/search
# ACV_USERNAME=tu_usuario
# ACV_PASSWORD=tu_password

# OpenLane (placeholder)
OPENLANE_ENABLED=false
# OPENLANE_URL=https://www.openlane.com/search
# OPENLANE_USERNAME=tu_usuario
# OPENLANE_PASSWORD=tu_password
```

### 3. Levantar el servidor

```bash
.venv/bin/uvicorn app.main:app --reload
```

La app estará disponible en `http://localhost:8000`.

---

## 📡 API REST

### `POST /api/search`

```bash
curl -X POST http://127.0.0.1:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{
    "marca": "Honda",
    "modelo": "Civic",
    "anio_min": 2014,
    "anio_max": 2016,
    "precio_max": 3000,
    "zip": "33101",
    "radio_millas": 100,
    "page_size": 25
  }'
```

**Respuesta:**

```json
{
  "items": [...],
  "total": 25,
  "errores": []
}
```

### Modelo `Vehicle`

| Campo | Descripción |
|-------|-------------|
| `titulo` | Título completo del vehículo |
| `anio`, `marca`, `modelo` | Datos identificativos |
| `precio`, `moneda` | Precio Buy Now cuando está disponible |
| `acv` | Actual Cash Value (visible en la lista de resultados) |
| `odometro` | Millas recorridas |
| `vin` | VIN (identificador del vehículo) |
| `motor` | Descripción del motor |
| `dano_primario` | Daño primario (visible tras login) |
| `dano_secundario` | Daño secundario (visible tras login) |
| `tipo` | Tipo de vehículo |
| `sucursal` | Código de sucursal en el sitio origen |
| `estado` | Estado de la subasta/venta (visible tras login) |
| `subasta` | Nombre/código de la subasta (visible tras login) |
| `imagen_url` | URL de imagen principal |
| `detalle_url` | Link al detalle en el sitio origen |
| `fuente` | Origen del dato (nombre del proveedor) |

---

## 🤖 Servidor MCP

El proyecto expone un servidor MCP en `/mcp/sse`.

### Tool disponible: `search_vehicles`

Parámetros:
- `marca` (requerido)
- `modelo`, `anio`
- `anio_min`, `anio_max`
- `precio_min`, `precio_max`
- `zip`, `radio_millas`
- `page_size`

### Configuración para clientes MCP

```json
{
  "mcpServers": {
    "car_scraper": {
      "url": "http://localhost:8000/mcp/sse"
    }
  }
}
```

Ejemplo de uso en Claude Desktop / OpenCode:

> *"Busca Honda Civic del 2014 al 2016 por menos de 3000 USD cerca de Miami."*

---

## 🧪 Tests

Incluye un test de integración del servidor MCP:

```bash
.venv/bin/python tests/test_mcp.py
```

El script se conecta vía SSE, lista la herramienta `search_vehicles` y ejecuta una búsqueda de prueba.

---

## 📸 Interfaz web

Accede a `http://localhost:8000` para usar el formulario de búsqueda. La UI muestra:

- Imagen del vehículo
- Año, marca y modelo
- Precio y odómetro
- Motor y VIN
- Link al detalle en el sitio origen

Diseño responsive con CSS Grid para móvil, tablet y desktop.

---

## ⚠️ Notas técnicas

- El sitio objetivo puede usar protección anti-bot. El scraper intenta primero con `httpx` + headers realistas; si es bloqueado, usa Playwright como fallback.
- IAAI usa **OpenID Connect** para login (`/Dashboard/Default` → `login.iaai.com` → `/signin-oidc`). El scraper sigue el flujo completo y guarda el estado en `/app/data/{provider}_session.json` para reutilizarlo entre búsquedas.
- Tras login se obtiene el **VIN completo** y datos adicionales como **ACV**, **daño primario/secundario** y **estado** (Clear/Salvage).
- Los proveedores Manheim, ACV Auctions y OpenLane están registrados como **placeholders**. Para activarlos hay que implementar su flujo de login y parseo específico.
- Cada proveedor tiene su propia configuración en `.env`: `IAAI_*`, `MANHEIM_*`, `ACV_*`, `OPENLANE_*`.
- El campo `tipo` se captura en el formulario pero actualmente se usa como texto libre en `FullSearch`; no se mapea aún a facetas reales del sitio.

---

## 📄 Licencia

Proyecto personal con fines de demostración. No afiliado a ninguna marca o sitio de subastas mencionado.

---

## 🙋‍♂️ Autor

Portfolio de desarrollo backend + scraping + integración con IA.
