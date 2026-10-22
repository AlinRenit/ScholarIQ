FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

# Tesseract is the local OCR engine (Milestone 2). English language data only;
# add tesseract-ocr-<lang> packages for other scripts.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
 && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 scholariq
WORKDIR /app

COPY pyproject.toml ./
COPY scholariq ./scholariq
RUN pip install .

COPY alembic.ini ./
COPY migrations ./migrations
COPY docker-entrypoint.sh ./
RUN mkdir -p /data/uploads && chown -R scholariq /data

USER scholariq
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health/live')"

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "scholariq.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
