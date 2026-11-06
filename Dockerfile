FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY app/ ./
RUN uv sync --no-dev
USER 10001:10001

CMD ["/app/.venv/bin/python", "-m", "server.app"]
