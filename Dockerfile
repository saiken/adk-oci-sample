FROM astral/uv:python3.13-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    HOST=0.0.0.0 \
    PORT=8000

WORKDIR /app

RUN useradd --create-home --uid 10001 appuser

# Install locked deps into the uv environment (includes python-dotenv)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .

USER appuser

EXPOSE 8000

CMD ["uv", "run", "python", "main.py"]
