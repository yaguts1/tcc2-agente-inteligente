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

> **Isto não é proteção contra perda do servidor.** Backup no mesmo volume
> cobre erro de operação, corrupção de banco e migração malfeita. Não cobre
> disco morto, VM apagada nem ransomware. Copiar `/data/backups` para fora da
> máquina, com a periodicidade que a instituição exigir, é uma decisão de
> infraestrutura que este sistema não toma sozinho.

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
