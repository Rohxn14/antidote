# Antidote: one container serving the web app and its API.
#   docker build -t antidote .
#   docker run -p 8000:8000 --env-file .env.cloud antidote

# 1. Build the web app (React + Vite) into static files.
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# 2. The API (FastAPI) serves those files and talks to FalkorDB.
FROM python:3.12.10-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ app/
COPY api/ api/
COPY scripts/ scripts/
COPY data/ data/
COPY docs/ docs/
COPY scenarios/ scenarios/
COPY --from=web /web/dist web/dist
EXPOSE 8000
CMD ["sh", "-c", "uvicorn api.server:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
