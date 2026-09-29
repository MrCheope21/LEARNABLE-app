FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Exact, tested versions (requirements.lock), not whatever is newest on the day of the build.
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app

# The app runs as a non-root user that can't write to /app, so the document storage directory
# (STORAGE_LOCAL_DIR's default) is created up front and owned by that user. docker-compose.yml
# mounts a volume here so uploaded files survive container rebuilds, like the database does.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/var/documents \
    && chown -R appuser:appuser /app/var
USER appuser

# Migrations are deliberately NOT run here: with several replicas they'd race. Run
# `alembic upgrade head` as a separate deploy step (docker-compose.yml does it for local dev).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
