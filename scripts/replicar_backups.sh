#!/bin/sh
# Copia os backups para FORA da VM e deixa um recibo que a aplicação lê.
#
# Por que o transporte fica aqui, e não dentro da aplicação
# --------------------------------------------------------
# Rodar o rsync a partir do processo web exigiria chave SSH dentro do
# container, execução de shell a partir da aplicação e acoplamento a um
# transporte só. Aqui, trocar de destino é editar UMA linha: quem for para
# nuvem substitui o `rsync` por `rclone copy`, `aws s3 sync` ou o que for, e o
# resto — inclusive o que a tela mostra — continua igual.
#
# Por que existe um recibo
# ------------------------
# Uma replicação que morre calada é indistinguível de uma que funciona, e essa
# é justamente a falha que backup existe para evitar. O recibo é o contrato com
# a aplicação: ela o lê e responde "a cópia externa está de pé?" em
# /api/admin/backup/status, do mesmo jeito que já responde sobre os backups
# locais. Um erro aqui PRECISA gerar recibo — por isso ele é escrito também no
# caminho de falha.
#
# Uso (cron do HOST, não do container):
#   0 4 * * * /caminho/scripts/replicar_backups.sh >> /var/log/upp-replica.log 2>&1
#
# Configuração: variáveis de ambiente ou um arquivo .env ao lado do compose.
#   BACKUP_DESTINO   obrigatório  ex: backup@10.0.0.9:/srv/upp-backups/
#   BACKUP_SSH_KEY   opcional     ex: /root/.ssh/id_upp_backup
#   BACKUP_DESTINO_LABEL opcional rótulo exibido na tela (padrão: host do destino)
#   COMPOSE_DIR      opcional     diretório do docker-compose.yml (padrão: pai deste script)
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
COMPOSE_DIR=${COMPOSE_DIR:-$(dirname "$SCRIPT_DIR")}
SERVICO=${BACKUP_SERVICO:-app}
DIR_BACKUPS_CONTAINER=${UPP_BACKUP_DIR:-/data/backups}
RECIBO_NOME=.replicacao.json

inicio=$(date +%s)
staging=$(mktemp -d)
# `trap` e não `rm` no fim: o staging some mesmo se o rsync falhar ou o cron
# matar o processo. Sem isso, uma falha recorrente enche /tmp com cópias do
# banco — dados clínicos esquecidos em diretório temporário.
trap 'rm -rf "$staging"' EXIT INT TERM

escapar_json() {
  # Aspas e barras invertidas quebrariam o JSON do recibo; mensagem de erro do
  # rsync costuma trazer caminho com barra e aspas.
  printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' | tr -d '\n'
}

gravar_recibo() {
  # $1=ok(true|false) $2=arquivos $3=erro
  agora=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  duracao=$(( $(date +%s) - inicio ))
  destino_label=${BACKUP_DESTINO_LABEL:-$(printf '%s' "${BACKUP_DESTINO:-}" | sed 's/:.*//')}
  recibo=$(cat <<JSON
{"terminado_em":"$agora","ok":$1,"arquivos":$2,"duracao_s":$duracao,
 "destino":"$(escapar_json "$destino_label")","erro":"$(escapar_json "$3")"}
JSON
)
  # Escreve DENTRO do volume, que é onde a aplicação enxerga.
  printf '%s' "$recibo" | docker compose -f "$COMPOSE_DIR/docker-compose.yml" \
    exec -T "$SERVICO" sh -c "cat > '$DIR_BACKUPS_CONTAINER/$RECIBO_NOME'" || {
      echo "[ERRO] nao foi possivel gravar o recibo no container" >&2
      return 1
    }
}

falhar() {
  echo "[ERRO] $1" >&2
  gravar_recibo false 0 "$1" || true
  exit 1
}

[ -n "${BACKUP_DESTINO:-}" ] || falhar "BACKUP_DESTINO nao configurado"
command -v rsync >/dev/null 2>&1 || falhar "rsync nao encontrado no host"

# 1) Tira os backups de dentro do volume para uma área de trabalho no host.
#    `docker compose cp` evita depender do mountpoint do volume (que exige
#    root e muda entre versões do Docker).
docker compose -f "$COMPOSE_DIR/docker-compose.yml" \
  cp "$SERVICO:$DIR_BACKUPS_CONTAINER/." "$staging/" \
  || falhar "falha ao extrair os backups do container"

# O recibo da execução anterior vem junto; não faz sentido replicá-lo.
rm -f "$staging/$RECIBO_NOME"

arquivos=$(find "$staging" -name 'backup_*.db' | wc -l | tr -d ' ')
[ "$arquivos" -gt 0 ] || falhar "nenhum backup encontrado em $DIR_BACKUPS_CONTAINER"

# 2) Envia. ESTA é a linha que muda numa migração para nuvem.
#    --delete espelha as remoções da retenção local; troque por --ignore-existing
#    se preferir que o destino acumule para sempre.
if [ -n "${BACKUP_SSH_KEY:-}" ]; then
  RSYNC_RSH="ssh -i $BACKUP_SSH_KEY -o StrictHostKeyChecking=accept-new"
  export RSYNC_RSH
fi

saida_rsync=$(rsync -az --delete --partial "$staging/" "$BACKUP_DESTINO" 2>&1) \
  || falhar "rsync falhou: $saida_rsync"

gravar_recibo true "$arquivos" ""
echo "[OK] $arquivos backup(s) replicados para ${BACKUP_DESTINO_LABEL:-$BACKUP_DESTINO}"
