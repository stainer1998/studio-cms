FROM python:3.12-slim

RUN pip install --no-cache-dir "uv>=0.9,<1"
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/venv PATH="/venv/bin:$PATH"

WORKDIR /srv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app
COPY migrations ./migrations

RUN useradd --system --create-home --uid 1000 studio
USER studio

EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-", "app:create_app()"]
