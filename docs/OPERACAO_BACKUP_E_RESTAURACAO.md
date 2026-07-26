# Backup e restauração

Procedimento operacional. Escrito para quem administra o servidor, não para
quem desenvolveu o sistema.

O ensaio descrito na seção "Restaurar" foi executado de ponta a ponta em
2026-07-26 sobre uma base de 17 MB (80.667 amostras): a aplicação foi parada, o
banco **apagado** e restaurado a partir do backup, com as contagens conferindo
exatamente. Enquanto ninguém apaga o original, uma rotina de backup não está
testada — está apenas configurada.

---

## O que é copiado

Um único arquivo SQLite, `/data/dados.db` dentro do volume `app_data`. Ele
contém tudo: pacientes, amostras de postura, eventos, alertas, agendas,
usuários e a trilha de auditoria.

Os backups ficam em `/data/backups` (configurável por `UPP_BACKUP_DIR`), no
mesmo volume.

> **Backup no mesmo volume não protege contra perda do servidor.** Ele cobre
> erro de operação, corrupção de banco e migração malfeita. Não cobre disco
> morto, VM apagada nem ransomware. Para isso existe a réplica externa, na
> seção "Cópia fora do servidor" abaixo.

## Quando acontece

- **Na subida da aplicação**, sempre. Antes disso o agendador dormia o intervalo
  inteiro primeiro, e uma instalação reiniciada com mais frequência que 24 h
  nunca chegava a fazer backup nenhum.
- **A cada `BACKUP_INTERVAL_HOURS`** (padrão 24).
- **Sob demanda**, em `POST /api/admin/backup/create` (exige papel `admin`).

Cada backup é aberto e conferido logo após ser criado — `PRAGMA
integrity_check`, presença das tabelas essenciais e contagem de linhas. **Se não
passa, o arquivo é apagado e a operação falha.** Um backup ruim no diretório é
pior que nenhum: ele aparece na listagem e passa uma impressão de cobertura que
não existe.

## Conferir se a cobertura está de pé

```bash
curl -s http://SERVIDOR:8000/TCC/api/admin/backup/status -H "Cookie: access_token=..."
```

```json
{"total": 4, "validos": 4, "invalidos": [], "ultimo_valido": "backup_20260726_005023.db",
 "idade_horas": 0.0, "proporcional": true, "saudavel": true}
```

`saudavel: false` significa uma destas coisas, e vale investigar antes de
precisar restaurar:

| Campo | O que indica |
|---|---|
| `ultimo_valido: null` | Nenhum backup íntegro existe |
| `idade_horas` alta | O agendador parou; procurar `backup_scheduler_error` no log |
| `proporcional: false` | O backup mais recente é bem menor que a base viva — provavelmente é backup de **outro** banco |
| `invalidos` não vazio | Há arquivos corrompidos no diretório; os nomes estão na lista |

O mesmo `status` traz um bloco `replicacao`, sobre a cópia fora do servidor —
ver a seção seguinte. Os dois vereditos são separados de propósito: `saudavel`
responde sobre o backup local (erro de operação, corrupção) e
`replicacao.saudavel` sobre perda da VM. Fundir os dois num booleano só
esconderia qual das duas proteções caiu.

## Cópia fora do servidor

Backup no mesmo disco do banco não sobrevive à perda do disco. A réplica
externa é feita por `scripts/replicar_backups.sh`, executado pelo **cron do
host** — não pela aplicação.

**Por que fora da aplicação.** Rodar o `rsync` a partir do processo web exigiria
chave SSH dentro do container e execução de shell a partir da aplicação, e
prenderia o sistema a um transporte só. Do jeito que está, migrar para nuvem é
trocar **uma linha** do script (`rsync` por `rclone copy`, `aws s3 sync`, o que
for); o recibo e a tela continuam iguais.

**Por que a aplicação ainda precisa saber.** Uma replicação que morre calada é
indistinguível de uma que funciona — a mesma falha que backup existe para
evitar. Por isso o script deixa um recibo (`.replicacao.json`, dentro do próprio
diretório de backups) e a aplicação o lê. Erro também gera recibo: é o caso que
mais importa registrar.

### Configurar

Na VM de destino, uma conta só para isto, com chave dedicada:

```bash
# no destino
sudo useradd -m -s /bin/sh backup
sudo -u backup mkdir -p /srv/upp-backups

# na VM da aplicação
ssh-keygen -t ed25519 -f /root/.ssh/id_upp_backup -N ''
ssh-copy-id -i /root/.ssh/id_upp_backup.pub backup@IP_DO_DESTINO
```

No `.env` da aplicação (para a aplicação saber que deve haver réplica):

```
BACKUP_REPLICACAO_INTERVALO_HORAS=24
```

No cron do **host** (não do container):

```cron
0 4 * * * BACKUP_DESTINO=backup@IP_DO_DESTINO:/srv/upp-backups/ \
          BACKUP_SSH_KEY=/root/.ssh/id_upp_backup \
          BACKUP_DESTINO_LABEL=vm-secundaria \
          /caminho/do/projeto/scripts/replicar_backups.sh \
          >> /var/log/upp-replica.log 2>&1
```

`BACKUP_REPLICACAO_INTERVALO_HORAS` precisa bater com a frequência do cron: é
contra ele que a aplicação julga se a réplica está atrasada (com tolerância de
meio intervalo, para um ciclo que atrasa alguns minutos não virar alarme).

Sem a variável, a tela informa que não há réplica configurada — **sem alarme
vermelho**. Alarmar por algo que a instituição não configurou treina a equipe a
ignorar o vermelho, e o vermelho é a única defesa contra a falha calada de
verdade.

### Conferir

Na tela: Admin → Backup → card "Cópia fora do servidor". Por API, o bloco
`replicacao` do `status`:

```json
{"configurada": true, "intervalo_horas": 24, "ok": true, "idade_horas": 3.2,
 "destino": "vm-secundaria", "arquivos": 4, "erro": null, "saudavel": true}
```

| Situação | O que fazer |
|---|---|
| `erro: "nenhuma replicacao registrada"` | O cron nunca rodou; conferir a entrada e o caminho do script |
| `ok: false` | A última tentativa falhou; o motivo está em `erro` e no `/var/log/upp-replica.log` |
| `idade_horas` alta com `ok: true` | O cron parou de disparar; a última execução até funcionou |

> **A réplica também não está testada enquanto ninguém restaurar a partir
> dela.** Vale repetir na VM de destino o ensaio da seção "Restaurar", usando
> um arquivo vindo do `rsync` e não do diretório local.

## Restaurar

O procedimento abaixo é o que foi ensaiado. **Leia inteiro antes de começar.**

### 1. Escolher e conferir o backup

```bash
docker compose exec app python3 -c "
from servicos.backup import BackupService
for b in BackupService('/data/dados.db','/data/backups').verificar_todos():
    print(b['filename'], b['size_mb'], 'MB', 'OK' if b['ok'] else b['motivo'], b['linhas'])"
```

Escolha o mais recente com `OK` e cujas contagens façam sentido para a
instalação. Um arquivo muito menor que os outros é suspeito.

### 2. Preservar o estado atual

Mesmo com o banco corrompido, guarde-o: ele pode conter dados posteriores ao
backup que valem recuperação manual depois.

```bash
docker compose exec app cp /data/dados.db /data/dados.db.antes_da_restauracao
```

### 3. Parar a aplicação

```bash
docker compose stop app
```

Não pule este passo. Restaurar por cima de um SQLite aberto corrompe o
resultado.

### 4. Restaurar

```bash
docker compose run --rm --no-deps -T app python3 -c "
from servicos.backup import BackupService
print(BackupService('/data/dados.db','/data/backups').restore_backup(
    'backup_AAAAMMDD_HHMMSS.db', '/data/dados.db'))"
```

Tem de imprimir `True`. O arquivo é verificado **antes** de ser copiado e o
destino é verificado **depois** — se qualquer uma das duas falhar, nada é
sobrescrito e o motivo vai para o log.

### 5. Subir e conferir

```bash
docker compose up -d app
sleep 10
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/healthz   # 200
docker compose exec app python3 -c "
import sqlite3; c=sqlite3.connect('/data/dados.db')
print({t: c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
       for t in ('pacientes','grade','eventos','alertas')})"
```

As contagens têm de bater com as que o passo 1 mostrou para o backup escolhido.

### 6. Depois

Só apague `/data/dados.db.antes_da_restauracao` quando tiver certeza de que
nada dele é necessário. As migrações rodam sozinhas na subida, então um backup
de uma versão anterior do esquema é atualizado automaticamente.

## O que a restauração NÃO traz de volta

O intervalo entre o último backup e o desastre. Com o padrão de 24 h, pode ser
um dia inteiro de amostras.

As amostras que os ESP32 ainda não tinham entregue **não** se perdem: o firmware
só avança o ponto de retomada sobre evento confirmado pelo servidor e repete
indefinidamente enquanto a falha for temporária (ver
`firmware/esp32_replay/esp32_replay.ino`). Ele reenvia o que ficou pendente
quando a aplicação voltar. O que se perde é o que já estava gravado no servidor
e não entrou no último backup.

Para encurtar essa janela, reduza `BACKUP_INTERVAL_HOURS`. O backup de uma base
de 17 MB levou 132 ms, então o custo de fazê-lo com mais frequência é baixo.

## Retenção

`POST /api/admin/backup/cleanup?keep_days=N` remove os mais antigos que N dias,
**preservando sempre os 3 mais recentes** por mais velhos que sejam. Antes,
`keep_days=0` apagava todos, inclusive o único bom — idade sozinha é critério
perigoso, porque numa instalação parada por um mês todo backup é "velho".
