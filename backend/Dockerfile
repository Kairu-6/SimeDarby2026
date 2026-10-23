FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 HF_HOME=/models DATABASE_PATH=/data/simeloop.sqlite3
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra vision
COPY app ./app
EXPOSE 8000
CMD ["uv", "run", "--frozen", "--no-dev", "--extra", "vision", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
