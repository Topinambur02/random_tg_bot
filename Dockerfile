FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    DATABASE_URL=sqlite+aiosqlite:////app/data/bot.sqlite3

RUN pip install --no-cache-dir uv

COPY pyproject.toml README.md ./
RUN uv sync --no-dev --no-install-project

COPY src ./src

RUN mkdir -p /app/data
VOLUME ["/app/data"]

CMD [".venv/bin/python", "-m", "main"]
