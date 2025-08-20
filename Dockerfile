FROM python:3.11-slim

# Allow statements and log messages to immediately appear in the Knative logs
ENV PYTHONUNBUFFERED=True

USER root
RUN useradd -s /bin/bash dummy && \
    mkdir -p /home/dummy/.cache && \
    chown -R dummy:dummy /home/dummy

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

# Set up uv cache directory with proper permissions
ENV UV_CACHE_DIR=/tmp/uv-cache
RUN mkdir -p /tmp/uv-cache && chmod 777 /tmp/uv-cache

# Copy dependency files for better layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies into cache (this layer will be cached by Docker)
RUN uv sync --frozen --no-install-project --no-dev

# Copy source code and install project (using cached dependencies)
COPY . /app
WORKDIR /app
RUN uv sync --frozen --no-dev && \
    chown -R dummy:dummy /app

USER dummy
ENTRYPOINT ["uv", "run", "fsh"]
