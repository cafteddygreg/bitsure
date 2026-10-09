import atexit
import os
import threading
import time
from contextlib import contextmanager

try:
    import psycopg2
    from psycopg2.extras import DictCursor
    from psycopg2.pool import ThreadedConnectionPool
    try:
        from psycopg2.pool import PoolError
    except ImportError:
        PoolError = Exception
except ImportError:
    import importlib.util as _ilu
    _sc_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sitecustomize.py")
    if os.path.exists(_sc_path):
        _spec = _ilu.spec_from_file_location("_bitsure_sitecustomize", _sc_path)
        if _spec and _spec.loader:
            _mod = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)
    import psycopg2
    from psycopg2.extras import DictCursor
    from psycopg2.pool import ThreadedConnectionPool
    PoolError = getattr(psycopg2.pool, "PoolError", Exception)

_pool = None
_pool_lock = threading.RLock()
_pool_cond = threading.Condition(_pool_lock)


def _load_database_url():
    try:
        from config import DATABASE_URL as _cfg_db_url
        if _cfg_db_url:
            return _cfg_db_url
    except Exception:
        pass
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return "sqlite:///bitsure_teddy.db"

    with open(env_path, "r", encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == "DATABASE_URL":
                val = value.strip().strip('"').strip("'")
                if val:
                    return val
    return "sqlite:///bitsure_teddy.db"


def _get_pool() -> ThreadedConnectionPool:
    global _pool
    with _pool_lock:
        if _pool is None:
            database_url = _load_database_url()
            if not database_url:
                raise RuntimeError("DATABASE_URL is required for PostgreSQL access")
            minconn = int(os.getenv("DB_POOL_MINCONN", "1"))
            maxconn = int(os.getenv("DB_POOL_MAXCONN", "20"))
            _pool = ThreadedConnectionPool(minconn, maxconn, database_url, cursor_factory=DictCursor)
            with pooled_connection() as conn:
                _ensure_schema(PostgresConnection(conn))
        return _pool


def _acquire_conn(timeout: float = 10.0):
    """Acquire a connection from the pool, waiting gracefully if all connections are briefly busy."""
    deadline = time.monotonic() + timeout
    pool = _get_pool()
    while True:
        with _pool_cond:
            try:
                conn = pool.getconn()
                if getattr(conn, "closed", 0):
                    try:
                        pool.putconn(conn, close=True)
                    except Exception:
                        pass
                    conn = pool.getconn()
                return conn
            except PoolError:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                _pool_cond.wait(timeout=min(remaining, 0.15))

    # Fallback: if pool is still full after waiting, open a direct short-lived connection
    database_url = _load_database_url()
    conn = psycopg2.connect(database_url, cursor_factory=DictCursor)
    setattr(conn, "_is_direct_fallback", True)
    return conn


def _release_conn(conn, close: bool = False):
    """Return a connection to the pool immediately and notify any waiting threads."""
    if conn is None:
        return
    if getattr(conn, "_is_direct_fallback", False):
        try:
            conn.close()
        except Exception:
            pass
        return
    with _pool_cond:
        try:
            if _pool is not None:
                if not getattr(conn, "closed", 1) and not getattr(conn, "autocommit", False):
                    try:
                        conn.rollback()
                    except Exception:
                        close = True
                _pool.putconn(conn, close=close or bool(getattr(conn, "closed", 0)))
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
        finally:
            _pool_cond.notify_all()


@contextmanager
def pooled_connection():
    if _pool is None:
        database_url = _load_database_url()
        if not database_url:
            raise RuntimeError("DATABASE_URL is required for PostgreSQL access")
        conn = psycopg2.connect(database_url, cursor_factory=DictCursor)
        conn.autocommit = False
        try:
            yield conn
        finally:
            conn.close()
        return

    conn = _acquire_conn()
    conn.autocommit = False
    try:
        yield conn
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        _release_conn(conn)


class _BufferedCursor:
    """Lightweight cursor adapter that holds fetched rows after the underlying DB connection is returned to the pool."""

    def __init__(self, rows, description, rowcount: int):
        self._rows = list(rows) if rows is not None else []
        self._idx = 0
        self.description = description
        self.rowcount = rowcount

    def fetchone(self):
        if self._idx >= len(self._rows):
            return None
        row = self._rows[self._idx]
        self._idx += 1
        return row

    def fetchall(self):
        if self._idx == 0:
            self._idx = len(self._rows)
            return list(self._rows)
        rem = self._rows[self._idx:]
        self._idx = len(self._rows)
        return list(rem)

    def fetchmany(self, size: int = 1):
        rem = self._rows[self._idx : self._idx + size]
        self._idx += len(rem)
        return list(rem)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __iter__(self):
        return iter(self.fetchall())


class _ManagedCursorContext:
    """Context manager for `with db.cursor() as cur:` that automatically returns the connection on exit."""

    def __init__(self):
        self._conn = None
        self._cur = None

    def __enter__(self):
        self._conn = _acquire_conn()
        self._conn.autocommit = True
        self._cur = self._conn.cursor()
        return self._cur

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self._cur is not None:
                self._cur.close()
        except Exception:
            pass
        _release_conn(self._conn, close=exc_type is not None)
        self._conn = None
        self._cur = None


class PostgresConnection:
    """Stateless connection proxy that borrows a pooled connection ONLY for the duration
    of each query and returns it immediately, preventing thread-local connection leaks."""

    def __init__(self, conn=None):
        self._schema_conn = conn

    def execute(self, sql, params=None):
        if self._schema_conn is not None:
            cur = self._schema_conn.cursor()
            try:
                cur.execute(sql, params or ())
                if not getattr(self._schema_conn, "autocommit", False):
                    self._schema_conn.commit()
                desc = getattr(cur, "description", None)
                rows = cur.fetchall() if desc is not None else []
                return _BufferedCursor(rows, desc, getattr(cur, "rowcount", 0))
            except Exception:
                try:
                    if not getattr(self._schema_conn, "autocommit", False):
                        self._schema_conn.rollback()
                except Exception:
                    pass
                raise
            finally:
                cur.close()

        conn = _acquire_conn()
        broken = False
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(sql, params or ())
                desc = getattr(cur, "description", None)
                rows = cur.fetchall() if desc is not None else []
                return _BufferedCursor(rows, desc, getattr(cur, "rowcount", 0))
        except psycopg2.OperationalError:
            broken = True
            raise
        finally:
            _release_conn(conn, close=broken)

    def cursor(self):
        if self._schema_conn is not None:
            return self._schema_conn.cursor()
        return _ManagedCursorContext()

    def commit(self):
        if self._schema_conn is not None and not getattr(self._schema_conn, "autocommit", False):
            self._schema_conn.commit()

    def rollback(self):
        if self._schema_conn is not None and not getattr(self._schema_conn, "autocommit", False):
            self._schema_conn.rollback()

    def close(self):
        pass


def get_connection():
    """Return a dedicated pooled connection for one operation/transaction."""
    conn = _acquire_conn()
    conn.autocommit = False
    return _PooledRawConnection(conn)


class _PooledRawConnection:
    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None and self._conn is not None:
            try:
                self._conn.rollback()
            except Exception:
                pass
        self.close()

    def close(self):
        if self._conn is not None:
            conn, self._conn = self._conn, None
            _release_conn(conn)

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def get_db():
    """Return a stateless PostgreSQL compatibility connection that never leaks pool slots."""
    _get_pool()
    return PostgresConnection()


def close_db():
    global _pool
    with _pool_cond:
        if _pool is not None:
            try:
                _pool.closeall()
            except Exception:
                pass
            _pool = None
        _pool_cond.notify_all()



def _ensure_schema(conn):
    statements = [
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            role TEXT DEFAULT 'tester',
            lang TEXT DEFAULT 'en',
            timeframe TEXT DEFAULT '1h',
            risk TEXT DEFAULT 'medium',
            terms_accepted INTEGER DEFAULT 0,
            trial_start DOUBLE PRECISION DEFAULT 0,
            created_at DOUBLE PRECISION DEFAULT 0,
            approved INTEGER DEFAULT 0,
            memo TEXT,
            username TEXT,
            pin TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS usage (
            user_id BIGINT,
            date TEXT,
            count INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, date)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS settings (
            user_id BIGINT,
            key TEXT,
            value TEXT,
            PRIMARY KEY (user_id, key)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS watchlist (
            user_id BIGINT,
            symbol TEXT,
            PRIMARY KEY (user_id, symbol)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS alerts (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            symbol TEXT,
            condition TEXT,
            price DOUBLE PRECISION,
            triggered INTEGER DEFAULT 0,
            created_at DOUBLE PRECISION DEFAULT 0,
            triggered_at DOUBLE PRECISION DEFAULT 0
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS signals (
            id TEXT PRIMARY KEY,
            user_id BIGINT,
            symbol TEXT,
            direction TEXT,
            entry_price DOUBLE PRECISION,
            sl DOUBLE PRECISION,
            tp DOUBLE PRECISION,
            score INTEGER,
            status TEXT DEFAULT 'pending',
            validation_status TEXT,
            validation_reason TEXT,
            rejection_reason TEXT,
            result_price DOUBLE PRECISION,
            result_pct DOUBLE PRECISION,
            pnl DOUBLE PRECISION,
            capital_before DOUBLE PRECISION,
            capital_after DOUBLE PRECISION,
            timeframe TEXT DEFAULT '1h',
            signal_type TEXT DEFAULT 'analyse',
            rr_ratio DOUBLE PRECISION,
            asset_class TEXT,
            params_used TEXT,
            created_at DOUBLE PRECISION,
            closed_at DOUBLE PRECISION
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS paper_positions (
            id TEXT PRIMARY KEY,
            user_id BIGINT,
            symbol TEXT,
            side TEXT DEFAULT 'BUY',
            entry_price DOUBLE PRECISION,
            exit_price DOUBLE PRECISION,
            sl DOUBLE PRECISION,
            tp DOUBLE PRECISION,
            qty DOUBLE PRECISION,
            leverage DOUBLE PRECISION DEFAULT 1,
            fees_total DOUBLE PRECISION DEFAULT 0,
            slippage DOUBLE PRECISION DEFAULT 0,
            capital_before DOUBLE PRECISION,
            capital_after DOUBLE PRECISION,
            current_price DOUBLE PRECISION,
            pnl_usdt DOUBLE PRECISION,
            pnl_pct DOUBLE PRECISION,
            status TEXT DEFAULT 'open',
            exit_reason TEXT,
            opened_at DOUBLE PRECISION,
            closed_at DOUBLE PRECISION,
            peak_price DOUBLE PRECISION
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS paper_capitals (
            user_id BIGINT PRIMARY KEY,
            capital DOUBLE PRECISION DEFAULT 10000
        )
        """,
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS approved INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS memo TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS username TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS pin TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS account_status TEXT DEFAULT 'PENDING_APPROVAL'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS quota_daily_analyses INTEGER DEFAULT 15",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS quota_daily_scans INTEGER DEFAULT 10",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS quota_max_alerts INTEGER DEFAULT 10",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS quota_max_paper_trades INTEGER DEFAULT 25",
        """
        CREATE TABLE IF NOT EXISTS user_feature_usage (
            user_id BIGINT,
            date TEXT,
            feature TEXT,
            count INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, date, feature)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS security_events (
            id SERIAL PRIMARY KEY,
            event_type TEXT NOT NULL,
            severity TEXT DEFAULT 'info',
            user_id BIGINT,
            email TEXT,
            ip_address TEXT,
            details TEXT,
            created_at DOUBLE PRECISION DEFAULT 0
        )
        """,
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS created_at DOUBLE PRECISION DEFAULT 0",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS triggered_at DOUBLE PRECISION DEFAULT 0",
        "ALTER TABLE signals ADD COLUMN IF NOT EXISTS user_id BIGINT",
        "ALTER TABLE signals ADD COLUMN IF NOT EXISTS validation_status TEXT",
        "ALTER TABLE signals ADD COLUMN IF NOT EXISTS validation_reason TEXT",
        "ALTER TABLE signals ADD COLUMN IF NOT EXISTS rejection_reason TEXT",
        "ALTER TABLE signals ADD COLUMN IF NOT EXISTS result_price DOUBLE PRECISION",
        "ALTER TABLE signals ADD COLUMN IF NOT EXISTS pnl DOUBLE PRECISION",
        "ALTER TABLE signals ADD COLUMN IF NOT EXISTS capital_before DOUBLE PRECISION",
        "ALTER TABLE signals ADD COLUMN IF NOT EXISTS capital_after DOUBLE PRECISION",
        "ALTER TABLE signals ADD COLUMN IF NOT EXISTS timeframe TEXT DEFAULT '1h'",
        "ALTER TABLE signals ADD COLUMN IF NOT EXISTS signal_type TEXT DEFAULT 'analyse'",
        "ALTER TABLE signals ADD COLUMN IF NOT EXISTS rr_ratio DOUBLE PRECISION",
        "ALTER TABLE signals ADD COLUMN IF NOT EXISTS asset_class TEXT",
        "ALTER TABLE signals ADD COLUMN IF NOT EXISTS params_used TEXT",
        "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS peak_price DOUBLE PRECISION",
        # Nouvelles colonnes paper trading v2
        "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS side TEXT DEFAULT 'BUY'",
        "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS exit_price DOUBLE PRECISION",
        "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS leverage DOUBLE PRECISION DEFAULT 1",
        "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS fees_total DOUBLE PRECISION DEFAULT 0",
        "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS slippage DOUBLE PRECISION DEFAULT 0",
        "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS capital_before DOUBLE PRECISION",
        "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS capital_after DOUBLE PRECISION",
        """
        CREATE TABLE IF NOT EXISTS trading_config (
            user_id BIGINT PRIMARY KEY,
            auto_trade BOOLEAN DEFAULT FALSE,
            leverage INT DEFAULT 1,
            risk_per_trade DOUBLE PRECISION DEFAULT 1.0,
            max_positions INT DEFAULT 3,
            min_score INT DEFAULT 70,
            max_daily_loss DOUBLE PRECISION DEFAULT 5.0,
            trailing_stop BOOLEAN DEFAULT FALSE,
            trailing_stop_pct DOUBLE PRECISION DEFAULT 1.0,
            dca_enabled BOOLEAN DEFAULT FALSE,
            dca_steps INT DEFAULT 3,
            dca_step_pct DOUBLE PRECISION DEFAULT 2.0,
            symbol_whitelist TEXT DEFAULT '',
            symbol_blacklist TEXT DEFAULT '',
            periodic_analysis_enabled BOOLEAN DEFAULT FALSE,
            market_type TEXT DEFAULT 'futures',
            trading_style TEXT DEFAULT 'day',
            analysis_timeframe TEXT DEFAULT '1h',
            analysis_interval_minutes INT DEFAULT 5,
            testnet BOOLEAN DEFAULT TRUE,
            cooldown_seconds INT DEFAULT 0,
            daily_loss_accum DOUBLE PRECISION DEFAULT 0.0,
            daily_loss_reset_at DOUBLE PRECISION,
            safety_lock BOOLEAN DEFAULT FALSE,
            safety_lock_reason TEXT,
            safety_lock_at DOUBLE PRECISION,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS periodic_analysis_enabled BOOLEAN DEFAULT FALSE",
        "ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS trading_style TEXT DEFAULT 'day'",
        "ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS analysis_timeframe TEXT DEFAULT '1h'",
        "ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS analysis_interval_minutes INT DEFAULT 5",
        "ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS safety_lock BOOLEAN DEFAULT FALSE",
        "ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS safety_lock_reason TEXT",
        "ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS safety_lock_at DOUBLE PRECISION",
        "ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS safety_warn BOOLEAN DEFAULT FALSE",
        "ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS safety_warn_reason TEXT",
        "ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS safety_warn_at DOUBLE PRECISION",
        "ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS safety_lock_ttl_seconds INT DEFAULT 3600",
        """
        CREATE TABLE IF NOT EXISTS binance_credentials (
            user_id BIGINT PRIMARY KEY,
            api_key TEXT NOT NULL,
            api_secret TEXT NOT NULL,
            testnet BOOLEAN DEFAULT TRUE,
            is_valid BOOLEAN DEFAULT TRUE,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS user_security_codes (
            user_id BIGINT PRIMARY KEY,
            code_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            failed_attempts INT DEFAULT 0,
            locked_until DOUBLE PRECISION,
            updated_at DOUBLE PRECISION
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS trades (
            id SERIAL PRIMARY KEY,
            signal_id TEXT,
            user_id BIGINT,
            symbol TEXT,
            direction TEXT,
            entry_price DOUBLE PRECISION,
            sl_price DOUBLE PRECISION,
            tp_price DOUBLE PRECISION,
            quantity DOUBLE PRECISION,
            leverage INT,
            market_type TEXT,
            status TEXT DEFAULT 'open',
            opened_at DOUBLE PRECISION,
            closed_at DOUBLE PRECISION,
            exit_reason TEXT,
            pnl_usdt DOUBLE PRECISION,
            pnl_pct DOUBLE PRECISION,
            binance_order_id TEXT,
            binance_client_order_id TEXT,
            sl_order_id TEXT,
            tp_order_id TEXT,
            error_message TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS strategy_lab_presets (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            symbol TEXT DEFAULT 'BTCUSDT',
            timeframe TEXT DEFAULT '15m',
            trading_style TEXT DEFAULT 'day',
            params_json TEXT NOT NULL,
            tags TEXT DEFAULT '',
            is_favorite INTEGER DEFAULT 0,
            notes TEXT DEFAULT '',
            created_by BIGINT,
            created_at DOUBLE PRECISION NOT NULL,
            updated_at DOUBLE PRECISION NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS strategy_lab_runs (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            preset_id INTEGER,
            parent_run_id INTEGER,
            market_type TEXT DEFAULT 'futures',
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            trading_style TEXT NOT NULL,
            period_split TEXT DEFAULT 'full',
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            data_source TEXT NOT NULL,
            candles_count INTEGER DEFAULT 0,
            engine_version TEXT DEFAULT '2.1.0',
            strategy_version TEXT DEFAULT 'teddy_v2',
            status TEXT DEFAULT 'COMPLETED',
            is_candidate INTEGER DEFAULT 0,
            data_quality_json TEXT DEFAULT '{}',
            steps_json TEXT DEFAULT '[]',
            params_json TEXT NOT NULL,
            metrics_json TEXT NOT NULL,
            trades_json TEXT NOT NULL,
            equity_json TEXT NOT NULL,
            signals_summary_json TEXT NOT NULL,
            tags TEXT DEFAULT '',
            is_favorite INTEGER DEFAULT 0,
            notes TEXT DEFAULT '',
            created_by BIGINT,
            created_at DOUBLE PRECISION NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS strategy_lab_ohlcv (
            market_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            open_time_ms BIGINT NOT NULL,
            close_time_ms BIGINT NOT NULL,
            open DOUBLE PRECISION NOT NULL,
            high DOUBLE PRECISION NOT NULL,
            low DOUBLE PRECISION NOT NULL,
            close DOUBLE PRECISION NOT NULL,
            volume DOUBLE PRECISION NOT NULL,
            source TEXT NOT NULL,
            fetched_at DOUBLE PRECISION NOT NULL,
            PRIMARY KEY (market_type, symbol, timeframe, open_time_ms)
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_strategy_lab_ohlcv_lookup
        ON strategy_lab_ohlcv(market_type, symbol, timeframe, open_time_ms)
        """,
        """
        CREATE TABLE IF NOT EXISTS strategy_lab_candles_cache (
            cache_key TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            start_ts BIGINT NOT NULL,
            end_ts BIGINT NOT NULL,
            data_source TEXT NOT NULL,
            candles_json TEXT NOT NULL,
            updated_at DOUBLE PRECISION NOT NULL
        )
        """,
    ]
    for statement in statements:
        conn.execute(statement)
    conn.commit()
    for col_def in (
        "parent_run_id INTEGER",
        "market_type TEXT DEFAULT 'futures'",
        "period_split TEXT DEFAULT 'full'",
        "engine_version TEXT DEFAULT '2.1.0'",
        "strategy_version TEXT DEFAULT 'teddy_v2'",
        "status TEXT DEFAULT 'COMPLETED'",
        "is_candidate INTEGER DEFAULT 0",
        "data_quality_json TEXT DEFAULT '{}'",
        "steps_json TEXT DEFAULT '[]'",
    ):
        try:
            conn.execute(f"ALTER TABLE strategy_lab_runs ADD COLUMN {col_def}")
            conn.commit()
        except Exception:
            conn.rollback()
    try:
        # Synchronisation automatique : tout utilisateur PRO / payant ou déjà approuvé
        # (sauf s'il est explicitement REJECTED ou SUSPENDED) a approved = 1, terms_accepted = 1 et account_status = 'APPROVED'.
        conn.execute(
            """
            UPDATE users
            SET approved = 1,
                terms_accepted = 1,
                account_status = 'APPROVED',
                role = CASE
                    WHEN LOWER(TRIM(COALESCE(role, ''))) IN ('pro', 'paid', 'premium', 'vip') THEN 'pro'
                    WHEN LOWER(TRIM(COALESCE(role, ''))) = 'admin' THEN 'admin'
                    ELSE COALESCE(NULLIF(TRIM(role), ''), 'tester')
                END
            WHERE COALESCE(account_status, '') NOT IN ('REJECTED', 'SUSPENDED')
              AND (
                  LOWER(TRIM(COALESCE(role, ''))) IN ('pro', 'paid', 'premium', 'vip', 'admin')
                  OR COALESCE(approved, 0) != 0
              )
            """
        )
        conn.execute(
            """
            UPDATE users
            SET account_status = 'PENDING_APPROVAL'
            WHERE COALESCE(account_status, '') = '' AND COALESCE(approved, 0) = 0
            """
        )
        conn.commit()
    except Exception:
        conn.rollback()
    try:
        conn.execute("DELETE FROM signals WHERE direction = 'WAIT'")
        conn.execute("ALTER TABLE signals ADD CONSTRAINT chk_no_wait CHECK (direction <> 'WAIT')")
        conn.commit()
    except Exception:
        conn.rollback()


atexit.register(close_db)
