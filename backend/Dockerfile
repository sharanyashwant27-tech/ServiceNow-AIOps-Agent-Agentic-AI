# ServiceNow Agentic AIOps — multi-stage image
# Repo: https://github.com/sharanyashwant27-tech/ServiceNow-AIOps-Agent-Agentic-AI
#
# Build (from repo root):
#   docker build -f backend/Dockerfile -t servicenow-aiops:latest .
# Run:
#   docker run --rm -p 8910:8910 servicenow-aiops:latest
# Full stack:
#   docker compose up --build

FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

ARG APP_VERSION=1.0.0
LABEL org.opencontainers.image.title="ServiceNow Agentic AIOps" \
      org.opencontainers.image.description="Enterprise ServiceNow Agentic AIOps platform (FastAPI + React)" \
      org.opencontainers.image.source="https://github.com/sharanyashwant27-tech/ServiceNow-AIOps-Agent-Agentic-AI" \
      org.opencontainers.image.documentation="https://github.com/sharanyashwant27-tech/ServiceNow-AIOps-Agent-Agentic-AI/blob/main/README.md" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${APP_VERSION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8910

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY --from=frontend /frontend/dist /app/frontend/dist
# Ship project README inside the image for operators / image inspection
COPY README.md /app/README.md

EXPOSE 8910
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8910/health', timeout=3)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8910"]
