FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata ca-certificates build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel
RUN pip install --no-cache-dir -r requirements.txt
# uni2ts has conflicting pins (scipy, torch); install core deps first, then uni2ts --no-deps
RUN pip install --no-cache-dir lightning gluonts hydra-core jaxtyping datasets tensorboard orjson multiprocess
RUN pip install --no-cache-dir --no-deps uni2ts

COPY src/ ./src/

RUN mkdir -p /app/data
VOLUME ["/app/data"]

# Default: run the daily scheduler. docker-compose overrides this for the
# web service.
CMD ["python", "-m", "scheduler.main"]
