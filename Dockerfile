# Stage 1: Build Frontend
# Node 20: o 18 esta em EOL, varias deps do frontend pedem >=20.19 (avisos
# EBADENGINE no npm ci) e o @tailwindcss/vite e ESM-only — sob o 18 o vite
# carrega o config como CommonJS e o build morre com ERR_REQUIRE_ESM.
# O frontend/Dockerfile ja usava node:20; este aqui e que estava defasado.
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
    # Build with base path /TCC/
    RUN chmod +x node_modules/.bin/vite
    RUN npm run build -- --base=/TCC/

# Stage 2: Python App
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl tzdata && apt-get clean

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt uvicorn[standard]

COPY . .

# Copy built frontend from previous stage
COPY --from=frontend-build /app/frontend/build /app/frontend/build

EXPOSE 8000

# Default prefix. O sistema roda em hospitais no Brasil e várias partes do
# código usam datetime.now() sem timezone explícito assumindo este fuso
# (ver ferramentas/exportador.py, dao.py) — TZ precisa bater com isso.
ENV APP_PREFIX=/TCC
ENV TZ=America/Sao_Paulo

CMD ["uvicorn", "interface.web:app", "--host", "0.0.0.0", "--port", "8000"]
