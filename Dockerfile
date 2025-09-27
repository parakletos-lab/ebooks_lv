# syntax=docker/dockerfile:1.7

#######################################################################
# Calibre-Web + Plugins Image
#
# Expected Repository Layout (relative to build context):
#   calibre-web/                  (git submodule with upstream code)
#   entrypoint/entrypoint_mainwrap.py (upstream main interception entrypoint)
#   plugins/users_books/...       (example plugin structure)
#
# Build:
#   docker build -t calibre-web-server .
#
# Run (example):
#   docker run -p 8083:8083 \
#     -e CALIBRE_WEB_PLUGINS=users_books \
#     -v $PWD/config:/app/config \
#     -v $PWD/var/data:/app/data \
#     calibre-web-server
#
# Environment Variables:
#   CALIBRE_WEB_PLUGINS   Comma-separated list of plugin import names (default: users_books)
#   CALIBRE_WEB_HOST      Bind host (default: 0.0.0.0)
#   CALIBRE_WEB_PORT      Port (default: 8083)
#   CALIBRE_WEB_DEBUG     If set to 1/true, enables Flask debug mode (dev only)
#
#######################################################################

############################
# Stage: base (deps layer)
############################
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System dependencies (adjust as needed for Calibre-Web optional features)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo libpng16-16 libmagic1 ghostscript \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only requirements first to maximize layer caching.
# IMPORTANT: The submodule must be initialized before building.
# If calibre-web/requirements.txt is missing the build will fail.
COPY calibre-web/requirements.txt ./calibre-web/requirements.txt

RUN pip install --upgrade pip setuptools wheel \
    && pip install -r calibre-web/requirements.txt

############################
# Stage: runtime
############################
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_HOME=/app \
    CALIBRE_WEB_PLUGINS=users_books \
    CALIBRE_WEB_HOST=0.0.0.0 \
    CALIBRE_WEB_PORT=8083

# (Optional) Create a non-root user for better security
ARG APP_UID=1000
ARG APP_GID=1000
RUN groupadd -g "${APP_GID}" appuser \
    && useradd -u "${APP_UID}" -g "${APP_GID}" -s /usr/sbin/nologin -d /nonexistent appuser \
    && mkdir -p /app /app/config /app/data \
    && chown -R appuser:appuser /app

WORKDIR /app

# Minimal runtime libs (mirror those from base if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo libpng16-16 libmagic1 ghostscript \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from base
COPY --from=base /usr/local/lib/python3.11 /usr/local/lib/python3.11
COPY --from=base /usr/local/bin /usr/local/bin

# Copy application code (submodule + entrypoint + plugins + mainwrap)
COPY calibre-web ./calibre-web
COPY entrypoint ./entrypoint
COPY plugins ./plugins

# Set PYTHONPATH so entrypoint/start.py can import:
#  - cps (from calibre-web)
#  - plugin packages (users_books, etc.)
ENV PYTHONPATH=/app/calibre-web:/app/plugins:/app

# Expose the Flask / Calibre-Web port
EXPOSE 8083

# Optional healthcheck hitting a simple plugin health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD python -c "import os,urllib.request,sys,json;port=os.environ.get('CALIBRE_WEB_PORT','8083');url=f'http://127.0.0.1:{port}/plugin/users_books/health';\n"\
    "import urllib.request;"\
    "\ntry:\n    r=urllib.request.urlopen(url,timeout=3); body=r.read(256).decode('utf-8','ignore');"\
    "\n    ok=('\"status\"' in body and 'ok' in body); print('healthy' if ok else 'unhealthy:body'); sys.exit(0 if ok else 1)"\
    "\nexcept Exception as e:\n    print('unhealthy',e); sys.exit(1)"

USER appuser

# Entrypoint: run seed (idempotent) then upstream main interception wrapper
# For production, replace python dev server with gunicorn (example commented below)
# CMD ["gunicorn", "-b", "0.0.0.0:8083", "entrypoint.entrypoint_mainwrap:app"]
CMD ["sh", "-c", "python entrypoint/seed_settings.py && python entrypoint/entrypoint_mainwrap.py"]
