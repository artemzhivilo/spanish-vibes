FROM python:3.12-slim

WORKDIR /app

# Install system deps for psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency definition first (better layer caching)
COPY pyproject.toml ./

# Install Python dependencies
RUN pip install --no-cache-dir \
    fastapi uvicorn[standard] jinja2 python-multipart \
    python-dotenv anthropic psycopg2-binary

# Copy the app
COPY app/ ./app/

# Production defaults
ENV PORT=8000
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
