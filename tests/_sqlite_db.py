"""Petit adaptateur SQLite imitant get_db() (placeholders %s, lignes accessibles par clé) pour tester sans PostgreSQL."""
import sqlite3
import threading


class _Row(dict):
    pass


class _Cursor:
    def __init__(self, rows, rowcount):
        self._rows = rows
        self.rowcount = rowcount

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows


class SqliteDB:
    def __init__(self):
        self._conn = sqlite3.connect(":memory:", check_same_thread=False, isolation_level=None)
        self._conn.row_factory = lambda cur, row: _Row({d[0]: row[i] for i, d in enumerate(cur.description)})
        self._lock = threading.Lock()

    def execute(self, sql, params=None):
        sql = sql.replace("%s", "?").replace("ADD COLUMN IF NOT EXISTS", "ADD COLUMN")
        if "IF NOT EXISTS" in sql and sql.lstrip().upper().startswith("ALTER"):
            raise sqlite3.OperationalError("IF NOT EXISTS unsupported on ALTER")
        with self._lock:
            cur = self._conn.execute(sql, tuple(params or ()))
            rows = cur.fetchall() if cur.description else []
            return _Cursor(rows, cur.rowcount)


def make_db():
    db = SqliteDB()
    db.execute("CREATE TABLE web_accounts (email TEXT PRIMARY KEY, user_id BIGINT UNIQUE, password_hash TEXT NOT NULL, google_sub TEXT, last_login_at DOUBLE PRECISION DEFAULT 0)")
    db.execute(
        """CREATE TABLE web_sessions (token TEXT PRIMARY KEY, token_hash TEXT, user_id BIGINT NOT NULL, email TEXT,
           csrf_token TEXT, ip_address TEXT, user_agent TEXT, created_at DOUBLE PRECISION DEFAULT 0, expires_at DOUBLE PRECISION DEFAULT 0)"""
    )
    db.execute(
        """CREATE TABLE security_events (id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT, severity TEXT, user_id BIGINT,
           email TEXT, ip_address TEXT, details TEXT, created_at DOUBLE PRECISION)"""
    )
    return db
