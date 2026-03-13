# Stage 1: Build frontend
FROM node:18-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2: Runtime
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /uvx /bin/

# Create non-root user
RUN groupadd -r mirofish && useradd -r -g mirofish -m mirofish

WORKDIR /app

# Install Python dependencies
COPY backend/pyproject.toml backend/uv.lock ./backend/
RUN cd backend && uv sync --frozen

# Copy backend source
COPY backend/ ./backend/

# Copy built frontend
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# Copy root files
COPY package.json ./

RUN chown -R mirofish:mirofish /app
USER mirofish

EXPOSE 5001

CMD ["backend/.venv/bin/python", "backend/run.py"]
