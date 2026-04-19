# Image combines a Python runtime with Node.js so we can run both the Gemini
# pipeline (Python) and the `lit` PDF screenshot CLI (@llamaindex/liteparse,
# shipped as a Node package).
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# System deps:
#   curl/ca-certificates/gnupg : fetch NodeSource setup script
#   nodejs                     : runtime for lit
#   libnss3, libatk-*, etc.    : Chromium runtime libs (liteparse uses a headless
#                                browser under the hood to render PDF pages)
#   fonts-liberation           : common font fallbacks so screenshots look sane
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        curl ca-certificates gnupg \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends \
        nodejs \
        libnss3 libatk-bridge2.0-0 libatk1.0-0 libcups2 libdrm2 \
        libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 \
        libpango-1.0-0 libpangocairo-1.0-0 libasound2 libatspi2.0-0 \
        libxshmfence1 libx11-xcb1 libxcb-dri3-0 \
        fonts-liberation \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# Install the lit CLI (provides `lit screenshot <pdf> -o <dir>`)
RUN npm install -g @llamaindex/liteparse

WORKDIR /app

# Install Python deps first (leverages Docker layer cache)
COPY req.txt ./
RUN pip install -r req.txt

# Copy only what the app needs
COPY POC1/ ./POC1/

# pdfs/ and POC1/results/ should be bind-mounted from the host (see compose),
# but create empty directories so first-run writes never fail.
RUN mkdir -p /app/pdfs /app/POC1/results

EXPOSE 8501

# Healthcheck: Streamlit's /_stcore/health returns 200 when the app is up.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD curl -fsS http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "POC1/app.py"]
