# Guia de Build e Deploy

Este guia descreve o único caminho de deploy suportado atualmente: **uma VM na nuvem + Docker Compose**, com HTTPS automático via Caddy. É a opção mais simples de operar sozinho, sem depender de orquestradores (Kubernetes, ECS, Cloud Run) — o sistema é projetado para rodar em **uma única instância** (ver seção "Limitações de escala" abaixo).

---

## Arquitetura de deploy

```
Internet ──▶ Caddy (80/443, HTTPS automático) ──▶ app (FastAPI + SPA, porta 8000)
                                                        │
                                                        ▼
                                              volume Docker "app_data"
                                              (dados.db, paciente_docs/, backups/)
```

Dois containers (`docker-compose.yml`):
- **`app`**: build multi-stage do `Dockerfile` (frontend React buildado + backend FastAPI na mesma imagem `python:3.11-slim`). Serve a API e a SPA no mesmo processo/porta.
- **`caddy`**: proxy reverso. Provisiona e renova certificado HTTPS automaticamente via Let's Encrypt quando `DOMAIN` aponta para um domínio real; usa certificado local autoassinado quando `DOMAIN=localhost` (desenvolvimento).

Banco de dados: SQLite em modo WAL, arquivo único dentro do volume `app_data`. Não há banco gerenciado separado — adequado para uma instância; ver limitações abaixo.

---

## Deploy em uma VM (passo a passo)

### 1. Provisionar a VM

Qualquer provedor serve (DigitalOcean Droplet, AWS EC2, GCP Compute Engine, Hetzner, etc.). Requisitos mínimos: 1 vCPU, 1-2GB RAM, Ubuntu 22.04+ (ou qualquer Linux com Docker).

No firewall/security group da VM, abra **apenas as portas 80 e 443** (não a 8000 — essa é só para debug local; em produção o app não deveria ser acessível diretamente de fora).

### 2. Instalar Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# reconecte a sessão SSH para o grupo fazer efeito
```

### 3. Apontar o DNS

Crie um registro `A` do seu domínio (ex: `upp.seudominio.com`) para o IP público da VM. Confirme com `dig +short upp.seudominio.com` antes de seguir — o Caddy precisa que o DNS já esteja resolvendo para conseguir emitir o certificado Let's Encrypt.

### 4. Clonar o repositório e configurar

```bash
git clone https://github.com/yaguts1/tcc2-agente-inteligente.git
cd tcc2-agente-inteligente
cp .env.example .env
```

Edite `.env`:
- `DOMAIN=upp.seudominio.com` (o domínio do passo 3)
- `JWT_SECRET_KEY=` — gere com `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`
- `ALLOWED_ORIGINS=https://upp.seudominio.com` (se for acessar a API de outro domínio; deixe vazio se só o próprio frontend embutido acessa)
- `UPP_ADMIN_PASS`/`UPP_ADMIN_TOKEN` — defina se for usar os logins/endpoints administrativos legados, senão deixe vazio (desabilitado por padrão)

Todas as variáveis estão documentadas em `.env.example`.

### 5. Subir

```bash
docker compose up -d --build
```

Primeira subida demora alguns minutos (build do frontend + emissão do certificado). Acompanhe com:

```bash
docker compose logs -f caddy   # confirma "certificate obtained successfully"
docker compose logs -f app     # confirma "Application startup complete"
```

Acesse `https://upp.seudominio.com` — deve responder com HTTPS válido automaticamente, sem nenhuma configuração manual de certificado.

### 6. Verificar

```bash
curl -f https://upp.seudominio.com/healthz   # {"status":"ok"}
curl -f https://upp.seudominio.com/docs      # Swagger UI
```

---

## Atualizando uma instância em produção

```bash
git pull origin main
docker compose up -d --build
```

O volume `app_data` (banco, uploads, backups) persiste através de rebuilds — não é apagado por `up --build`. Só `docker compose down -v` remove volumes, e isso normalmente não deve ser rodado em produção.

## Backup e restauração

Backup automático já roda dentro do app (task periódica, ver `BACKUP_INTERVAL_HOURS` em `.env.example`, default 24h), salvando em `UPP_BACKUP_DIR` dentro do volume. Endpoints manuais também existem:

```bash
curl -X POST https://upp.seudominio.com/TCC/admin/backup/create -H "Authorization: Bearer $UPP_ADMIN_TOKEN"
curl https://upp.seudominio.com/TCC/admin/backup/list -H "Authorization: Bearer $UPP_ADMIN_TOKEN"
```

Para copiar backups para fora da VM (recomendado — o volume Docker ainda é a mesma máquina), use `docker cp` ou `rsync` periodicamente para outro destino (outra VM, storage de objeto, etc.):

```bash
docker cp upp_app:/data/backups ./backups-local
```

## Rodando os testes antes de fazer deploy

```bash
docker run --rm -v "$(pwd):/app" -w /app python:3.11-slim bash -c \
  "pip install -q -r requirements.txt && pytest -q"
```

(Usa uma imagem `python:3.11-slim` limpa — reproduz fielmente o ambiente do CI, incluindo as versões pinadas em `requirements.txt`.)

---

## Limitações de escala (decisão deliberada)

Este sistema é projetado para **uma única instância**, não múltiplas réplicas atrás de um load balancer:

- **SQLite**: um arquivo único; múltiplos processos escrevendo simultaneamente de VMs diferentes não é suportado (WAL mode ajuda com concorrência dentro do mesmo processo/host, não entre hosts).
- **Rate limiter** (`interface/rate_limiter.py`) e o motor de alertas incremental (`servicos/processamento_incremental.py`) mantêm estado em memória por processo — 2+ réplicas processariam eventos duplicados e teriam limites de taxa inconsistentes.
- **Reconciler de devices e backup automático** (`interface/lifespan_tasks.py`) rodam como tasks in-process sem lock distribuído — 2+ réplicas duplicariam o trabalho.
- **Uploads de documentos** ficam em disco local (dentro do volume Docker) — não há storage de objeto compartilhado.

Se no futuro for necessário escalar horizontalmente (múltiplas VMs/réplicas), isso exige trocar SQLite por Postgres gerenciado, mover rate limiting/estado para Redis compartilhado, e uploads para storage de objeto (S3-compatible) — uma mudança de arquitetura maior, fora do escopo atual.

---

## Alternativas não utilizadas (referência)

Provedores gerenciados (Heroku, AWS ECS, Google Cloud Run, DigitalOcean App Platform) foram considerados mas não são o caminho documentado/testado aqui — a maioria deles assume estado externo (banco gerenciado, storage de objeto) que este sistema não usa hoje. Se decidir migrar para um deles no futuro, resolva primeiro as limitações de escala acima.
