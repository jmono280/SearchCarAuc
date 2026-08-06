# Etapa base ligera con Python 3.12
FROM python:3.12-slim

WORKDIR /app

# Evita prompts de apt y reduce capas
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright \
    APP_PORT=8000

# Instala dependencias de sistema necesarias para Playwright/Chromium
# y curl para el healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    ca-certificates \
    fonts-liberation \
    libappindicator3-1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    libxtst6 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Instala dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instala Chromium y sus dependencias de sistema para Playwright
RUN playwright install chromium \
    && playwright install-deps chromium

# Copia el código fuente
COPY . .

# Crea directorio para persistir la sesión de Playwright entre búsquedas
RUN mkdir -p /app/data

# Puerto expuesto por Uvicorn (se puede sobrescribir con APP_PORT)
EXPOSE 8000

# Healthcheck contra la raíz de FastAPI
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD sh -c "curl -f http://localhost:${APP_PORT:-8000}/ || exit 1"

# Comando de arranque: lee APP_PORT desde el entorno
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${APP_PORT:-8000}"]
