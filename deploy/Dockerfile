# Mock mode by default: no AWS credentials needed.
FROM node:20-slim AS web
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY server ./server
RUN pip install --no-cache-dir .
COPY --from=web /app/web/dist ./web/dist
ENV HUDDLE_MODE=mock HUDDLE_PORT=8000 HUDDLE_DB_URL=sqlite:////data/huddle.db
VOLUME /data
EXPOSE 8000
CMD ["uvicorn", "server.api:app", "--host", "0.0.0.0", "--port", "8000"]
