"""Repository for User related database operations."""
from __future__ import annotations

import sqlite3
from typing import Optional, Dict
from interface.db_core import connect, utc_now_iso

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

    def get_by_username(self, username: str) -> Optional[Dict]:
        uname = str(username or "").strip()
        if not uname:
            return None
        with connect(self.db_path) as conn:
            self._ensure_users_role_column(conn)
            cur = conn.execute("SELECT username, password_hash, display_name, created_at, role FROM users WHERE username = ?", (uname,))
            row = cur.fetchone()
        return None if row is None else dict(row)
