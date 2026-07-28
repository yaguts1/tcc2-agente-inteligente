"""Repository for Patient related database operations."""
from __future__ import annotations

import re
import sqlite3
import pandas as pd
import structlog
from typing import List, Sequence, Optional

from interface.db_core import connect, utc_now_iso
from interface.repositories.unidades import (
    UNIDADE_PADRAO,
    assert_unidade_valida,
    filtro_sql as filtro_de_unidades,
)

logger = structlog.get_logger(__name__)

PACIENTE_ID_PREFIX = "PAC"
PERFIS_VALIDOS = {"baixo", "medio", "alto"}
DEFAULT_ROTINA_DURACAO_MIN = 30


class JaTeveAlta(ValueError):
    """Operacao que exige internacao aberta, num paciente que ja teve alta."""


def _para_ms(iso: str) -> int:
    """Timestamp ISO (UTC naive, a convencao do banco) em milissegundos."""
    return int(pd.to_datetime(iso).timestamp() * 1000)

class PatientRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _ensure_paciente(self, conn: sqlite3.Connection, paciente_id: str) -> None:
        conn.execute("INSERT OR IGNORE INTO pacientes(id) VALUES (?)", (paciente_id,))

    def _generate_paciente_id(self, conn: sqlite3.Connection, prefix: str = PACIENTE_ID_PREFIX) -> str:
        existing_ids = {str(row[0]) for row in conn.execute("SELECT id FROM pacientes")}
        pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
        maior = 0
        for pid in existing_ids:
            match = pattern.match(pid)
            if match:
                maior = max(maior, int(match.group(1)))
        while True:
            maior += 1
            candidate = f"{prefix}-{maior:04d}"
            if candidate not in existing_ids:
                return candidate

    def _normalize_cama_id(self, valor: str | None) -> str | None:
        if valor is None:
            return None
        texto = str(valor).strip()
        return texto or None

    def _assert_cama_disponivel(
        self,
        conn: sqlite3.Connection,
        cama_id: str | None,
        *,
        unidade_id: int | None = None,
        ignorar_paciente: str | None = None,
    ) -> None:
        """Um paciente por leito DENTRO DA UNIDADE.

        A checagem era global, e por isso duas alas com um "Leito 12" cada nao
        podiam coexistir: a segunda admissao era recusada citando um paciente de
        outro predio. A mensagem de erro chegava a vazar o ID de um paciente que
        o operador nao tinha por que conhecer.
        """
        if cama_id is None:
            return
        unidade = UNIDADE_PADRAO if unidade_id is None else int(unidade_id)
        row = conn.execute(
            "SELECT paciente_id FROM paciente_fichas WHERE cama_id = ? AND unidade_id = ?",
            (cama_id, unidade),
        ).fetchone()
        if row is not None:
            existente = str(row["paciente_id"])
            if ignorar_paciente is None or existente != ignorar_paciente:
                raise ValueError(f"Cama '{cama_id}' ja esta atribuida ao paciente {existente}.")

    # ------------------------------------------------------------------
    # Leito: uma implementacao so
    # ------------------------------------------------------------------
    def _vincular_device_da_cama(
        self, conn: sqlite3.Connection, cama_id: str, paciente_id: str, agora_iso: str, agora_ms: int
    ) -> None:
        """Passa o device instalado no leito para o paciente que o ocupa agora."""
        cur = conn.execute(
            "SELECT device_id FROM device_assignments"
            " WHERE cama_id = ? AND end_ms IS NULL ORDER BY start_ms DESC LIMIT 1",
            (cama_id,),
        )
        row = cur.fetchone()
        if row is None:
            return
        device_id = row["device_id"]
        conn.execute(
            "UPDATE device_assignments SET end_ts = ?, end_ms = ?"
            " WHERE device_id = ? AND end_ms IS NULL",
            (agora_iso, agora_ms, device_id),
        )
        conn.execute(
            "INSERT INTO device_assignments (device_id, cama_id, paciente_id, start_ts, start_ms)"
            " VALUES (?, ?, ?, ?, ?)",
            (device_id, cama_id, paciente_id, agora_iso, agora_ms),
        )

    def _mover_para_cama(
        self,
        conn: sqlite3.Connection,
        paciente_id: str,
        cama_id: str | None,
        agora_iso: str,
        agora_ms: int,
        unidade_id: int | None = None,
    ) -> None:
        """Fecha o periodo do leito anterior e abre o do novo (ou nenhum).

        Uma implementacao so para `create`, `update`, `transferir`, `dar_alta` e
        a troca de leitos. Antes o mesmo bloco estava copiado em `create` e
        `update` com diferencas sutis, que e como as duas divergem sem ninguem
        perceber — e o que este historico de leito alimenta e a resolucao de "de
        quem e esta leitura de sensor".

        Sem try/except: e chamado sempre dentro da transacao de quem move o
        paciente, e um historico de leito que falha em silencio produz dado
        clinico atribuido ao paciente errado. Se falhar, a operacao inteira tem
        que voltar atras.
        """
        cur = conn.execute(
            "SELECT id FROM paciente_cama_history"
            " WHERE paciente_id = ? AND end_ms IS NULL ORDER BY start_ms DESC LIMIT 1",
            (paciente_id,),
        )
        aberto = cur.fetchone()
        if aberto is not None:
            conn.execute(
                "UPDATE paciente_cama_history SET end_ts = ?, end_ms = ? WHERE id = ?",
                (agora_iso, agora_ms, int(aberto["id"])),
            )

        if cama_id is None:
            return

        # A unidade do periodo, e nao so o leito: e o que permite calcular
        # paciente-hora por ala depois que o paciente muda de ala. Sem ela, a
        # unica unidade conhecida seria a ATUAL da ficha, e um paciente que
        # passou tres dias na ala A e um na B apareceria como quatro na B.
        conn.execute(
            "INSERT INTO paciente_cama_history"
            " (paciente_id, cama_id, start_ts, start_ms, unidade_id)"
            " VALUES (?, ?, ?, ?, ?)",
            (paciente_id, cama_id, agora_iso, agora_ms, unidade_id),
        )
        self._vincular_device_da_cama(conn, cama_id, paciente_id, agora_iso, agora_ms)

    def _normalize_hhmm(self, valor: str) -> str:
        texto = str(valor or "").strip()
        if not texto:
            raise ValueError("Horario de rotina invalido.")
        partes = texto.split(":")
        if len(partes) != 2:
            raise ValueError(f"Horario '{texto}' deve estar no formato HH:MM.")
        try:
            hora = int(partes[0])
            minuto = int(partes[1])
        except ValueError as exc:
            raise ValueError(f"Horario '{texto}' deve conter numeros validos.") from exc
        if not (0 <= hora <= 23 and 0 <= minuto <= 59):
            raise ValueError(f"Horario '{texto}' fora do intervalo 00:00-23:59.")
        return f"{hora:02d}:{minuto:02d}"

    def _prepare_rotinas(self, rotinas: Sequence[dict] | None) -> List[dict]:
        if not rotinas:
            return []
        preparados: List[dict] = []
        for ordem, raw in enumerate(rotinas):
            if raw is None:
                continue
            label = str(raw.get("label", "")).strip()
            if not label:
                continue
            inicio_val = self._normalize_hhmm(raw.get("inicio", ""))
            try:
                duracao = int(raw.get("duracao_min", DEFAULT_ROTINA_DURACAO_MIN))
            except (TypeError, ValueError):
                duracao = DEFAULT_ROTINA_DURACAO_MIN
            if duracao <= 0:
                duracao = DEFAULT_ROTINA_DURACAO_MIN
            descricao_raw = raw.get("descricao")
            descricao_val = None if descricao_raw is None else str(descricao_raw).strip() or None
            ativo_flag = raw.get("ativo", True)
            ativo_val = 0 if ativo_flag in (False, 0, "0") else 1
            sort_order = raw.get("sort_order")
            try:
                sort_idx = int(sort_order)
            except (TypeError, ValueError):
                sort_idx = ordem
            preparados.append(
                {
                    "label": label,
                    "inicio": inicio_val,
                    "duracao_min": duracao,
                    "descricao": descricao_val,
                    "ativo": ativo_val,
                    "sort_order": sort_idx,
                }
            )
        return preparados

    def _replace_rotinas(self, conn: sqlite3.Connection, paciente_id: str, rotinas: Sequence[dict] | None) -> None:
        normalizadas = self._prepare_rotinas(rotinas)
        conn.execute("DELETE FROM paciente_rotinas WHERE paciente_id = ?", (paciente_id,))
        if not normalizadas:
            return
        conn.executemany(
            """
            INSERT INTO paciente_rotinas (paciente_id, label, inicio, duracao_min, descricao, ativo, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    paciente_id,
                    item["label"],
                    item["inicio"],
                    item["duracao_min"],
                    item["descricao"],
                    item["ativo"],
                    item["sort_order"],
                )
                for item in normalizadas
            ],
        )

    def _fetch_rotinas(self, conn: sqlite3.Connection, paciente_id: str) -> List[dict]:
        cursor = conn.execute(
            """
            SELECT id, label, inicio, duracao_min, descricao, ativo, sort_order
            FROM paciente_rotinas
            WHERE paciente_id = ?
            ORDER BY sort_order, inicio
            """,
            (paciente_id,),
        )
        rows = cursor.fetchall()
        return [
            {
                "id": row["id"],
                "label": row["label"],
                "inicio": row["inicio"],
                "duracao_min": row["duracao_min"],
                "descricao": row["descricao"],
                "ativo": bool(row["ativo"]),
                "sort_order": row["sort_order"],
            }
            for row in rows
        ]

    def list_all(
        self,
        include_routines: bool = False,
        unidades: set[int] | None = None,
        incluir_alta: bool = False,
    ) -> List[dict]:
        """Fichas visiveis para quem pergunta.

        `unidades=None` significa SEM RESTRICAO (admin), e `set()` significa
        nenhuma unidade — a distincao esta em `repositories/unidades.filtro_sql`,
        e trata-la como "vazio = tudo" devolveria o hospital inteiro justamente
        para quem nao pode ver nada.

        `incluir_alta=False` por padrao: depois que alta virou estado
        (migrations/0009), a lista da ala encheria de gente que ja foi embora.
        Quem quer o historico pede explicitamente.
        """
        condicao, params = filtro_de_unidades(unidades, coluna="f.unidade_id")
        clausula_alta = (
            ""
            if incluir_alta
            else " AND EXISTS (SELECT 1 FROM internacoes i"
                 " WHERE i.paciente_id = f.paciente_id AND i.alta_ms IS NULL)"
        )
        with connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT f.paciente_id, f.nome, f.perfil, f.cama_id, f.observacoes,"
                " f.created_at, f.updated_at, f.unidade_id"
                " FROM paciente_fichas f"
                f" WHERE 1 = 1{condicao}{clausula_alta}"
                " ORDER BY f.nome COLLATE NOCASE, f.paciente_id",
                params,
            )
            fichas = []
            for row in cursor.fetchall():
                ficha = dict(row)
                if include_routines:
                    ficha["rotinas"] = self._fetch_rotinas(conn, ficha["paciente_id"])
                fichas.append(ficha)
            return fichas

    def get_by_id(self, paciente_id: str, include_routines: bool = False) -> Optional[dict]:
        with connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT paciente_id, nome, perfil, cama_id, observacoes, created_at, updated_at, unidade_id
                FROM paciente_fichas
                WHERE paciente_id = ?
                """,
                (paciente_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            ficha = dict(row)
            if include_routines:
                ficha["rotinas"] = self._fetch_rotinas(conn, paciente_id)
            return ficha

    def get_by_cama(self, cama_id: str, include_routines: bool = False) -> Optional[dict]:
        cama_norm = self._normalize_cama_id(cama_id)
        if cama_norm is None:
            return None
        with connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT paciente_id, nome, perfil, cama_id, observacoes, created_at, updated_at
                FROM paciente_fichas
                WHERE cama_id = ?
                """,
                (cama_norm,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            ficha = dict(row)
            if include_routines:
                ficha["rotinas"] = self._fetch_rotinas(conn, ficha["paciente_id"])
            return ficha

    def create(
        self,
        nome: str,
        perfil: str,
        cama_id: str | None = None,
        observacoes: str | None = None,
        rotinas: Sequence[dict] | None = None,
        registrado_por: str | None = None,
        unidade_id: int | None = None,
    ) -> dict:
        nome_limpo = str(nome or "").strip()
        if not nome_limpo:
            raise ValueError("Nome do paciente nao pode ser vazio.")
        perfil_norm = str(perfil or "").strip().lower()
        if perfil_norm not in PERFIS_VALIDOS:
            raise ValueError(f"Perfil invalido: {perfil}.")
        cama_norm = self._normalize_cama_id(cama_id)
        obs_val = None if observacoes is None else str(observacoes).strip() or None
        
        unidade = UNIDADE_PADRAO if unidade_id is None else int(unidade_id)

        with connect(self.db_path) as conn:
            assert_unidade_valida(conn, unidade)
            self._assert_cama_disponivel(conn, cama_norm, unidade_id=unidade)
            paciente_id = self._generate_paciente_id(conn)
            agora_iso = utc_now_iso()
            conn.execute("INSERT INTO pacientes (id) VALUES (?)", (paciente_id,))
            conn.execute(
                """
                INSERT INTO paciente_fichas (paciente_id, nome, perfil, cama_id, observacoes, created_at, updated_at, unidade_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (paciente_id, nome_limpo, perfil_norm, cama_norm, obs_val, agora_iso, agora_iso, unidade),
            )
            self._replace_rotinas(conn, paciente_id, rotinas)

            agora_ms = _para_ms(agora_iso)
            self._mover_para_cama(
                conn, paciente_id, cama_norm, agora_iso, agora_ms, unidade_id=unidade
            )
            # Cadastrar um paciente E admiti-lo: nao existe, neste sistema,
            # paciente que exista sem estar internado. O episodio comeca aqui
            # para que alta, tempo de permanencia e o denominador de
            # paciente-hora tenham de onde partir.
            conn.execute(
                "INSERT INTO internacoes (paciente_id, admissao_ts, admissao_ms, admitido_por, unidade_id)"
                " VALUES (?, ?, ?, ?, ?)",
                (paciente_id, agora_iso, agora_ms, registrado_por, unidade),
            )
            conn.commit()

        return self.get_by_id(paciente_id, include_routines=True) # type: ignore

    def update(
        self,
        paciente_id: str,
        nome: str,
        perfil: str,
        cama_id: str | None = None,
        observacoes: str | None = None,
        rotinas: Sequence[dict] | None = None,
    ) -> dict:
        nome_limpo = str(nome or "").strip()
        if not nome_limpo:
            raise ValueError("Nome do paciente nao pode ser vazio.")
        perfil_norm = str(perfil or "").strip().lower()
        if perfil_norm not in PERFIS_VALIDOS:
            raise ValueError(f"Perfil invalido: {perfil}.")
        cama_norm = self._normalize_cama_id(cama_id)
        obs_val = None if observacoes is None else str(observacoes).strip() or None
        
        with connect(self.db_path) as conn:
            cur = conn.execute(
                "SELECT paciente_id, cama_id, unidade_id FROM paciente_fichas WHERE paciente_id = ?",
                (paciente_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise LookupError("Paciente nao encontrado.")
            existing_cama = row["cama_id"]
            self._assert_cama_disponivel(
                conn, cama_norm, unidade_id=row["unidade_id"], ignorar_paciente=paciente_id
            )
            agora_iso = utc_now_iso()
            conn.execute(
                """
                UPDATE paciente_fichas
                SET nome = ?, perfil = ?, cama_id = ?, observacoes = ?, updated_at = ?
                WHERE paciente_id = ?
                """,
                (nome_limpo, perfil_norm, cama_norm, obs_val, agora_iso, paciente_id),
            )
            if rotinas is not None:
                self._replace_rotinas(conn, paciente_id, rotinas)
            
            # A mudanca de leito por aqui existe para o formulario continuar
            # funcionando, mas nao e mais o caminho recomendado: `transferir()`
            # e que registra a transferencia como alivio de pressao e reinicia o
            # motor. Editar o campo num formulario nao tem como saber que houve
            # um deslocamento fisico do paciente.
            mudou_de_leito = (existing_cama or None) != (cama_norm or None)
            if mudou_de_leito:
                self._mover_para_cama(
                    conn,
                    paciente_id,
                    cama_norm,
                    agora_iso,
                    _para_ms(agora_iso),
                    unidade_id=row["unidade_id"],
                )
            conn.commit()

        return self.get_by_id(paciente_id, include_routines=True) # type: ignore

    # ------------------------------------------------------------------
    # Ciclo de vida do episodio
    # ------------------------------------------------------------------
    def internacao_aberta(self, paciente_id: str) -> dict | None:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM internacoes WHERE paciente_id = ? AND alta_ms IS NULL",
                (paciente_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def dar_alta(
        self, paciente_id: str, motivo: str | None = None, usuario: str | None = None
    ) -> dict:
        """Encerra o episodio SEM destruir o historico clinico.

        A unica forma de tirar um paciente da tela era `delete()`, que apaga
        alertas, grade, eventos, timeline e historico de leito. Ou seja: a
        operacao mais rotineira de uma ala destruia exatamente a evidencia que
        acreditacao e LGPD Art. 37 exigem guardar, e o paciente sumia do
        denominador de qualquer analise retroativa.

        Alta libera o leito (a ficha fica sem `cama_id`, e o indice unico
        parcial `idx_pac_fichas_cama` volta a permitir o proximo ocupante),
        fecha o periodo em `paciente_cama_history` e desvincula o device — sem
        isso, a leitura do sensor do leito continuaria caindo no prontuario de
        quem ja foi embora.

        O estado do motor tambem vai embora: `EstadoDecisor` guarda
        `baseline_postura` e `cooldown_ate`, e um `PAC-NNNN` reaproveitado
        herdaria os de um estranho.
        """
        if not paciente_id:
            raise ValueError("paciente_id deve ser informado")

        with connect(self.db_path) as conn:
            ficha = conn.execute(
                "SELECT cama_id FROM paciente_fichas WHERE paciente_id = ?", (paciente_id,)
            ).fetchone()
            if ficha is None:
                raise LookupError("Paciente nao encontrado.")

            episodio = conn.execute(
                "SELECT id, admissao_ms FROM internacoes"
                " WHERE paciente_id = ? AND alta_ms IS NULL",
                (paciente_id,),
            ).fetchone()
            if episodio is None:
                raise JaTeveAlta(f"Paciente {paciente_id} nao tem internacao aberta.")

            agora_iso = utc_now_iso()
            agora_ms = _para_ms(agora_iso)

            conn.execute(
                "UPDATE internacoes SET alta_ts = ?, alta_ms = ?, motivo_alta = ?,"
                " dado_alta_por = ? WHERE id = ?",
                (agora_iso, agora_ms, motivo, usuario, int(episodio["id"])),
            )
            self._mover_para_cama(conn, paciente_id, None, agora_iso, agora_ms)
            conn.execute(
                "UPDATE paciente_fichas SET cama_id = NULL, updated_at = ?"
                " WHERE paciente_id = ?",
                (agora_iso, paciente_id),
            )
            conn.execute(
                "UPDATE device_assignments SET end_ts = ?, end_ms = ?"
                " WHERE paciente_id = ? AND end_ms IS NULL",
                (agora_iso, agora_ms, paciente_id),
            )
            self._limpar_estado_do_motor(conn, paciente_id)
            conn.commit()

        return {
            "paciente_id": paciente_id,
            "alta_ts": agora_iso,
            "permanencia_horas": round((agora_ms - int(episodio["admissao_ms"])) / 3_600_000, 2),
            "cama_liberada": ficha["cama_id"],
        }

    def transferir(
        self,
        paciente_id: str,
        nova_cama: str | None,
        usuario: str | None = None,
        unidade_id: int | None = None,
    ) -> dict:
        """Move o paciente de leito como UMA operacao, nao como efeito colateral.

        Antes isso era editar um campo de formulario. Duas coisas se perdiam:

        1. A transferencia E um reposicionamento. Ser erguido para a maca,
           levado pelo corredor e reacomodado e alivio de pressao real — o
           evento mais movimentado do dia do paciente. Para o motor, cujo estado
           e por paciente e nao por leito, o intervalo era lido como UMA corrida
           continua de imobilidade: o paciente recebia credito de zero movimento
           justamente ali. Por isso o estado do motor e zerado aqui.

        2. Se o relogio do ESP32 do leito novo estiver ATRAS do anterior, TODA
           amostra do leito novo era descartada como fora de ordem, em nivel
           debug, ate o relogio passar. Zerar o estado tambem zera esse
           `_ultima_ts`.
        """
        if not paciente_id:
            raise ValueError("paciente_id deve ser informado")
        cama_norm = self._normalize_cama_id(nova_cama)

        with connect(self.db_path) as conn:
            ficha = conn.execute(
                "SELECT cama_id, unidade_id FROM paciente_fichas WHERE paciente_id = ?",
                (paciente_id,),
            ).fetchone()
            if ficha is None:
                raise LookupError("Paciente nao encontrado.")
            if conn.execute(
                "SELECT 1 FROM internacoes WHERE paciente_id = ? AND alta_ms IS NULL",
                (paciente_id,),
            ).fetchone() is None:
                raise JaTeveAlta(
                    f"Paciente {paciente_id} nao esta internado; nao ha o que transferir."
                )

            cama_anterior = ficha["cama_id"]
            unidade_anterior = ficha["unidade_id"]
            # Destino na MESMA ala quando nao se informa outra: transferir de
            # leito dentro da propria unidade e o caso comum, e exigir a
            # unidade em toda chamada quebraria quem ja usa a operacao.
            unidade_destino = (
                unidade_anterior if unidade_id is None else int(unidade_id)
            )
            muda_de_ala = unidade_destino != unidade_anterior

            if (cama_anterior or None) == cama_norm and not muda_de_ala:
                raise ValueError("O paciente ja esta neste leito.")

            if muda_de_ala:
                assert_unidade_valida(conn, unidade_destino)

            # A ocupacao e conferida na ala de DESTINO.
            #
            # Era conferida na ala de ORIGEM, e por isso uma transferencia entre
            # alas produzia estado errado em silencio: o leito da ala de destino
            # podia estar ocupado sem que ninguem visse, o `cama_id` era gravado
            # e a `unidade_id` da ficha continuava sendo a de origem — dois
            # pacientes no mesmo leito real, e um deles listado na ala errada.
            self._assert_cama_disponivel(
                conn,
                cama_norm,
                unidade_id=unidade_destino,
                ignorar_paciente=paciente_id,
            )

            agora_iso = utc_now_iso()
            agora_ms = _para_ms(agora_iso)
            conn.execute(
                "UPDATE paciente_fichas SET cama_id = ?, unidade_id = ?, updated_at = ?"
                " WHERE paciente_id = ?",
                (cama_norm, unidade_destino, agora_iso, paciente_id),
            )
            self._mover_para_cama(
                conn, paciente_id, cama_norm, agora_iso, agora_ms, unidade_id=unidade_destino
            )
            # `internacoes.unidade_id` NAO muda: ele registra onde a internacao
            # COMECOU. Sobrescrever atribuiria a estadia inteira a ultima ala,
            # que e exatamente o erro que o historico por periodo evita.
            self._limpar_estado_do_motor(conn, paciente_id)
            conn.commit()

        return {
            "paciente_id": paciente_id,
            "cama_anterior": cama_anterior,
            "cama_atual": cama_norm,
            "unidade_anterior": unidade_anterior,
            "unidade_atual": unidade_destino,
            "mudou_de_unidade": muda_de_ala,
            "ts": agora_iso,
            "usuario": usuario,
        }

    def trocar_leitos(self, paciente_a: str, paciente_b: str, usuario: str | None = None) -> dict:
        """Dois pacientes trocam de leito, atomicamente.

        Era impossivel: `_assert_cama_disponivel` barra o primeiro passo, porque
        qualquer sequencia de dois `update` passa por um estado em que um leito
        tem dois ocupantes ou um paciente nao tem leito nenhum. Trocar dois
        pacientes de lugar e rotina numa ala, e a tela so devolvia erro.

        A saida e liberar os dois leitos ANTES de reatribuir, dentro da mesma
        transacao — o estado intermediario existe, mas ninguem fora dela o ve.
        """
        if not paciente_a or not paciente_b:
            raise ValueError("Os dois pacientes precisam ser informados")
        if paciente_a == paciente_b:
            raise ValueError("Nao da para trocar um paciente com ele mesmo")

        with connect(self.db_path) as conn:
            fichas = {}
            unidades_envolvidas: set = set()
            for pid in (paciente_a, paciente_b):
                row = conn.execute(
                    "SELECT cama_id, unidade_id FROM paciente_fichas WHERE paciente_id = ?", (pid,)
                ).fetchone()
                if row is None:
                    raise LookupError(f"Paciente {pid} nao encontrado.")
                if row["cama_id"] is None:
                    raise ValueError(f"Paciente {pid} nao esta em nenhum leito.")
                fichas[pid] = row["cama_id"]
                unidades_envolvidas.add(row["unidade_id"])

            # Trocar de leito ENTRE unidades nao e troca, sao duas
            # transferencias — os dois pacientes mudam de ala, e o destino de
            # cada um precisa ser validado contra a ocupacao da ala de destino.
            # Aceitar aqui produziria dois pacientes na unidade errada, com
            # `cama_id` que pode ja estar ocupado la.
            if len(unidades_envolvidas) > 1:
                raise ValueError(
                    "Troca de leitos so entre pacientes da mesma unidade;"
                    " para mover entre alas use transferencia."
                )
            unidade_comum = next(iter(unidades_envolvidas))

            agora_iso = utc_now_iso()
            agora_ms = _para_ms(agora_iso)

            # Libera os dois primeiro: o indice unico parcial de `cama_id` recusa
            # qualquer ordem que atribua antes de liberar.
            conn.execute(
                "UPDATE paciente_fichas SET cama_id = NULL, updated_at = ?"
                " WHERE paciente_id IN (?, ?)",
                (agora_iso, paciente_a, paciente_b),
            )
            for pid, destino in (
                (paciente_a, fichas[paciente_b]),
                (paciente_b, fichas[paciente_a]),
            ):
                conn.execute(
                    "UPDATE paciente_fichas SET cama_id = ?, updated_at = ? WHERE paciente_id = ?",
                    (destino, agora_iso, pid),
                )
                self._mover_para_cama(
                    conn, pid, destino, agora_iso, agora_ms, unidade_id=unidade_comum
                )
                # Os dois foram fisicamente movidos: os dois reiniciam.
                self._limpar_estado_do_motor(conn, pid)
            conn.commit()

        return {
            "ts": agora_iso,
            "usuario": usuario,
            "trocas": [
                {"paciente_id": paciente_a, "de": fichas[paciente_a], "para": fichas[paciente_b]},
                {"paciente_id": paciente_b, "de": fichas[paciente_b], "para": fichas[paciente_a]},
            ],
        }

    def _limpar_estado_do_motor(self, conn: sqlite3.Connection, paciente_id: str) -> None:
        """Apaga o estado persistido do decisor para este paciente.

        Só a linha no banco: o cache em memoria do PROCESSADOR e limpo pela
        camada de servico, que e quem tem acesso a ele. Chamar os dois e
        responsabilidade de quem move o paciente.
        """
        try:
            conn.execute("DELETE FROM estado_incremental WHERE paciente_id = ?", (paciente_id,))
        except sqlite3.OperationalError:
            # A tabela e criada sob demanda por servicos/processamento_incremental;
            # num banco onde o motor nunca rodou ela simplesmente nao existe.
            logger.debug("estado_incremental_ausente", paciente_id=paciente_id)

    # Tabelas apagadas junto com o paciente, na ordem em que sao apagadas.
    # A coluna que aponta para o paciente muda de nome em `pacientes` (`id`).
    _TABELAS_DO_PACIENTE = (
        ("paciente_rotinas", "paciente_id"),
        ("paciente_documentos", "paciente_id"),
        ("paciente_cama_history", "paciente_id"),
        ("device_assignments", "paciente_id"),
        ("timeline_events", "paciente_id"),
        # As tres abaixo faltavam, e a ausencia era visivel na tela: `alertas`
        # sobrevivia ao paciente e `listar_alertas_frontend` continuava
        # listando, so que sem ficha para resolver nome e leito — o alerta
        # voltava rotulado com o ID cru ("PAC-0007") e sem quarto, de um
        # paciente que nao existe mais e que ninguem consegue abrir. `grade` e
        # `eventos` alimentam o motor e a exportacao, entao ficavam
        # contabilizados em relatorio de alguem ja removido.
        ("alertas", "paciente_id"),
        ("grade", "paciente_id"),
        ("eventos", "paciente_id"),
        # Faltava, e o vazamento e do tipo que nao aparece em teste nenhum: o
        # `EstadoDecisor` persistido guarda `baseline_postura` e `cooldown_ate`,
        # e os IDs sao gerados por "maior existente + 1" — apagar PAC-0007 faz o
        # proximo paciente cadastrado se chamar PAC-0007 e HERDAR o estado do
        # motor de um estranho. O sintoma seria um paciente novo nascendo em
        # cooldown, sem alerta nenhum, sem nada explicando.
        ("estado_incremental", "paciente_id"),
        ("internacoes", "paciente_id"),
        ("agendas_paciente", "paciente_id"),
        ("paciente_fichas", "paciente_id"),
        ("pacientes", "id"),
    )

    def delete(self, paciente_id: str) -> dict[str, int] | None:
        """Remove o paciente e TODO o rastro clinico dele.

        Devolve quantas linhas sairam de cada tabela, ou `None` se o paciente
        nao existia. A contagem sobe ate a resposta HTTP de proposito: e uma
        operacao irreversivel sobre dado clinico, e quem a executa precisa ver
        o tamanho do que apagou — "removido com sucesso" nao distingue apagar
        uma ficha vazia de apagar seis meses de historico.
        """
        if not paciente_id:
            raise ValueError("paciente_id deve ser informado")
        removidos: dict[str, int] = {}
        with connect(self.db_path) as conn:
            cur = conn.execute("SELECT paciente_id FROM paciente_fichas WHERE paciente_id = ?", (paciente_id,))
            if cur.fetchone() is None:
                return None
            for tabela, coluna in self._TABELAS_DO_PACIENTE:
                try:
                    cursor = conn.execute(
                        f"DELETE FROM {tabela} WHERE {coluna} = ?", (paciente_id,)  # noqa: S608 - nomes internos, nao entrada
                    )
                except sqlite3.OperationalError:
                    # `estado_incremental` e `agendas_paciente` sao criadas sob
                    # demanda, fora das migrations: num banco onde o motor nunca
                    # rodou ou nenhuma agenda foi cadastrada, elas nao existem.
                    # Ausente e o mesmo que vazia — o que nao pode e a falta de
                    # uma tabela opcional impedir a limpeza das outras.
                    logger.debug("tabela_do_paciente_ausente", tabela=tabela)
                    continue
                removidos[tabela] = cursor.rowcount if cursor.rowcount > 0 else 0
            conn.commit()
        return removidos

    def proximo_identificador(self, prefixo: str = PACIENTE_ID_PREFIX) -> str:
        with connect(self.db_path) as conn:
            return self._generate_paciente_id(conn, prefix=prefixo)

    def ensure_minimal_ficha(
        self,
        paciente_id: str,
        nome: str | None = None,
        perfil: str | None = None,
        cama_id: str | None = None,
    ) -> None:
        """Garante um registro minimo em paciente_fichas para `paciente_id`.

        Se a ficha ja existir, nao faz nada (conservador, nunca sobrescreve).

        Abre internacao junto, pela mesma razao de `create`: neste sistema um
        paciente com ficha esta, por definicao, internado. Sem isso, o paciente
        que entra por aqui (import de alertas em `routers/admin.py`) nasceria
        sem episodio e ficaria impossivel de transferir ou de receber alta —
        ambas exigem internacao aberta e responderiam 409 para sempre, sem
        nenhuma pista de que a causa foi a porta de entrada.
        """
        if not paciente_id:
            raise ValueError("paciente_id deve ser informado.")

        perfil_val = None if perfil is None else str(perfil).strip().lower()
        if perfil_val not in PERFIS_VALIDOS:
            perfil_val = "medio"

        cama_norm = self._normalize_cama_id(cama_id)
        nome_val = None if nome is None else str(nome).strip() or None

        with connect(self.db_path) as conn:
            self._ensure_paciente(conn, paciente_id)
            cur = conn.execute("SELECT paciente_id FROM paciente_fichas WHERE paciente_id = ?", (paciente_id,))
            if cur.fetchone() is not None:
                return
            agora_iso = utc_now_iso()
            conn.execute(
                "INSERT INTO paciente_fichas (paciente_id, nome, perfil, cama_id, observacoes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (paciente_id, nome_val or paciente_id, perfil_val, cama_norm, None, agora_iso, agora_iso),
            )
            conn.execute(
                "INSERT OR IGNORE INTO internacoes (paciente_id, admissao_ts, admissao_ms)"
                " VALUES (?, ?, ?)",
                (paciente_id, agora_iso, _para_ms(agora_iso)),
            )
            if cama_norm is not None:
                try:
                    start_ms = int(pd.to_datetime(agora_iso).timestamp() * 1000)
                    conn.execute(
                        "INSERT INTO paciente_cama_history (paciente_id, cama_id, start_ts, start_ms) VALUES (?, ?, ?, ?)",
                        (paciente_id, cama_norm, agora_iso, start_ms),
                    )
                except Exception:
                    logger.warning(
                        "insercao_historico_cama_falhou",
                        paciente_id=paciente_id,
                        cama_id=cama_norm,
                        exc_info=True,
                    )
            conn.commit()

