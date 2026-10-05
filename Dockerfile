# syntax=docker/dockerfile:1.7
#
# All-in-one image: API, background worker, folder watcher and web UI in one
# container. Postgres and Redis run as their own containers (deploy/compose.yaml).
# Published by CI as ghcr.io/bhusallaxman22/camera-dashboard.

ARG NODE_VERSION=24
ARG PYTHON_VERSION=3.12

# Debian-based Node so the standalone server's native modules match the glibc runtime.
FROM node:${NODE_VERSION}-bookworm-slim AS web-deps
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:${NODE_VERSION}-bookworm-slim AS web-build
WORKDIR /web
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=web-deps /web/node_modules ./node_modules
COPY frontend/ ./
RUN npm run build

FROM node:${NODE_VERSION}-bookworm-slim AS node

FROM python:${PYTHON_VERSION}-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Debian's packaged exiftool predates the Z6III; keep in sync with backend/Dockerfile.
ARG EXIFTOOL_VERSION=13.59
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        perl ffmpeg curl ca-certificates libglib2.0-0 tini \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL "https://github.com/exiftool/exiftool/archive/refs/tags/${EXIFTOOL_VERSION}.tar.gz" \
        | tar -xz -C /opt \
    && mv "/opt/exiftool-${EXIFTOOL_VERSION}" /opt/exiftool \
    && ln -s /opt/exiftool/exiftool /usr/local/bin/exiftool \
    && exiftool -ver

ARG YUNET_SHA256=8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4
RUN mkdir -p /opt/models \
    && curl -fsSL -o /opt/models/face_detection_yunet_2023mar.onnx \
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx" \
    && echo "${YUNET_SHA256}  /opt/models/face_detection_yunet_2023mar.onnx" | sha256sum -c -

COPY --from=node /usr/local/bin/node /usr/local/bin/node

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
COPY backend/app ./app

COPY --from=web-build /web/.next/standalone /web
COPY --from=web-build /web/.next/static /web/.next/static
COPY --from=web-build /web/public /web/public

COPY --chmod=755 docker/entrypoint.sh /usr/local/bin/z6iii

ENV HOME=/tmp \
    NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    FACE_MODEL_PATH=/opt/models/face_detection_yunet_2023mar.onnx \
    EXIFTOOL_PATH=/usr/local/bin/exiftool \
    BACKEND_INTERNAL_URL=http://127.0.0.1:8000 \
    PUID=568 \
    PGID=568

ARG GIT_SHA=unknown
LABEL org.opencontainers.image.title="Z6III AI Studio" \
      org.opencontainers.image.description="Self-hosted Nikon Z6III photo workflow: live ingest, RAW+JPEG pairing, previews, analysis and culling" \
      org.opencontainers.image.revision="${GIT_SHA}"

VOLUME ["/data"]
EXPOSE 3000 8000
HEALTHCHECK --interval=30s --timeout=20s --start-period=90s --retries=3 CMD ["z6iii", "healthcheck"]
ENTRYPOINT ["/usr/bin/tini", "--", "z6iii"]
CMD ["all"]
