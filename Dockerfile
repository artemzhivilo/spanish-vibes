FROM python:3.12-slim

WORKDIR /app

# Copy dependency definition first (better layer caching)
COPY pyproject.toml ./

# Install dependencies only (not the project itself)
RUN pip install --no-cache-dir fastapi uvicorn jinja2 python-multipart PyYAML markdown openai feedparser

# Copy the full project
COPY . .

# Ensure data directory exists and is writable
RUN mkdir -p /app/data

# Production defaults
ENV HOST=0.0.0.0
ENV PORT=8000
ENV PYTHONPATH=/app/src

EXPOSE 8000

CMD ["python", "-m", "spanish_vibes"]
