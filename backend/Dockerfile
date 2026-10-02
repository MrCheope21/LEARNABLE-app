# Builds the web client, then the API image that serves both (app/web.py): the browser
# talks to /api on the same origin it was loaded from, so no CORS setup is needed
# (docs/WEB_ARCHITECTURE.md, docs/DEPLOYMENT.md §6). Build context is the repo root
# (render.yaml sets dockerContext: .), so this stage can reach ../web.
FROM node:22-slim AS web-build
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Exact, tested versions (requirements.lock), not whatever is newest on the day of the build.
COPY backend/requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
COPY backend/app ./app
COPY --from=web-build /web/dist ./web-dist

# The app runs as a non-root user that can't write to /app, so the document storage directory
# (STORAGE_LOCAL_DIR's default) is created up front and owned by that user. docker-compose.yml
# mounts a volume here so uploaded files survive container rebuilds, like the database does;
# render.yaml mounts its persistent disk at the same path.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/var/documents \
    && chown -R appuser:appuser /app/var
USER appuser

# Uvicorn reads FORWARDED_ALLOW_IPS whatever command starts it (docker-compose.yml overrides
# the CMD), so request URLs and client IPs reflect the HTTPS proxy in front (Render's load
# balancer, Caddy) instead of this container's own port.
ENV WEB_DIST_DIR=/app/web-dist \
    FORWARDED_ALLOW_IPS=*

# Migrations are deliberately NOT run here: with several replicas they'd race. Run
# `alembic upgrade head` as a separate deploy step (docker-compose.yml does it for local dev;
# render.yaml runs it as a pre-deploy command). Render (and most hosts) assign the port via $PORT.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
