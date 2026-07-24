# Stage 1: Build Frontend
FROM node:18-alpine as frontend-build
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
