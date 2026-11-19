# One image for the worker and the API. It holds dependencies only: the code is
# mounted read-only by docker-compose.yml, so a code update reaches the offline
# server as a small folder or git bundle rather than a new image
# (docs/decisions/0001-code-mounted-not-baked.md).
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1

COPY docker/requirements.lock /tmp/requirements.lock
# Wheels only and hash-checked, so the image is reproducible and needs no compilers.
RUN pip install --require-hashes --only-binary=:all: -r /tmp/requirements.lock \
 && rm /tmp/requirements.lock

# rasterio's bundled GDAL links against the system expat library, which slim images omit.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libexpat1 \
 && rm -rf /var/lib/apt/lists/*

RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin atlas
WORKDIR /app
ENV PYTHONPATH=/app
USER 10001:10001
