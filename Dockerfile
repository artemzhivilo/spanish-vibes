FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first (better cache)
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev --no-editable

# Copy the rest of the application
COPY . .

# Install the project itself
RUN uv sync --frozen --no-dev

# Create data directory for SQLite (writable)
RUN mkdir -p /app/data

# Default environment
ENV HOST=0.0.0.0
ENV PORT=8000

EXPOSE 8000

CMD ["uv", "run", "spanish-vibes"]
