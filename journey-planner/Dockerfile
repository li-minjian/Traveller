# Journey Planner image for local development. Docker Compose mounts the
# source code into /app, so code changes apply without rebuilding the image.
FROM python:3.14.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

RUN useradd --uid 1000 --create-home app
COPY --chown=app:app . .
USER app

EXPOSE 8001

CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-8001} --threads 4 --timeout 100 config.wsgi:application"]
