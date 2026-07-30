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

- [ ] Réplica dos backups para fora da VM configurada:
  - [ ] Conta e chave SSH dedicadas criadas na VM de destino
  - [ ] Entrada de cron do host chamando `scripts/replicar_backups.sh`
  - [ ] `BACKUP_REPLICACAO_INTERVALO_HORAS` no `.env`, batendo com a frequência do cron
  - [ ] Admin → Backup → "Cópia fora do servidor" mostra a última réplica
  - [ ] Restauração ensaiada a partir de um arquivo vindo da réplica, não do diretório local
- [ ] Atualização = **puxar a imagem publicada**, não reconstruir:

      ```bash
      git pull                                    # traz compose/Caddyfile/regras
      # o CI imprime a linha exata no resumo do run, com o SHA do commit:
      echo 'UPP_IMAGE=ghcr.io/yaguts1/tcc2-agente-inteligente:sha-<12 chars>' >> .env
      docker compose pull app && docker compose up -d app
      ```

      Por quê: `--build` reconstrói na VM, então a imagem que roda **não é** a
      que passou pelos testes — outra data, outro cache de camadas, outras
      versões resolvidas de dependência não fixada. Pior, o build acontece
      *depois* de derrubar o serviço: um `pip install` que falhe por rede
      quebra a produção no meio da atualização.

      Use a tag por **SHA**, nunca `:main` — `:main` é alvo móvel e não
      identifica o que está no ar. O volume persiste; não precisa recriar.

- [ ] Rollback = trocar `UPP_IMAGE` pelo SHA anterior e repetir os dois
      comandos. É a razão de a tag ser imutável.
