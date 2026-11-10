# Backend image for local development. Docker Compose mounts the source code
# into /app, so code changes apply without rebuilding the image.
FROM python:3.14.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

# Unprivileged user. UID 1000 matches the first user on most Linux machines,
# so files created through the bind mount (e.g. migrations) belong to them.
RUN useradd --uid 1000 --create-home app
COPY --chown=app:app . .
USER app

EXPOSE 8000

# Django's development server reloads automatically on code changes.
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
