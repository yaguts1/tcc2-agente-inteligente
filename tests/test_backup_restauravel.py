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
from datetime import datetime, timedelta, timezone

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


def test_estado_denuncia_backup_de_outro_banco(banco, servico, tmp_path):
    """Integro e recente nao basta — pode ser backup de OUTRO banco.

    Aconteceu de verdade: a suite de testes gravava copias do banco de teste no
    diretorio real, e a mais nova, valida e recentissima, virava o "ultimo
    backup bom": 240 KB no lugar de 17 MB. O sistema informaria cobertura total
    apontando para um banco praticamente vazio.
    """
    # Um backup legitimo, e depois um de um banco quase vazio, mais recente.
    servico.create_backup()

    outro = tmp_path / "outro.db"
    criar_esquema(str(outro))
    intruso = BackupService(str(outro), backup_dir=str(servico.backup_dir))
    intruso.create_backup()

    estado = servico.estado()

    assert estado["validos"] == 2, "os dois arquivos sao SQLite integros"
    assert estado["proporcional"] is False
    assert estado["saudavel"] is False, (
        "reportou cobertura saudavel apontando para um backup de outro banco"
    )


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


@pytest.mark.asyncio
async def test_endpoints_de_backup_nao_devolvem_caminho_do_disco(app_isolado, cabecalho_auth):
    """`path` carrega o caminho real no servidor e nao serve para nada no cliente.

    Todas as operacoes sao por `filename`, dentro do diretorio configurado.
    Devolver o caminho entrega a estrutura de diretorios ao navegador — o mesmo
    vazamento que `erro_interno` existe para evitar no resto da API. E rota de
    admin, mas admin tambem nao precisa disso para operar.
    """
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app_isolado.app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers=cabecalho_auth(username="admin1", role="admin"),
    ) as client:
        criado = await client.post("/api/admin/backup/create")
        assert criado.status_code == 200, criado.text
        assert "path" not in criado.json()
        assert criado.json()["filename"].endswith(".db")
        assert "/" not in criado.json()["filename"] and "\\" not in criado.json()["filename"]

        listagem = await client.get("/api/admin/backup/list")
        assert all("path" not in b for b in listagem.json()["backups"])

        verificacao = await client.post("/api/admin/backup/verify")
        assert all("path" not in b for b in verificacao.json()["backups"])
        # O que o cliente precisa continua vindo.
        assert all("filename" in b and "ok" in b for b in verificacao.json()["backups"])


class TestIntervaloDeBackup:
    """O intervalo era lido em DOIS lugares, com tratamentos diferentes.

    O agendador caia no default diante de um valor ilegivel; o endpoint de
    status estourava 500. Pior que a robustez: divergindo, o veredito "estou
    coberto?" passaria a julgar a idade do ultimo backup contra um intervalo
    que nao e o que o agendador de fato usa.
    """

    def test_valor_valido(self, monkeypatch):
        from servicos.backup import intervalo_de_backup_horas

        monkeypatch.setenv("BACKUP_INTERVAL_HOURS", "6")
        assert intervalo_de_backup_horas() == 6

    def test_valor_ilegivel_cai_no_padrao_em_vez_de_estourar(self, monkeypatch):
        from servicos.backup import intervalo_de_backup_horas

        monkeypatch.setenv("BACKUP_INTERVAL_HOURS", "seis")
        assert intervalo_de_backup_horas() == 24

    def test_zero_vira_uma_hora(self, monkeypatch):
        # Intervalo 0 faria o agendador rodar em laco fechado.
        from servicos.backup import intervalo_de_backup_horas

        monkeypatch.setenv("BACKUP_INTERVAL_HOURS", "0")
        assert intervalo_de_backup_horas() == 1

    @pytest.mark.asyncio
    async def test_status_nao_estoura_com_configuracao_ilegivel(
        self, app_isolado, cabecalho_auth, monkeypatch
    ):
        from httpx import ASGITransport, AsyncClient

        monkeypatch.setenv("BACKUP_INTERVAL_HOURS", "vinte e quatro")
        transport = ASGITransport(app=app_isolado.app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers=cabecalho_auth(username="admin1", role="admin"),
        ) as client:
            resp = await client.get("/api/admin/backup/status")

        assert resp.status_code == 200, resp.text
        assert "saudavel" in resp.json()


class TestReplicacaoExterna:
    """A copia FORA da VM precisa ser observavel, nao so existir.

    Backup no mesmo disco do banco cobre erro de operacao e corrupcao; nao
    cobre disco morto nem VM apagada. O transporte fica num script do host (para
    nao por chave SSH no container nem prender o sistema a um transporte so),
    mas script sozinho recria a falha calada: uma replicacao que parou de rodar
    e indistinguivel de uma que funciona. Dai o recibo.
    """

    def _recibo(self, backup_dir, **campos):
        import json as _json
        from pathlib import Path

        from servicos.backup import RECIBO_REPLICACAO

        base = {
            "terminado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "ok": True,
            "arquivos": 3,
            "duracao_s": 4,
            "destino": "backup@10.0.0.9",
            "erro": "",
        }
        base.update(campos)
        (Path(backup_dir) / RECIBO_REPLICACAO).write_text(
            _json.dumps(base), encoding="utf-8"
        )

    def test_sem_configuracao_nao_alarma(self, tmp_path, monkeypatch):
        """Alarmar por algo que a instituicao nao configurou treina a equipe a
        ignorar o vermelho — e o vermelho e a unica defesa contra a falha
        calada de verdade."""
        from servicos.backup import estado_replicacao

        monkeypatch.delenv("BACKUP_REPLICACAO_INTERVALO_HORAS", raising=False)

        estado = estado_replicacao(tmp_path)

        assert estado["configurada"] is False
        assert estado["erro"] is None

    def test_configurada_sem_recibo_e_alarme(self, tmp_path, monkeypatch):
        """Configurou e nunca rodou: e exatamente o caso que o recibo existe
        para expor."""
        from servicos.backup import estado_replicacao

        monkeypatch.setenv("BACKUP_REPLICACAO_INTERVALO_HORAS", "24")

        estado = estado_replicacao(tmp_path)

        assert estado["configurada"] is True
        assert estado["saudavel"] is False
        assert "nenhuma replicacao" in estado["erro"]

    def test_replicacao_recente_e_bem_sucedida(self, tmp_path, monkeypatch):
        from servicos.backup import estado_replicacao

        monkeypatch.setenv("BACKUP_REPLICACAO_INTERVALO_HORAS", "24")
        self._recibo(tmp_path)

        estado = estado_replicacao(tmp_path)

        assert estado["saudavel"] is True
        assert estado["destino"] == "backup@10.0.0.9"
        assert estado["arquivos"] == 3

    def test_replicacao_que_falhou_nao_conta_como_cobertura(self, tmp_path, monkeypatch):
        """Recibo recente com ok=false e o caso perigoso: ha registro de
        execucao, mas nao ha copia."""
        from servicos.backup import estado_replicacao

        monkeypatch.setenv("BACKUP_REPLICACAO_INTERVALO_HORAS", "24")
        self._recibo(tmp_path, ok=False, erro="rsync falhou: connection refused")

        estado = estado_replicacao(tmp_path)

        assert estado["saudavel"] is False
        assert "connection refused" in estado["erro"]

    def test_replicacao_velha_demais_deixa_de_valer(self, tmp_path, monkeypatch):
        """O cron pode ter morrido; um recibo de duas semanas nao prova nada
        sobre hoje."""
        from servicos.backup import estado_replicacao

        monkeypatch.setenv("BACKUP_REPLICACAO_INTERVALO_HORAS", "24")
        antigo = datetime.now(timezone.utc) - timedelta(days=14)
        self._recibo(tmp_path, terminado_em=antigo.strftime("%Y-%m-%dT%H:%M:%SZ"))

        estado = estado_replicacao(tmp_path)

        assert estado["saudavel"] is False
        assert estado["idade_horas"] > 300

    def test_tolera_atraso_de_meio_intervalo(self, tmp_path, monkeypatch):
        """Um ciclo que atrasa nao e incidente; um ciclo que nao aconteceu e.
        Mesma tolerancia ja usada para o backup local."""
        from servicos.backup import estado_replicacao

        monkeypatch.setenv("BACKUP_REPLICACAO_INTERVALO_HORAS", "24")
        atrasado = datetime.now(timezone.utc) - timedelta(hours=30)
        self._recibo(tmp_path, terminado_em=atrasado.strftime("%Y-%m-%dT%H:%M:%SZ"))

        assert estado_replicacao(tmp_path)["saudavel"] is True

    def test_recibo_corrompido_nao_derruba_o_status(self, tmp_path, monkeypatch):
        """O endpoint de status e a ferramenta de diagnostico: nao pode cair
        junto com o que ele diagnostica."""
        from pathlib import Path

        from servicos.backup import RECIBO_REPLICACAO, estado_replicacao

        monkeypatch.setenv("BACKUP_REPLICACAO_INTERVALO_HORAS", "24")
        (Path(tmp_path) / RECIBO_REPLICACAO).write_text("{isto nao e json", encoding="utf-8")

        estado = estado_replicacao(tmp_path)

        assert estado["saudavel"] is False
        assert "ilegivel" in estado["erro"]

    def test_recibo_nao_aparece_como_backup(self, tmp_path):
        """O glob de backups e `backup_*.db`; o recibo comeca com ponto. Se
        entrasse na listagem, viraria um "backup" que nao restaura."""
        from servicos.backup import BackupService

        self._recibo(tmp_path)
        servico = BackupService(str(tmp_path / "x.db"), backup_dir=str(tmp_path))

        assert servico.list_backups() == []

    def test_status_expoe_a_replicacao(self, tmp_path, monkeypatch):
        """A tela le `estado()`; a replicacao precisa chegar por ali."""
        from servicos.backup import BackupService

        monkeypatch.setenv("BACKUP_REPLICACAO_INTERVALO_HORAS", "24")
        self._recibo(tmp_path)
        servico = BackupService(str(tmp_path / "x.db"), backup_dir=str(tmp_path))

        estado = servico.estado()

        assert estado["replicacao"]["saudavel"] is True
        # E o veredito local continua separado do externo: sao protecoes contra
        # falhas diferentes, e um booleano so esconderia qual delas caiu.
        assert "saudavel" in estado and estado["saudavel"] is not estado["replicacao"]

    def test_le_o_formato_que_o_script_realmente_gera(self, tmp_path, monkeypatch):
        """Contrato entre `scripts/replicar_backups.sh` e a aplicacao.

        Os outros testes desta classe escrevem o recibo a mao, o que valida a
        leitura mas nao o acordo entre as duas metades. Estes sao os bytes que
        o script emite de fato (com a quebra de linha do heredoc no meio, que e
        JSON valido mas ja quebraria um parser ingenuo). Se alguem mudar o
        formato num lado, este teste cai.
        """
        from pathlib import Path

        from servicos.backup import RECIBO_REPLICACAO, estado_replicacao

        monkeypatch.setenv("BACKUP_REPLICACAO_INTERVALO_HORAS", "24")
        agora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        bruto = (
            '{"terminado_em":"' + agora + '","ok":true,"arquivos":2,"duracao_s":0,\n'
            ' "destino":"vm-secundaria","erro":""}'
        )
        (Path(tmp_path) / RECIBO_REPLICACAO).write_text(bruto, encoding="utf-8")

        estado = estado_replicacao(tmp_path)

        assert estado["saudavel"] is True
        assert estado["destino"] == "vm-secundaria"
        assert estado["arquivos"] == 2

    def test_le_o_recibo_de_falha_que_o_script_gera(self, tmp_path, monkeypatch):
        """O caminho de falha do script tambem grava recibo — e e o que
        importa: uma replicacao que morre calada e o defeito a evitar."""
        from pathlib import Path

        from servicos.backup import RECIBO_REPLICACAO, estado_replicacao

        monkeypatch.setenv("BACKUP_REPLICACAO_INTERVALO_HORAS", "24")
        agora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        bruto = (
            '{"terminado_em":"' + agora + '","ok":false,"arquivos":0,"duracao_s":1,\n'
            ' "destino":"vm-secundaria","erro":"rsync nao encontrado no host"}'
        )
        (Path(tmp_path) / RECIBO_REPLICACAO).write_text(bruto, encoding="utf-8")

        estado = estado_replicacao(tmp_path)

        assert estado["saudavel"] is False
        assert estado["erro"] == "rsync nao encontrado no host"
