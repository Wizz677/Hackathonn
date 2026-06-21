# Sunset — single-service image: builds the React SPA, then serves it together
# with the FastAPI API from one container (one URL, no CORS, self-contained).

# ---- Stage 1: build the React frontend ----
FROM node:22-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build                      # -> /app/frontend/dist

# ---- Stage 2: Python backend that also serves the built SPA ----
FROM python:3.12-slim AS app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app/backend

COPY backend/requirements.txt ./
RUN pip install -r requirements.txt

COPY backend/ ./
# Bring in the compiled SPA so FastAPI can serve it at "/" (see main.py).
COPY --from=frontend /app/frontend/dist /app/frontend/dist

EXPOSE 8000
# Render injects $PORT; fall back to 8000 for local runs. Shell form so $PORT expands.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
