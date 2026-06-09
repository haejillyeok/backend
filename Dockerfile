FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_MODULE=be \
    HOST=0.0.0.0 \
    PORT=8000 \
    WORKERS=1

WORKDIR /app

RUN groupadd --system app \
    && useradd --system --gid app --create-home app

COPY pyproject.toml README.md ./
COPY app ./app

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir . \
    && find /app -type d -name __pycache__ -prune -exec rm -rf {} + \
    && find /app -type f -name "*.pyc" -delete

USER app

EXPOSE 8000 8001

CMD ["sh", "-c", "exec uvicorn \"app.${APP_MODULE}.main:app\" --host \"$HOST\" --port \"$PORT\" --workers \"$WORKERS\""]
