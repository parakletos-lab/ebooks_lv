#######################################################################
# Calibre-Web + Integrated App Layer Image
#
# Expected Repository Layout (relative to build context):
#   calibre-web/                  (git submodule with upstream code)
#   entrypoint/entrypoint_mainwrap.py (upstream main interception entrypoint)
#   app/                          (first-party extensions; replaces plugins)
#
# Build:
#   docker build -t calibre-web-server .
#
# Run (example):
#   docker run -p 8083:8083 \
#     -v $PWD/config:/app/config \
#     -v $PWD/var/data:/app/data \
#     calibre-web-server
#
# Environment Variables:
#   CALIBRE_WEB_HOST      Bind host (default: 0.0.0.0)
#   CALIBRE_WEB_PORT      Port (default: 8083)
#   CALIBRE_WEB_DEBUG     If set to 1/true, enables Flask debug mode (dev only)
#
#######################################################################

############################
# Stage: base (deps layer)
############################
FROM public.ecr.aws/docker/library/python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System dependencies (adjust as needed for Calibre-Web optional features)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo libpng16-16 libmagic1 ghostscript curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only requirements first to maximize layer caching.
# IMPORTANT: The submodule must be initialized before building.
# If calibre-web/requirements.txt is missing the build will fail.
COPY calibre-web/requirements.txt ./calibre-web/requirements.txt

RUN pip install --upgrade pip setuptools wheel \
    && pip install -r calibre-web/requirements.txt \
    && pip install gunicorn

############################
# Stage: runtime
############################
FROM public.ecr.aws/docker/library/python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_HOME=/app \
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
    libjpeg62-turbo libpng16-16 libmagic1 ghostscript curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from base
COPY --from=base /usr/local/lib/python3.11 /usr/local/lib/python3.11
COPY --from=base /usr/local/bin /usr/local/bin

# Copy application code (submodule + entrypoint + integrated app layer)
COPY calibre-web ./calibre-web
COPY entrypoint ./entrypoint
COPY app ./app
COPY translations ./translations

# Set PYTHONPATH so entrypoint/start.py can import upstream cps and app layer
ENV PYTHONPATH=/app/calibre-web:/app

# Expose the Flask / Calibre-Web port
EXPOSE 8083

# (Optional) Healthcheck could hit a lightweight upstream route; disabled by default
# HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 CMD curl -f http://127.0.0.1:8083/ || exit 1

USER appuser

# Default CMD keeps dev friendliness; override with prod compose for gunicorn.
CMD ["python", "entrypoint/entrypoint_mainwrap.py"]
