FROM node:24-alpine AS frontend-builder

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm install

COPY frontend/ ./
RUN npm run build


FROM python:3.13-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system supportoid && adduser --system --ingroup supportoid supportoid

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip && python -m pip install -r /app/requirements.txt

COPY src /app/src
COPY deploy /app/deploy
COPY docs /app/docs
COPY data /app/data
COPY README.md LICENSE NOTICE CONTRIBUTING.md SECURITY.md CODE_OF_CONDUCT.md /app/
COPY docker-compose.yml /app/docker-compose.yml
COPY --from=frontend-builder /frontend/dist /app/frontend/dist

RUN mkdir -p /app/data/runtime && chown -R supportoid:supportoid /app

USER supportoid

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import json, urllib.request; data=json.load(urllib.request.urlopen('http://127.0.0.1:8001/api/v1/health', timeout=3)); raise SystemExit(0 if data.get('status') in {'healthy', 'degraded'} else 1)"

CMD ["python", "-m", "src.cli", "serve"]
