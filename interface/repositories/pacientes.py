"""Repository for Patient related database operations."""
from __future__ import annotations

import re
import sqlite3
import pandas as pd
from typing import List, Sequence, Optional, Dict

from interface.db_core import connect, utc_now_iso
from interface.api_shared import DEFAULT_PERFIL

PACIENTE_ID_PREFIX = "PAC"
PERFIS_VALIDOS = {"baixo", "medio", "alto"}
DEFAULT_ROTINA_DURACAO_MIN = 30

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
        ignorar_paciente: str | None = None,
    ) -> None:
        if cama_id is None:
            return
        cursor = conn.execute(
            "SELECT paciente_id FROM paciente_fichas WHERE cama_id = ?",
            (cama_id,),
        )
        row = cursor.fetchone()
        if row is not None:
            existente = str(row["paciente_id"])
            if ignorar_paciente is None or existente != ignorar_paciente:
                raise ValueError(f"Cama '{cama_id}' ja esta atribuida ao paciente {existente}.")

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

    def list_all(self, include_routines: bool = False) -> List[dict]:
        with connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT paciente_id, nome, perfil, cama_id, observacoes, created_at, updated_at
                FROM paciente_fichas
                ORDER BY nome COLLATE NOCASE, paciente_id
                """
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
                SELECT paciente_id, nome, perfil, cama_id, observacoes, created_at, updated_at
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
            self._assert_cama_disponivel(conn, cama_norm)
            paciente_id = self._generate_paciente_id(conn)
            agora_iso = utc_now_iso()
            conn.execute("INSERT INTO pacientes (id) VALUES (?)", (paciente_id,))
            conn.execute(
                """
                INSERT INTO paciente_fichas (paciente_id, nome, perfil, cama_id, observacoes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (paciente_id, nome_limpo, perfil_norm, cama_norm, obs_val, agora_iso, agora_iso),
            )
            self._replace_rotinas(conn, paciente_id, rotinas)
            
            # History and Device Assignment Logic
            if cama_norm is not None:
                start_ms = int(pd.to_datetime(agora_iso).timestamp() * 1000)
                conn.execute(
                    "INSERT INTO paciente_cama_history (paciente_id, cama_id, start_ts, start_ms) VALUES (?, ?, ?, ?)",
                    (paciente_id, cama_norm, agora_iso, start_ms),
                )
                try:
                    cur = conn.execute(
                        "SELECT device_id FROM device_assignments WHERE cama_id = ? AND end_ms IS NULL ORDER BY start_ms DESC LIMIT 1",
                        (cama_norm,),
                    )
                    row = cur.fetchone()
                    if row is not None:
                        device_id = row["device_id"]
                        now_ms = int(pd.to_datetime(agora_iso).timestamp() * 1000)
                        conn.execute(
                            "UPDATE device_assignments SET end_ts = ?, end_ms = ? WHERE device_id = ? AND end_ms IS NULL",
                            (agora_iso, now_ms, device_id),
                        )
                        conn.execute(
                            "INSERT INTO device_assignments (device_id, cama_id, paciente_id, start_ts, start_ms) VALUES (?, ?, ?, ?, ?)",
                            (device_id, cama_norm, paciente_id, agora_iso, now_ms),
                        )
                except Exception:
                    pass
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
                "SELECT paciente_id, cama_id FROM paciente_fichas WHERE paciente_id = ?",
                (paciente_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise LookupError("Paciente nao encontrado.")
            existing_cama = row["cama_id"]
            self._assert_cama_disponivel(conn, cama_norm, ignorar_paciente=paciente_id)
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
            
            # History Logic
            try:
                if (existing_cama or None) != (cama_norm or None):
                    cur2 = conn.execute(
                        "SELECT id, start_ms FROM paciente_cama_history WHERE paciente_id = ? AND end_ms IS NULL ORDER BY start_ms DESC LIMIT 1",
                        (paciente_id,),
                    )
                    r2 = cur2.fetchone()
                    now_ms = int(pd.to_datetime(agora_iso).timestamp() * 1000)
                    if r2 is not None:
                        aid = int(r2["id"])
                        conn.execute(
                            "UPDATE paciente_cama_history SET end_ts = ?, end_ms = ? WHERE id = ?",
                            (agora_iso, now_ms, aid),
                        )
                    if cama_norm is not None:
                        conn.execute(
                            "INSERT INTO paciente_cama_history (paciente_id, cama_id, start_ts, start_ms) VALUES (?, ?, ?, ?)",
                            (paciente_id, cama_norm, agora_iso, now_ms),
                        )
                        try:
                            cur = conn.execute(
                                "SELECT device_id FROM device_assignments WHERE cama_id = ? AND end_ms IS NULL ORDER BY start_ms DESC LIMIT 1",
                                (cama_norm,),
                            )
                            row = cur.fetchone()
                            if row is not None:
                                device_id = row["device_id"]
                                conn.execute(
                                    "UPDATE device_assignments SET end_ts = ?, end_ms = ? WHERE device_id = ? AND end_ms IS NULL",
                                    (agora_iso, now_ms, device_id),
                                )
                                conn.execute(
                                    "INSERT INTO device_assignments (device_id, cama_id, paciente_id, start_ts, start_ms) VALUES (?, ?, ?, ?, ?)",
                                    (device_id, cama_norm, paciente_id, agora_iso, now_ms),
                                )
                        except Exception:
                            pass
            except Exception:
                pass
            conn.commit()
            
        return self.get_by_id(paciente_id, include_routines=True) # type: ignore

    def delete(self, paciente_id: str) -> int:
        if not paciente_id:
            raise ValueError("paciente_id deve ser informado")
        with connect(self.db_path) as conn:
            cur = conn.execute("SELECT paciente_id FROM paciente_fichas WHERE paciente_id = ?", (paciente_id,))
            if cur.fetchone() is None:
                return 0
            conn.execute("DELETE FROM paciente_rotinas WHERE paciente_id = ?", (paciente_id,))
            conn.execute("DELETE FROM paciente_documentos WHERE paciente_id = ?", (paciente_id,))
            conn.execute("DELETE FROM paciente_cama_history WHERE paciente_id = ?", (paciente_id,))
            conn.execute("DELETE FROM device_assignments WHERE paciente_id = ?", (paciente_id,))
            conn.execute("DELETE FROM timeline_events WHERE paciente_id = ?", (paciente_id,))
            conn.execute("DELETE FROM paciente_fichas WHERE paciente_id = ?", (paciente_id,))
            conn.execute("DELETE FROM pacientes WHERE id = ?", (paciente_id,))
            conn.commit()
        return 1
