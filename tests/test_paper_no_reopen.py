"""Régression : une position Paper fermée ne doit jamais être rouverte par un cache obsolète."""
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("ADMIN_ID", "1")

from paper_trader import PaperTrader  # noqa: E402


class _Conn:
    """Enveloppe SQLite imitant l'API utilisée par PaperTrader (placeholders %s)."""

    def __init__(self):
        self.c = sqlite3.connect(":memory:", check_same_thread=False)
        self.c.row_factory = sqlite3.Row
        self.c.execute(
            "CREATE TABLE paper_positions (id TEXT PRIMARY KEY, user_id INT, symbol TEXT, side TEXT,"
            " entry_price REAL, exit_price REAL, sl REAL, tp REAL, qty REAL, leverage REAL, fees_total REAL,"
            " slippage REAL, capital_before REAL, capital_after REAL, current_price REAL, pnl_usdt REAL,"
            " pnl_pct REAL, status TEXT, exit_reason TEXT, opened_at REAL, closed_at REAL, peak_price REAL)"
        )
        self.c.execute("CREATE TABLE paper_capitals (user_id INT PRIMARY KEY, capital REAL)")

    def execute(self, sql, params=()):
        return self.c.execute(sql.replace("%s", "?"), params)

    def commit(self):
        self.c.commit()

    def rollback(self):
        self.c.rollback()


def _make(conn):
    pt = PaperTrader.__new__(PaperTrader)
    pt.conn = conn
    pt.positions, pt.closed_positions, pt.capitals = {}, {}, {}
    pt._load()
    return pt


class PaperNoReopenTest(unittest.TestCase):
    def test_stale_instance_cannot_reopen_closed_position(self):
        conn = _Conn()
        a = _make(conn)
        a.init_capital(1, 10000.0)
        pos, err = a.open_position(1, "BTCUSDT", 100.0, 90.0, 120.0, 1.0, side="BUY", leverage=1.0)
        self.assertIsNone(err)

        stale = _make(conn)  # autre instance qui voit la position ouverte
        self.assertEqual(len(stale.get_positions(1)), 1)

        self.assertIsNotNone(a.close_position(1, pos["id"], 101.0))
        stale.update_price("BTCUSDT", 102.0)  # écriture d'un cache obsolète

        row = conn.execute("SELECT status FROM paper_positions WHERE id = %s", (pos["id"],)).fetchone()
        self.assertEqual(row["status"], "closed")
        self.assertEqual(len(_make(conn).get_positions(1)), 0)

    def test_stale_instance_does_not_credit_capital_twice(self):
        conn = _Conn()
        a = _make(conn)
        a.init_capital(1, 10000.0)
        pos, _ = a.open_position(1, "BTCUSDT", 100.0, 90.0, 120.0, 1.0, side="BUY", leverage=1.0)
        stale = _make(conn)
        a.close_position(1, pos["id"], 101.0)
        cap_after_first = conn.execute("SELECT capital FROM paper_capitals WHERE user_id = 1").fetchone()["capital"]
        self.assertIsNone(stale.close_position(1, pos["id"], 150.0))
        cap_now = conn.execute("SELECT capital FROM paper_capitals WHERE user_id = 1").fetchone()["capital"]
        self.assertEqual(cap_after_first, cap_now)

    def test_normal_open_update_close_still_works(self):
        conn = _Conn()
        a = _make(conn)
        a.init_capital(1, 10000.0)
        pos, _ = a.open_position(1, "ETHUSDT", 100.0, 90.0, 120.0, 1.0, side="BUY", leverage=1.0)
        a.update_price("ETHUSDT", 105.0)
        row = conn.execute("SELECT current_price, status FROM paper_positions WHERE id = %s", (pos["id"],)).fetchone()
        self.assertEqual(row["status"], "open")
        self.assertEqual(row["current_price"], 105.0)
        self.assertIsNotNone(a.close_position(1, pos["id"], 105.0))


class PaperGetInstanceTest(unittest.TestCase):
    def test_get_instance_exists_and_sees_positions_opened_elsewhere(self):
        import paper_trader as module

        conn = _Conn()
        shared = _make(conn)
        shared.init_capital(1, 10000.0)
        web = _make(conn)  # instance « API web » : ouvre après le démarrage de l'instance partagée
        pos, err = web.open_position(1, "BTCUSDT", 100.0, 90.0, 120.0, 1.0, side="BUY", leverage=1.0)
        self.assertIsNone(err)
        self.assertEqual(len(shared.get_positions(1)), 0)  # cache obsolète

        original = module.paper_trader
        module.paper_trader = shared
        try:
            pt = PaperTrader.get_instance()
        finally:
            module.paper_trader = original
        self.assertIs(pt, shared)
        self.assertEqual(len(pt.get_positions(1)), 1)

        pt.update_price("BTCUSDT", 130.0)  # TP à 120 touché
        closed = pt.check_exits()
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0]["exit_reason"], "TP")
        row = conn.execute("SELECT status FROM paper_positions WHERE id = %s", (pos["id"],)).fetchone()
        self.assertEqual(row["status"], "closed")


if __name__ == "__main__":
    unittest.main()
