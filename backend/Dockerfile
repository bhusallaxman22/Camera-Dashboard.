FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Debian's packaged exiftool predates the Z6III; pin a current release so the
# Nikon maker notes (lens, AF, shutter count, picture control) decode fully.
ARG EXIFTOOL_VERSION=13.59

# perl:     exiftool runtime
# ffmpeg:   video poster frames
# curl:     container healthcheck + exiftool download
# libglib2.0-0: required by opencv-python-headless
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        perl ffmpeg curl ca-certificates libglib2.0-0 tini \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL "https://github.com/exiftool/exiftool/archive/refs/tags/${EXIFTOOL_VERSION}.tar.gz" \
        | tar -xz -C /opt \
    && mv "/opt/exiftool-${EXIFTOOL_VERSION}" /opt/exiftool \
    && ln -s /opt/exiftool/exiftool /usr/local/bin/exiftool \
    && exiftool -ver

# YuNet face detector (OpenCV Zoo, MIT) — gives face boxes + eye landmarks.
ARG YUNET_SHA256=8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4
RUN mkdir -p /opt/models \
    && curl -fsSL -o /opt/models/face_detection_yunet_2023mar.onnx \
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx" \
    && echo "${YUNET_SHA256}  /opt/models/face_detection_yunet_2023mar.onnx" | sha256sum -c -
ENV FACE_MODEL_PATH=/opt/models/face_detection_yunet_2023mar.onnx

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini docker-entrypoint.sh ./
COPY migrations ./migrations
COPY app ./app
RUN chmod +x /app/docker-entrypoint.sh

# Writable HOME for any library caches when running as an arbitrary UID.
ENV HOME=/tmp

EXPOSE 8000
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/app/docker-entrypoint.sh", "api"]
