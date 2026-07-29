"""Repository for User related database operations."""
from __future__ import annotations

import sqlite3
from typing import Optional, Dict

import structlog

from interface.db_core import connect, utc_now_iso

logger = structlog.get_logger(__name__)

class UltimoAdmin(RuntimeError):
    """A operacao deixaria a instalacao sem nenhum administrador ativo.

    Rebaixar ou desativar o ultimo admin torna backup, importacao e gestao de
    usuarios permanentemente inacessiveis — nao ha por onde recuperar pela
    aplicacao.
    """


class UserRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _ensure_users_role_column(self, conn: sqlite3.Connection) -> None:
        """Add role column to users table if it doesn't exist."""
        info = conn.execute("PRAGMA table_info(users)").fetchall()
        colunas = {str(row["name"]) for row in info}
        if "role" not in colunas:
            conn.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'staff'")

    def create(
        self,
        username: str,
        password_hash: str,
        display_name: str | None = None,
        role: str | None = None,
    ) -> str:
        """Cria um usuario e devolve o papel atribuido.

        Quando `role` nao e informado, o PRIMEIRO usuario da instalacao vira
        "admin" e os demais "staff". Sem isso ninguem jamais seria admin: o
        create nunca gravava a coluna e o default do schema e "staff", entao os
        endpoints administrativos ficariam inalcançaveis depois de passarem a
        exigir o papel.
        """
        uname = str(username or "").strip()
        if not uname:
            raise ValueError("username invalido")
        ph = str(password_hash or "").strip()
        if not ph:
            raise ValueError("password_hash necessario")
        disp = None if display_name is None else str(display_name).strip() or None
        agora = utc_now_iso()

        with connect(self.db_path) as conn:
            self._ensure_users_role_column(conn)
            cur = conn.execute("SELECT username FROM users WHERE username = ?", (uname,))
            if cur.fetchone() is not None:
                raise ValueError("usuario ja existe")

            if role is None:
                total = int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])
                role = "admin" if total == 0 else "staff"

            conn.execute(
                "INSERT INTO users (username, password_hash, display_name, created_at, role)"
                " VALUES (?, ?, ?, ?, ?)",
                (uname, ph, disp, agora, role),
            )
        return role

    def count(self) -> int:
        """Quantidade de usuarios cadastrados.

        Usado pelo /auth/register para liberar o cadastro do PRIMEIRO usuario
        (bootstrap da instalacao) e exigir credencial dai em diante.
        """
        with connect(self.db_path) as conn:
            self._ensure_users_role_column(conn)
            cur = conn.execute("SELECT COUNT(*) FROM users")
            return int(cur.fetchone()[0])

    PAPEIS_VALIDOS = frozenset({"admin", "staff"})

    def listar(self) -> list[Dict]:
        """Lista os usuarios, sem expor o hash de senha."""
        with connect(self.db_path) as conn:
            self._ensure_users_role_column(conn)
            linhas = conn.execute(
                "SELECT username, display_name, role, ativo, created_at,"
                "       coren, categoria"
                " FROM users ORDER BY created_at"
            ).fetchall()
        return [
            {**dict(linha), "ativo": bool(linha["ativo"])}
            for linha in linhas
        ]

    def contar_admins_ativos(self, exceto: str | None = None) -> int:
        """Quantos admins ativos existem (opcionalmente ignorando um).

        Serve para impedir que a instalacao fique sem nenhum administrador —
        rebaixar ou desativar o ultimo admin deixaria backup, importacao e
        gestao de usuarios permanentemente inacessiveis.
        """
        sql = "SELECT COUNT(*) FROM users WHERE role = 'admin' AND ativo = 1"
        params: tuple = ()
        if exceto:
            sql += " AND username != ?"
            params = (exceto,)
        with connect(self.db_path) as conn:
            self._ensure_users_role_column(conn)
            return int(conn.execute(sql, params).fetchone()[0])

    def _restariam_admins(self, conn: sqlite3.Connection, exceto: str) -> bool:
        """Sobra algum admin ativo se `exceto` deixar de contar? (dentro da transacao)"""
        total = conn.execute(
            "SELECT COUNT(*) FROM users WHERE role = 'admin' AND ativo = 1 AND username != ?",
            (exceto,),
        ).fetchone()[0]
        return int(total) > 0

    def definir_papel(self, username: str, role: str) -> None:
        """Altera o papel, recusando o que deixaria a instalacao sem admin.

        A checagem mora AQUI, na mesma transacao do UPDATE, e nao no router.
        Antes eram duas conexoes separadas: o router contava os admins, e so
        depois — noutra conexao — gravava. Duas requisicoes simultaneas
        rebaixando admins diferentes viam, cada uma, o outro ainda como admin,
        e as duas passavam. O resultado e o estado que o modulo declara
        impossivel: zero administradores, com backup, importacao e gestao de
        usuarios permanentemente inacessiveis.

        `BEGIN IMMEDIATE` pega o lock de escrita antes do SELECT, entao a
        contagem e o UPDATE enxergam o mesmo estado.
        """
        if role not in self.PAPEIS_VALIDOS:
            raise ValueError(f"papel invalido: {role}")
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            if role != "admin" and not self._restariam_admins(conn, username):
                # So bloqueia se o alvo for de fato o ultimo admin ativo; para
                # quem ja e staff, `_restariam_admins` conta os admins todos.
                atual = conn.execute(
                    "SELECT role, ativo FROM users WHERE username = ?", (username,)
                ).fetchone()
                if atual is not None and atual["role"] == "admin" and atual["ativo"]:
                    raise UltimoAdmin("Nao e possivel rebaixar o ultimo administrador ativo.")
            cur = conn.execute(
                "UPDATE users SET role = ? WHERE username = ?", (role, username)
            )
            if cur.rowcount == 0:
                raise LookupError("usuario nao encontrado")

    def definir_ativo(self, username: str, ativo: bool) -> None:
        """Ativa/desativa, recusando o que deixaria a instalacao sem admin.

        Mesma razao de `definir_papel`: o invariante e verificado na transacao
        que o aplica.
        """
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            if not ativo and not self._restariam_admins(conn, username):
                atual = conn.execute(
                    "SELECT role, ativo FROM users WHERE username = ?", (username,)
                ).fetchone()
                if atual is not None and atual["role"] == "admin" and atual["ativo"]:
                    raise UltimoAdmin("Nao e possivel desativar o ultimo administrador ativo.")
            cur = conn.execute(
                "UPDATE users SET ativo = ? WHERE username = ?",
                (1 if ativo else 0, username),
            )
            if cur.rowcount == 0:
                raise LookupError("usuario nao encontrado")

    def definir_senha(self, username: str, password_hash: str) -> None:
        ph = str(password_hash or "").strip()
        if not ph:
            raise ValueError("password_hash necessario")
        with connect(self.db_path) as conn:
            cur = conn.execute(
                "UPDATE users SET password_hash = ? WHERE username = ?", (ph, username)
            )
            if cur.rowcount == 0:
                raise LookupError("usuario nao encontrado")

    def get_by_username(self, username: str) -> Optional[Dict]:
        uname = str(username or "").strip()
        if not uname:
            return None
        with connect(self.db_path) as conn:
            self._ensure_users_role_column(conn)
            cur = conn.execute(
                "SELECT username, password_hash, display_name, created_at, role, ativo,"
                " tokens_validos_apos FROM users WHERE username = ?",
                (uname,),
            )
            row = cur.fetchone()
        return None if row is None else dict(row)

    # ------------------------------------------------------------------
    # Identificacao profissional
    # ------------------------------------------------------------------
    CATEGORIAS_VALIDAS = {"enfermeiro", "tecnico", "auxiliar", "outro"}

    def definir_registro_profissional(
        self, username: str, coren: str | None, categoria: str | None
    ) -> dict:
        """Numero no conselho e categoria de quem opera o sistema.

        COFEN Res. 429/2012 exige que o registro de enfermagem identifique o
        profissional por nome E numero de registro. Com um `username` solto, o
        que este sistema produz e apoio de plantao — nao documentacao — e a
        equipe segue registrando reposicionamento a parte no prontuario, que e
        o caminho mais curto para a ferramenta ser abandonada.

        Nao valida o formato do COREN: ele varia por estado e por categoria
        (`COREN-SP 123456-ENF`), e uma expressao regular errada aqui recusaria
        registro legitimo — que e pior que aceitar um digitado torto, porque o
        primeiro impede o trabalho e o segundo e corrigivel.
        """
        categoria_norm = None if categoria is None else str(categoria).strip().lower()
        if categoria_norm is not None and categoria_norm not in self.CATEGORIAS_VALIDAS:
            raise ValueError(
                f"categoria invalida: {categoria!r}"
                f" (aceitas: {sorted(self.CATEGORIAS_VALIDAS)})"
            )
        coren_norm = None if coren is None else str(coren).strip().upper() or None

        with connect(self.db_path) as conn:
            cur = conn.execute(
                "UPDATE users SET coren = ?, categoria = ? WHERE username = ?",
                (coren_norm, categoria_norm, username),
            )
            if cur.rowcount == 0:
                raise LookupError(f"Usuario {username} nao encontrado.")
        logger.info(
            "registro_profissional_definido",
            usuario=username,
            categoria=categoria_norm,
            tem_coren=bool(coren_norm),
        )
        return {"username": username, "coren": coren_norm, "categoria": categoria_norm}
