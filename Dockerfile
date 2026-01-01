FROM python:3.14-slim

# Allow statements and log messages to immediately appear in the Knative logs
ENV PYTHONUNBUFFERED=True

USER root
RUN useradd -s /bin/bash dummy

# Install system dependencies and set locale
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        locales \
        gcc \
        libkrb5-dev && \
    localedef -i en_US -c -f UTF-8 -A /usr/share/locale/locale.alias en_US.UTF-8 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files for better layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies (no cache to avoid permission issues)
RUN uv sync --frozen --no-install-project --no-dev --no-cache

# Copy source code and install project
COPY . /app
WORKDIR /app
RUN uv sync --frozen --no-dev --no-cache && \
    chown -R dummy:dummy /app

# Set UV environment variables to prevent cache usage at runtime
ENV UV_NO_CACHE=1
ENV UV_CACHE_DIR=/tmp
ENV PATH="/app/.venv/bin:$PATH"

USER dummy
ENTRYPOINT ["python", "-m", "fsh.main"]
