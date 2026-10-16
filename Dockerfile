FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /uvx /bin/

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock LICENSE README.md ./
COPY src ./src
COPY scripts ./scripts
COPY select_entry_batch.py ./

RUN uv sync --locked --python 3.12

ENTRYPOINT ["uv", "run", "--no-sync", "python", "scripts/run_competition_batch.py"]
