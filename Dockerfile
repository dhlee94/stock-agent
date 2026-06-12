# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata ca-certificates build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# BuildKit cache mount: pip downloads are reused across rebuilds (torch ~500MB 등 재다운로드 방지)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip setuptools wheel
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt
# uni2ts has conflicting pins (scipy, torch); install core deps first, then uni2ts --no-deps
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install lightning gluonts hydra-core jaxtyping datasets tensorboard orjson multiprocess
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-deps uni2ts

# web_crawl uses Playwright's headless Chromium. The pip package alone ships no
# browser binary, so crawl_url fails with "Executable doesn't exist" until we
# install chromium + its OS-level deps here.
RUN playwright install --with-deps chromium

# Pre-build matplotlib's font cache at build time (after all fonts, incl. the
# emoji font pulled in by playwright's deps, are installed). The cache is baked
# into the image, so at runtime matplotlib loads it silently instead of
# re-scanning fonts and logging "Failed to extract ... NotoColorEmoji.ttf
# (Non-scalable fonts are not supported)" / "generated new fontManager".
RUN python -c "import matplotlib.pyplot"

COPY src/ ./src/

RUN mkdir -p /app/data
VOLUME ["/app/data"]

# Default: run the daily scheduler. docker-compose overrides this for the
# web service.
CMD ["python", "-m", "scheduler.main"]
