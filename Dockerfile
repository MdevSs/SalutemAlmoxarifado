FROM node:22-bookworm-slim AS frontend-build
WORKDIR /workspace
RUN corepack enable && corepack prepare pnpm@11.25.0 --activate
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY frontend/package.json ./frontend/package.json
RUN pnpm install --frozen-lockfile
COPY frontend ./frontend
RUN pnpm build

FROM python:3.12.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=3000 \
    PATH="/app/backend/.venv/bin:${PATH}"
WORKDIR /app/backend

RUN pip install --no-cache-dir uv==0.12.19
COPY backend/pyproject.toml backend/uv.lock ./
COPY backend/app ./app
RUN uv sync --locked --no-dev
COPY --from=frontend-build /workspace/frontend/dist /app/frontend/dist

USER 10001:10001
EXPOSE 3000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-3000}"]
