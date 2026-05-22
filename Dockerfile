# POC2 deployment image.
#
# Slim — no Node, no Chromium, no `lit` CLI. POC2 hands the PDF directly to the
# Gemini Files API and pins an explicit context cache (system instruction +
# PDF). No rasterization, no per-window JSON written to disk; nothing
# persisted between runs.
#
# (POC1's container required Node + Chromium for @llamaindex/liteparse. If
# you still need to run POC1 inside Docker, check out the previous Dockerfile
# from git history — it lives in the same path before this commit.)
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_MAX_UPLOAD_SIZE=1024 \
    STREAMLIT_SERVER_MAX_MESSAGE_SIZE=1024

# Minimal OS deps: curl for the healthcheck, ca-certificates for HTTPS to the
# Gemini API. Nothing else — no graphics stack, no Node toolchain.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        curl ca-certificates \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first so the layer caches across source edits.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Both POC trees ship in the image so the source is browsable on the host,
# but only POC2 is launchable here (POC1 needs the `lit` CLI from Node).
COPY POC2/ ./POC2/

EXPOSE 8501

# Healthcheck: Streamlit's /_stcore/health returns 200 when the app is up.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD curl -fsS http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "POC2/app.py"]
