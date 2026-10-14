# Islas JS del Studio (Tiptap; luego Monaco y GrapesJS), compiladas con esbuild.
FROM node:24-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/src ./src
RUN mkdir -p /app/static/dist && npm run build

FROM python:3.12-slim

RUN pip install --no-cache-dir "uv>=0.9,<1"
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/venv PATH="/venv/bin:$PATH"

WORKDIR /srv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app
COPY --from=frontend /app/static/dist ./app/static/dist
COPY migrations ./migrations

# El volumen de medios hereda el dueño de esta carpeta la primera vez que se monta.
RUN useradd --system --create-home --uid 1000 studio \
    && mkdir -p /srv/storage/media && chown -R studio /srv/storage
USER studio

EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-", "app:create_app()"]
