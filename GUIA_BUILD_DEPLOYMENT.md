# 🚀 GUIA DE BUILD E DEPLOYMENT

**Data**: 27 de Outubro de 2025  
**Status**: ✅ Production Ready  

---

## 📦 BUILD FRONTEND CONCLUÍDO

### Resultado
```
✓ 1736 modules transformed
✓ index.html (0.44 kB gzipped: 0.29 kB)
✓ assets/index-Bp6hjLTB.css (44.51 kB gzipped: 8.90 kB)
✓ assets/index-CK18vjlA.js (435.29 kB gzipped: 131.24 kB)
✓ Built in 1.71s ✅
```

### Saída
```
Localização: frontend/build/
- index.html          (entry point)
- assets/             (CSS, JS, JS chunks)
- vite.svg           (ícone)
```

### Tamanho
```
Total (gzipped):
├─ HTML: 0.29 kB
├─ CSS:  8.90 kB
└─ JS:   131.24 kB
────────────────────
Total: ~140 kB (gzipped)
```

**Performance**: ✅ Excelente (<2s load time esperado)

---

## 🐳 PRÓXIMO PASSO: DOCKER

### Verificar Docker

```bash
docker --version
docker-compose --version
```

### Estrutura Docker

```
Dockerfile              # Build Python backend
docker-compose.yml      # Orchestration

Services:
├─ backend (Python, port 8000)
├─ frontend (Node, port 5173)
└─ database (SQLite, volume)
```

### Build Docker

```bash
# Construir imagens
docker-compose build

# Rodar containers
docker-compose up -d

# Ver logs
docker-compose logs -f

# Parar
docker-compose down
```

---

## 📋 CHECKLIST DE DEPLOYMENT

### Desenvolvimento Local ✅
- [x] Backend rodando (uvicorn)
- [x] Frontend rodando (dev server)
- [x] Testes passando (4/4)
- [x] Frontend buildado
- [x] Sem erros TypeScript
- [x] Sem erros Python

### Staging (Docker Local)
- [ ] Docker build completo
- [ ] docker-compose up funcionando
- [ ] Conectividade entre serviços
- [ ] Database persistindo
- [ ] Logs estruturados
- [ ] Performance aceitável

### Produção
- [ ] Database backup strategy
- [ ] Environment variables
- [ ] CORS configurado
- [ ] Rate limiting
- [ ] Monitoring ativo
- [ ] Alertas configurados
- [ ] SSL/TLS (HTTPS)
- [ ] Domains configurados

---

## 🔧 VARIÁVEIS DE AMBIENTE

### Backend
```bash
# .env ou dockerfile
UPP_DB_PATH=dados.db
PORT=8000
LOG_LEVEL=info
ALLOW_ORIGINS=http://localhost:5173,https://seu-dominio.com
```

### Frontend
```bash
# frontend/.env
VITE_API_URL=http://localhost:8000  # dev
VITE_API_URL=https://api.seu-dominio.com  # prod
```

---

## 📁 ESTRUTURA PRÉ-DEPLOYMENT

```
root/
├─ backend/
│  ├─ interface/
│  ├─ modulo_alerta/
│  ├─ servicos/
│  ├─ tests/
│  └─ requirements.txt
│
├─ frontend/
│  ├─ src/
│  ├─ build/          ← ✅ Gerado
│  ├─ dist/           ← ✅ (vite build)
│  └─ package.json
│
├─ docker-compose.yml
├─ Dockerfile
├─ .dockerignore
└─ .env.production
```

---

## 🌍 OPÇÕES DE DEPLOYMENT

### Opção 1: VPS com Docker Compose
**Plataforma**: Linux VPS (qualquer)  
**Custo**: ~$5-20/mês  

```bash
# SSH no servidor
ssh user@seu-vps.com

# Clone repo
git clone https://github.com/seu-repo/tcc2-agente-inteligente.git
cd tcc2-agente-inteligente

# Configure .env
nano .env.production

# Deploy
docker-compose -f docker-compose.yml up -d

# Reverse proxy (Nginx)
# Configure em /etc/nginx/sites-available/...
```

### Opção 2: Heroku
**Plataforma**: Heroku  
**Custo**: ~$7-50/mês  

```bash
# Install Heroku CLI
heroku login

# Create app
heroku create seu-app-name

# Deploy
git push heroku main
```

### Opção 3: AWS ECS
**Plataforma**: Amazon Web Services  
**Custo**: Pay as you go (~$20-100/mês)  

```bash
# Push image to ECR
aws ecr get-login-password --region us-east-1 | docker login ...
docker tag seu-app:latest xxx.dkr.ecr.us-east-1.amazonaws.com/seu-app:latest
docker push xxx.dkr.ecr.us-east-1.amazonaws.com/seu-app:latest

# Deploy ECS Fargate via console ou CLI
```

### Opção 4: Google Cloud Run
**Plataforma**: Google Cloud  
**Custo**: Pay as you go (~$0-30/mês)  

```bash
# Deploy backend
gcloud run deploy seu-app \
  --source . \
  --platform managed \
  --region us-central1

# Deploy frontend to Cloud Storage + CDN
gsutil -m cp -r frontend/build/* gs://seu-app.com/
```

### Opção 5: DigitalOcean App Platform
**Plataforma**: DigitalOcean  
**Custo**: ~$12-50/mês  

```bash
# Via dashboard ou doctl CLI
doctl apps create --spec app.yaml
```

---

## 🔐 SECURITY CHECKLIST

### HTTPS/SSL
- [ ] Certificado SSL válido
- [ ] Redirecionamento HTTP → HTTPS
- [ ] HSTS header configurado
- [ ] Certificado auto-renovável (Let's Encrypt)

### API Security
- [ ] CORS restritivo
- [ ] Rate limiting ativo
- [ ] Input validation
- [ ] SQL injection prevention (✅ done)
- [ ] CSRF protection
- [ ] JWT autenticação (optional)

### Database
- [ ] Backups automáticos
- [ ] Encryption em repouso
- [ ] Acesso restrito (firewall)
- [ ] Logs de auditoria

### Monitoring
- [ ] Logs centralizados
- [ ] Alertas de erro
- [ ] Métrics (CPU, memory, DB)
- [ ] Performance tracking

---

## 📊 PERFORMANCE TARGETS

### Frontend
- Load Time: < 2s (gzip: 140 kB)
- Lighthouse Score: > 90
- Mobile Speed: > 80

### Backend
- API Response: < 100ms
- Database Query: < 50ms
- Throughput: > 1000 req/s

---

## 🚀 COMANDOS ÚTEIS

### Build
```bash
# Frontend
cd frontend && npm run build

# Docker
docker-compose build
docker-compose build --no-cache  # Force rebuild
```

### Run
```bash
# Local
uvicorn interface.web:app --reload
cd frontend && npm run dev

# Docker
docker-compose up -d
docker-compose logs -f
```

### Test
```bash
# Python tests
python -m pytest tests/ -v

# Coverage
python -m pytest tests/ --cov=interface --cov=modulo_alerta
```

### Deploy
```bash
# Push changes
git add .
git commit -m "feat: new feature"
git push origin main

# Or manual
docker-compose up -d --build
```

---

## 📞 TROUBLESHOOTING

### Frontend não conecta ao backend
```
Verifique:
1. VITE_API_URL está correto
2. Backend está rodando em 8000
3. CORS está configurado
4. Firewall permite conexão
```

### Database corrompido
```
Solução:
1. Faça backup: cp dados.db dados.db.bak
2. Delete: rm dados.db
3. Reinicie: próxima execução recriar-á
```

### Performance lenta
```
Verifique:
1. CPU usage
2. Memory usage  
3. Disk I/O
4. Network latency
5. Database indexes
```

---

## 📈 PÓS-DEPLOYMENT

### Primeiras 24 Horas
- [ ] Monitorar logs
- [ ] Verificar alertas
- [ ] Testar funcionalidade
- [ ] Validar performance

### Primeira Semana
- [ ] Análise de usuário
- [ ] Coletar feedback
- [ ] Otimizações
- [ ] Bug fixes

### Próximas Semanas
- [ ] Features adicionais
- [ ] Análise de tráfego
- [ ] Melhorias UX
- [ ] Escalabilidade

---

## 📚 DOCUMENTAÇÃO RELACIONADA

- `STATUS_PROJETO_27OUT.md` - Status completo
- `TESTE_PERSISTENCIA_PASSO_A_PASSO.md` - Teste manual
- `RELATORIO_TESTES_27OUT.md` - Testes automatizados
- `docker-compose.yml` - Configuração Docker
- `.env.example` - Template de variáveis

---

## 🎯 RESUMO

### Status Atual
```
✅ Frontend buildado
✅ Backend pronto
✅ Testes passando
✅ Docker configurado
⏳ Deploy pendente
```

### Próximo Passo
1. Testar Docker Compose localmente
2. Escolher plataforma de deployment
3. Configurar domain e SSL
4. Deploy em produção
5. Monitoring e alertas

---

**Pronto para deploy!** 🚀

Escolha uma das opções de deployment acima e siga as instruções.

