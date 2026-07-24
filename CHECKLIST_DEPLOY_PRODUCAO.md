# Checklist de Deploy em Produção

Passo a passo completo está em [`GUIA_BUILD_DEPLOYMENT.md`](GUIA_BUILD_DEPLOYMENT.md). Esta é só a lista de verificação rápida antes/depois de subir uma instância nova.

## Antes de subir

- [ ] `pytest -q` passa localmente (ver comando em `GUIA_BUILD_DEPLOYMENT.md`)
- [ ] DNS do domínio já aponta para o IP da VM (`dig +short seudominio.com`)
- [ ] Firewall/security group da VM libera só as portas 80 e 443 (não a 8000)
- [ ] `.env` criado a partir de `.env.example` com:
  - [ ] `DOMAIN` configurado com o domínio real
  - [ ] `JWT_SECRET_KEY` gerado (não deixado vazio — o app recusa subir sem isso quando `ENVIRONMENT=production`)
  - [ ] `ALLOWED_ORIGINS` configurado se necessário
  - [ ] `UPP_ADMIN_PASS`/`UPP_ADMIN_TOKEN` definidos apenas se for usar os endpoints administrativos legados

## Depois de subir

- [ ] `docker compose logs caddy` mostra `certificate obtained successfully`
- [ ] `curl -f https://seudominio.com/healthz` responde `{"status":"ok"}`
- [ ] Login funciona e o dashboard carrega
- [ ] Um evento de teste chega via `/api/eventos` ou WebSocket e aparece no dashboard
- [ ] Backup automático confirmado nos logs após o primeiro ciclo (`BACKUP_INTERVAL_HOURS`), ou disparado manualmente via `/admin/backup/create`

## Rotina operacional

- [ ] Backups copiados periodicamente para fora da VM (`docker cp`/`rsync`, ver guia)
- [ ] Atualização = `git pull` + `docker compose up -d --build` (volume persiste, não precisa recriar)
