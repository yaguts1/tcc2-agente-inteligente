"""Um backup so vale se restaurar.

Antes, `create_backup` gravava o arquivo, media o tamanho e registrava
`backup_created`. Nada jamais abria o resultado — um arquivo truncado, vazio ou
corrompido produzia o mesmo log de sucesso. A descoberta ficaria para o dia da
restauracao, que e o pior momento possivel para descobrir.

O teste central aqui e o ciclo inteiro: gravar dados, fazer backup, DESTRUIR o
banco original e restaurar. Enquanto ninguem apagou o original, nada foi
provado.
"""

import sqlite3

import pytest

from interface.db_core import criar_esquema
from servicos.backup import (
    MANTER_MINIMO,
    BackupInvalido,
    BackupService,
    verificar_arquivo,
)


@pytest.fixture
def banco(tmp_path):
    """Banco com esquema real e um paciente com historico."""
    db = tmp_path / "dados.db"
    criar_esquema(str(db))
    with sqlite3.connect(db) as conn:
        # So `id`: as demais colunas de `pacientes` vem de migracoes, e o teste
        # nao deve depender de qual ja rodou.
        conn.execute("INSERT INTO pacientes (id) VALUES (?)", ("PAC-BKP",))
        conn.executemany(
            "INSERT INTO grade (paciente_id, ts, postura, confianca) VALUES (?,?,?,?)",
            [("PAC-BKP", f"2026-01-05T{h:02d}:00:00", "supino", 0.9) for h in range(24)],
        )
    return db


@pytest.fixture
def servico(banco, tmp_path):
    return BackupService(str(banco), backup_dir=str(tmp_path / "backups"))


def test_ciclo_completo_com_o_original_destruido(banco, servico, tmp_path):
    """O unico teste que prova alguma coisa: apagar o banco e traze-lo de volta."""
    caminho = servico.create_backup()

    # Destroi o original — nao renomeia, nao move: apaga.
    banco.unlink()
    assert not banco.exists()

    restaurado = tmp_path / "restaurado.db"
    assert servico.restore_backup(caminho.split("/")[-1].split("\\")[-1], str(restaurado)) is True

    with sqlite3.connect(restaurado) as conn:
        paciente = conn.execute("SELECT id FROM pacientes WHERE id='PAC-BKP'").fetchone()
        amostras = conn.execute(
            "SELECT COUNT(*) FROM grade WHERE paciente_id='PAC-BKP'"
        ).fetchone()
        posturas = conn.execute(
            "SELECT ts, postura FROM grade WHERE paciente_id='PAC-BKP' ORDER BY ts LIMIT 1"
        ).fetchone()

    assert paciente is not None
    assert amostras[0] == 24, "o historico do paciente nao sobreviveu ao ciclo"
    assert posturas == ("2026-01-05T00:00:00", "supino"), "os dados voltaram alterados"


def test_backup_que_nao_verifica_nao_fica_no_diretorio(tmp_path):
    """Se o arquivo gerado nao presta, ele nao pode ser deixado la.

    Um backup ruim no diretorio e pior que nenhum: aparece na listagem, reseta
    o contador de "ultimo backup" e passa uma impressao de cobertura que nao
    existe.
    """
    vazio = tmp_path / "sem_esquema.db"
    with sqlite3.connect(vazio) as conn:
        conn.execute("CREATE TABLE irrelevante (x INT)")

    dir_backup = tmp_path / "backups"
    servico = BackupService(str(vazio), backup_dir=str(dir_backup))

    with pytest.raises(BackupInvalido):
        servico.create_backup()

    assert list(dir_backup.glob("backup_*.db")) == [], (
        "o arquivo invalido continuou no diretorio de backups"
    )


def test_arquivo_corrompido_e_recusado(servico, tmp_path):
    """Bytes aleatorios com nome de backup nao passam por backup."""
    falso = tmp_path / "backups" / "backup_20260101_000000.db"
    falso.write_bytes(b"isto nao e um banco de dados" * 100)

    verificacao = verificar_arquivo(falso)
    assert not verificacao
    assert verificacao.motivo

    assert servico.restore_backup(falso.name, str(tmp_path / "alvo.db")) is False, (
        "restaurar a partir de um arquivo corrompido sobrescreveria a base boa"
    )


def test_arquivo_truncado_e_recusado(servico, tmp_path):
    """Um SQLite valido mas sem as tabelas do sistema nao restaura nada."""
    truncado = tmp_path / "backups" / "backup_20260101_000001.db"
    with sqlite3.connect(truncado) as conn:
        conn.execute("CREATE TABLE pacientes (id TEXT)")  # falta grade/eventos/alertas

    verificacao = verificar_arquivo(truncado)
    assert not verificacao
    assert "essenciais" in verificacao.motivo


def test_cleanup_nunca_apaga_os_ultimos_backups(servico):
    """`keep_days=0` apagava TODOS, inclusive o unico bom.

    Idade sozinha e criterio perigoso: numa instalacao parada por um mes, todo
    backup e "velho". O piso por contagem garante que sempre sobra de onde
    restaurar.
    """
    for _ in range(MANTER_MINIMO + 2):
        servico.create_backup()

    total_antes = len(servico.list_backups())
    servico.cleanup_old_backups(keep_days=0)
    restantes = servico.list_backups()

    assert total_antes >= MANTER_MINIMO + 2
    assert len(restantes) == MANTER_MINIMO, (
        f"sobraram {len(restantes)} backups; o piso e {MANTER_MINIMO}"
    )


def test_backups_no_mesmo_segundo_nao_se_sobrescrevem(servico):
    """O nome tinha resolucao de segundo e o arquivo era reaberto em modo escrita.

    Dois backups no mesmo segundo caiam no mesmo nome: o segundo passava por
    cima do primeiro e um ponto de restauracao sumia, sem nada no log dizendo
    isso. Acontece de verdade ao disparar /admin/backup/create duas vezes.
    """
    caminhos = {servico.create_backup() for _ in range(5)}

    assert len(caminhos) == 5, f"5 backups geraram apenas {len(caminhos)} arquivos distintos"
    assert len(servico.list_backups()) == 5


def test_estado_denuncia_ausencia_de_backup(servico):
    """Sem nenhum backup, o estado tem de dizer que NAO esta saudavel."""
    estado = servico.estado()

    assert estado["saudavel"] is False
    assert estado["ultimo_valido"] is None
    assert estado["validos"] == 0


def test_estado_saudavel_apos_backup(servico):
    servico.create_backup()

    estado = servico.estado(intervalo_esperado_horas=24)

    assert estado["saudavel"] is True
    assert estado["validos"] == 1
    assert estado["invalidos"] == []
    assert estado["idade_horas"] < 1


def test_estado_aponta_o_invalido_pelo_nome(servico, tmp_path):
    """Quem for restaurar precisa saber QUAL arquivo nao presta."""
    servico.create_backup()
    ruim = tmp_path / "backups" / "backup_20260101_000002.db"
    ruim.write_bytes(b"lixo")

    estado = servico.estado()

    assert ruim.name in estado["invalidos"]
    assert estado["validos"] == 1


def test_falha_do_agendador_nao_e_engolida(tmp_path):
    """O loop precisa PODER ver o erro para registra-lo.

    Antes, `scheduled_backup_task` capturava tudo e retornava normalmente: o
    agendador logava `backup_scheduler_cycle_done` mesmo quando o backup tinha
    falhado.
    """
    from servicos.backup import scheduled_backup_task

    vazio = tmp_path / "sem_esquema.db"
    with sqlite3.connect(vazio) as conn:
        conn.execute("CREATE TABLE irrelevante (x INT)")

    with pytest.raises(BackupInvalido):
        scheduled_backup_task(str(vazio), str(tmp_path / "bkp"))
