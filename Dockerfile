FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.4.30 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock* ./
COPY src ./src
RUN uv sync --no-dev
EXPOSE 8000
CMD ["uv", "run", "--no-dev", "uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
