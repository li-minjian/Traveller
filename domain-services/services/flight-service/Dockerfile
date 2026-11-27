# Flight Service (endpoint of domain-services/contract/openapi.yaml). Build and run from this folder:
#   docker build -t flight-service .
#   docker run --rm -p 8101:8000 --env-file ../../../.env flight-service
FROM python:3.14.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

RUN useradd --uid 1000 --create-home app
COPY --chown=app:app src/ ./src/
USER app

WORKDIR /app/src
EXPOSE 8000
CMD ["uvicorn", "main:create_app_from_env", "--factory", "--host", "0.0.0.0", "--port", "8000"]
