# 📋 Checklist de Próximos Passos - Deploy em Produção

## ✅ Status Atual

- ✅ Código completo e testado
- ✅ Frontend build otimizado
- ✅ Backend APIs funcionando
- ✅ 0 bugs críticos
- ✅ Documentação extensiva

**Pronto para**: Deploy em Produção

---

## 🚀 PRÉ-DEPLOY CHECKLIST

### 1. Código Preparação

- [ ] Fazer merge de `feat/websocket-esp32` para `main`
  ```bash
  git checkout main
  git merge feat/websocket-esp32
  ```

- [ ] Tag a versão
  ```bash
  git tag -a v1.0.0-prod -m "Production release - todas as features e correções"
  ```

- [ ] Verificar arquivos build
  ```bash
  ls -la frontend/dist/
  ls -la frontend/build/
  ```

### 2. Database Preparação

- [ ] Backup do SQLite atual
  ```bash
  cp tcc.db tcc.db.backup.$(date +%Y%m%d)
  ```

- [ ] Verificar migrations aplicadas
  ```bash
  python -c "from interface.dao import _init_db; _init_db('tcc.db')"
  ```

- [ ] Testar queries críticas
  ```bash
  sqlite3 tcc.db "SELECT COUNT(*) FROM timeline_events;"
  sqlite3 tcc.db "SELECT COUNT(*) FROM alertas;"
  ```

### 3. Environment Setup

- [ ] Copiar `.env.production`
  ```bash
  cp .env.example .env.production
  ```

- [ ] Configurar variáveis (IMPORTANTE):
  - `DATABASE_URL`: caminho do banco em produção
  - `SECRET_KEY`: novo valor seguro
  - `CORS_ORIGINS`: domínios permitidos
  - `LOG_LEVEL`: production (INFO)

- [ ] Validar variáveis
  ```bash
  python -c "import os; os.getenv('SECRET_KEY', 'NOT SET')"
  ```

### 4. Docker Build

- [ ] Build images
  ```bash
  docker-compose -f docker-compose.production.yml build
  ```

- [ ] Verificar images
  ```bash
  docker images | grep "tcc\|agente"
  ```

- [ ] Testar build sem push
  ```bash
  docker-compose -f docker-compose.production.yml up --no-start
  ```

---

## 🔒 SEGURANÇA PRÉ-DEPLOY

- [ ] Revisar `interface/api.py` para credenciais hardcoded
  ```bash
  grep -r "password\|secret\|key" interface/*.py
  ```

- [ ] Configurar CORS corretamente
  ```python
  CORS_ORIGINS = os.getenv("CORS_ORIGINS", "").split(",")
  ```

- [ ] Usar HTTPS em produção
  - [ ] Obter certificado SSL (Let's Encrypt recomendado)
  - [ ] Configurar HTTPS redirect
  - [ ] Testar com: `curl -I https://yourdomain.com`

- [ ] Validar JWT Secret
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(32))"
  ```

- [ ] Remover credenciais de debug
  - [ ] Verificar `main.py` para código debug
  - [ ] Verificar `frontend/.env` para URLs de dev

---

## 🧪 TESTES PRÉ-DEPLOY

### Tests Locais
```bash
# Backend tests
cd /path/to/project
python -m pytest tests/ -v --tb=short

# Frontend build
cd frontend
npm run build
npm run preview  # Preview production build
```

- [ ] Todos os testes passando
- [ ] Build sem warnings
- [ ] Preview sem errors

### Teste Manual em Docker
```bash
docker-compose -f docker-compose.production.yml up -d
sleep 5
curl http://localhost:8000/api/stats
curl http://localhost/  # Frontend
```

- [ ] Backend respondendo em porta 8000
- [ ] Frontend servindo em porta 80
- [ ] Sem logs de erro

### Teste de Conectividade
```bash
# Check backend
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"test","password":"test"}'

# Check WebSocket
wscat -c ws://localhost:8000/api/ws/alerts
```

- [ ] Auth endpoint respondendo
- [ ] WebSocket conectando
- [ ] Sem timeouts

---

## 📦 DEPLOYMENT ESCOLHA DE PLATAFORMA

### Opção 1: Docker + Manual VPS (Recomendado para Controle)
Ver: `GUIA_BUILD_DEPLOYMENT.md` - Opção 1

- [ ] SSH acesso ao servidor configurado
- [ ] Docker + docker-compose instalados
- [ ] Pull/Push do repositório
- [ ] Rodar compose na VPS

### Opção 2: Heroku (Rápido e Gerenciado)
Ver: `GUIA_BUILD_DEPLOYMENT.md` - Opção 2

- [ ] Criar app no Heroku
- [ ] Heroku CLI configurado
- [ ] Procfile criado
- [ ] Deploy com `git push heroku main`

### Opção 3: AWS (Escalável)
Ver: `GUIA_BUILD_DEPLOYMENT.md` - Opção 3

- [ ] EC2 instance criada
- [ ] RDS database (ou SQLite em EBS)
- [ ] Security Groups configurados
- [ ] Load Balancer se necessário

### Opção 4: GCP (Gcloud CLI)
Ver: `GUIA_BUILD_DEPLOYMENT.md` - Opção 4

- [ ] Projeto GCP criado
- [ ] Cloud Run habilitado
- [ ] Dockerfile pronto
- [ ] Deploy com `gcloud run deploy`

### Opção 5: DigitalOcean (Balanceado)
Ver: `GUIA_BUILD_DEPLOYMENT.md` - Opção 5

- [ ] Droplet criado
- [ ] App Platform ou Kubernetes
- [ ] Database gerenciado
- [ ] Deploy com git push

---

## 🚀 DEPLOY EXECUÇÃO

### Passo 1: Push código para produção

```bash
git checkout main
git pull origin main
git push origin main  # Se tiver webhook, já faz deploy
```

- [ ] Código em main
- [ ] Webhook disparado (se configurado)

### Passo 2: Build e push de images

```bash
docker build -t seu-registry/tcc-frontend:latest frontend/
docker build -t seu-registry/tcc-backend:latest .
docker push seu-registry/tcc-frontend:latest
docker push seu-registry/tcc-backend:latest
```

- [ ] Images built
- [ ] Images pushed
- [ ] Registry acessível em produção

### Passo 3: Deploy em produção

**Via docker-compose:**
```bash
ssh seu-servidor
cd /var/app/tcc
git pull
docker-compose -f docker-compose.production.yml pull
docker-compose -f docker-compose.production.yml up -d
```

- [ ] Login SSH bem-sucedido
- [ ] Containers iniciando
- [ ] Portas abertas (80, 443, 8000)

### Passo 4: Smoke Tests em Produção

```bash
# Check se está respondendo
curl https://seu-dominio.com/api/stats

# Check Timeline
curl https://seu-dominio.com/api/timeline?limit=5

# Check login
curl -X POST https://seu-dominio.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}'
```

- [ ] API respondendo com 200
- [ ] Dados sendo retornados
- [ ] HTTPS funcionando

---

## 📊 MONITORAMENTO PÓS-DEPLOY

### Logs em Tempo Real
```bash
docker-compose -f docker-compose.production.yml logs -f
```

- [ ] Verificar logs a cada hora na primeira semana
- [ ] Procurar por erros ou warnings
- [ ] Alertar sobre problemas imediatos

### Métricas Básicas

- [ ] Response time: < 500ms
- [ ] Error rate: < 1%
- [ ] Uptime: > 99%
- [ ] WebSocket connections: verificar spike

### Setup de Monitoring

```bash
# Prometheus scraping
curl http://localhost:9090/api/v1/query?query=up

# Grafana dashboards
http://seu-dominio.com:3000  # Se exposto
```

- [ ] Prometheus rodando
- [ ] Grafana dashboards criados
- [ ] Alertas configurados

### Backup Automático

```bash
# Diário às 2 AM
0 2 * * * /usr/local/bin/backup-db.sh

# Backup script
#!/bin/bash
cp /var/app/tcc/tcc.db /backups/tcc.$(date +%Y%m%d).db
```

- [ ] Script de backup criado
- [ ] Cron job configurado
- [ ] Testes de restore executados

---

## 🔧 TROUBLESHOOTING COMUM

### Container não inicia
```bash
docker-compose logs
docker ps -a  # Ver status
docker-compose -f docker-compose.production.yml down
docker-compose -f docker-compose.production.yml up -d --build
```

### Porta já em uso
```bash
netstat -tulpn | grep :8000
kill -9 $(lsof -t -i :8000)
```

### Database locked
```bash
# Apenas um container acessando por vez
docker-compose scale backend=1
```

### WebSocket desconectando
- Verificar logs para timeouts
- Aumentar keepalive
- Verificar load balancer settings

---

## 📝 DOCUMENTAÇÃO PRODUÇÃO

Copiar para servidor de produção:

- [ ] `GUIA_BUILD_DEPLOYMENT.md` - Como foi feito deploy
- [ ] `RELATORIO_FINAL_SESSAO_27OUT.md` - Status do sistema
- [ ] `CORRECOES_FRONTEND_27OUT.md` - Conhecer as correções
- [ ] README.md - Instruções básicas

---

## 🎯 SUCESSO DEPLOY = QUANDO

- [ ] `curl https://seu-dominio.com` retorna 200
- [ ] Login funciona
- [ ] Dashboard carrega dados
- [ ] Timeline mostra eventos
- [ ] WebSocket conecta
- [ ] 0 errors em logs
- [ ] Testes passam

---

## 📞 SUPORTE

### Se algo der errado

1. Verificar logs imediatamente
   ```bash
   docker-compose logs backend frontend
   ```

2. Reverter último deploy
   ```bash
   git revert HEAD
   git push
   docker-compose restart
   ```

3. Abrir issue no repositório
   - Incluir logs
   - Descrever o que fez
   - Timestamp do problema

### Contatos Importantes

- Lead: [seu-email]
- DevOps: [devops-email]
- Database: [db-admin]

---

## 🎓 APRENDIZADOS IMPORTANTES

1. **Sempre testar em staging primeiro**
2. **Ter rollback plan antes de deploy**
3. **Monitorar logs na primeira hora**
4. **Database backups antes de qualquer migração**
5. **WebSocket é stateful - testar load balancing**

---

## ✅ Checklist Final

- [ ] Código em main
- [ ] Tests passando
- [ ] Build funcionando
- [ ] Ambiente configurado
- [ ] Backup executado
- [ ] Plataforma escolhida
- [ ] Deploy realizado
- [ ] Smoke tests ok
- [ ] Monitoramento setup
- [ ] Documentação atualizada

**Quando TUDO estiver marcado → Deploy bem-sucedido! 🎉**

---

**Data**: 27 de Outubro de 2025  
**Status**: Pronto para Deploy  
**Próximo**: Executar este checklist
