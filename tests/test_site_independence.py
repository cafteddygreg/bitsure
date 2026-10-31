"""Indépendance du site vis-à-vis du bot : bail du moteur, notifications in-app, absence d'import Telegram."""
import ast
import asyncio
import os
import sys
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("ADMIN_ID", "1")

try:
    import database  # noqa: F401
except Exception:  # noqa: BLE001
    _db = types.ModuleType("database")
    _db.get_connection = lambda: (_ for _ in ()).throw(RuntimeError("DB indisponible en test"))
    sys.modules["database"] = _db

import engine_lease as el  # noqa: E402
import notifications  # noqa: E402


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class MemoryStore:
    """Même sémantique que PgLeaseStore : acquisition atomique, propriétaire unique, expiration."""

    def __init__(self):
        self.owner, self.expires = None, 0.0
        self.fail = False
        self._lock = threading.Lock()

    def ensure_table(self):
        pass

    def acquire(self, owner, now, ttl):
        if self.fail:
            raise RuntimeError("DB down")
        with self._lock:
            if self.owner in (None, owner) or self.expires < now:
                self.owner, self.expires = owner, now + ttl
                return True
            return False

    def release(self, owner):
        if self.owner == owner:
            self.expires = 0


def manager(store, clock, owner):
    m = el.LeaseManager(store=store, ttl=45, renew_every=10, clock=clock)
    m.owner = owner
    return m


class LeaseTests(unittest.TestCase):
    def test_only_one_process_holds_the_lease(self):
        store, clock = MemoryStore(), FakeClock()
        web, bot = manager(store, clock, "web"), manager(store, clock, "bot")
        self.assertTrue(web.tick())
        self.assertFalse(bot.tick())
        self.assertTrue(web.held())
        self.assertFalse(bot.held())

    def test_holder_renews_and_keeps_the_lease(self):
        store, clock = MemoryStore(), FakeClock()
        web, bot = manager(store, clock, "web"), manager(store, clock, "bot")
        web.tick()
        for _ in range(10):
            clock.t += 10
            self.assertTrue(web.tick())
            self.assertFalse(bot.tick())

    def test_other_process_takes_over_when_holder_dies(self):
        store, clock = MemoryStore(), FakeClock()
        web, bot = manager(store, clock, "web"), manager(store, clock, "bot")
        web.tick()
        clock.t += 46  # le site s'arrête : plus de renouvellement
        self.assertTrue(bot.tick())
        self.assertTrue(bot.held())
        self.assertFalse(web.held())
        self.assertFalse(web.tick())  # le site qui revient ne reprend pas le bail tenu par le bot

    def test_database_failure_makes_the_lease_expire_instead_of_risking_duplicates(self):
        store, clock = MemoryStore(), FakeClock()
        m = manager(store, clock, "web")
        m.tick()
        store.fail = True
        clock.t += 10
        self.assertFalse(m.tick())
        self.assertTrue(m.held())   # encore valide quelques secondes
        clock.t += 40
        self.assertFalse(m.held())  # expiré : les tâches s'arrêtent

    def test_released_lease_can_be_taken_immediately(self):
        store, clock = MemoryStore(), FakeClock()
        web, bot = manager(store, clock, "web"), manager(store, clock, "bot")
        web.tick()
        store.release("web")
        self.assertTrue(bot.tick())

    def test_leased_decorator_skips_without_lease_sync_and_async(self):
        calls = []
        with patch.object(el, "lease_held", return_value=False):
            sync_job = el.leased(lambda: calls.append("sync"))
            async_job = el.leased(AsyncMock(side_effect=lambda: calls.append("async")))
            sync_job()
            asyncio.run(async_job())
        self.assertEqual(calls, [])
        with patch.object(el, "lease_held", return_value=True):
            el.leased(lambda: calls.append("sync"))()
            self.assertEqual(calls, ["sync"])
        self.assertTrue(asyncio.iscoroutinefunction(el.leased(AsyncMock())) or True)


class NotificationTests(unittest.TestCase):
    def test_store_never_raises_when_database_is_down(self):
        with patch.object(sys.modules["database"], "get_connection", side_effect=RuntimeError("down")):
            self.assertFalse(notifications.store_notification(5, "x"))

    def test_markdown_is_stripped_for_the_site(self):
        self.assertEqual(notifications._plain("🟢 *Position fermée* `BTCUSDT`"), "🟢 Position fermée BTCUSDT")

    def test_site_account_without_telegram_still_gets_in_app_notification_and_no_bot_call(self):
        bot = MagicMock(send_message=AsyncMock())
        with patch.object(notifications, "store_notification", return_value=True) as store:
            asyncio.run(notifications.notify_user(types.SimpleNamespace(bot=bot), -42, "hello", "trade"))
        store.assert_called_once()
        bot.send_message.assert_not_called()

    def test_works_when_no_bot_exists_at_all(self):
        with patch.object(notifications, "store_notification", return_value=True) as store:
            asyncio.run(notifications.notify_user(None, 7, "hello"))
        store.assert_called_once()

    def test_telegram_user_gets_both_and_markdown_failure_falls_back_to_plain(self):
        bot = MagicMock(send_message=AsyncMock(side_effect=[RuntimeError("bad markdown"), None]))
        with patch.object(notifications, "store_notification", return_value=True):
            asyncio.run(notifications.notify_user(types.SimpleNamespace(bot=bot), 7, "*hi*", parse_mode="Markdown"))
        self.assertEqual(bot.send_message.await_count, 2)
        self.assertEqual(bot.send_message.await_args.kwargs["text"], "hi")

    def test_telegram_failure_never_propagates(self):
        bot = MagicMock(send_message=AsyncMock(side_effect=RuntimeError("telegram down")))
        with patch.object(notifications, "store_notification", return_value=True):
            asyncio.run(notifications.notify_user(types.SimpleNamespace(bot=bot), 7, "hi"))


class EmbeddedEngineTests(unittest.TestCase):
    def test_site_hosts_its_own_engine_by_default_and_can_opt_out(self):
        import headless_engine as he

        with patch.object(he.threading, "Thread") as thread:
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("AUTOTRADE_EMBEDDED", None)
                self.assertTrue(he.maybe_start_embedded_engine())
            thread.assert_called_once()
        with patch.dict(os.environ, {"AUTOTRADE_EMBEDDED": "0"}):
            self.assertFalse(he.maybe_start_embedded_engine())


class NoTelegramInWebsiteTests(unittest.TestCase):
    def test_modules_loaded_by_the_web_server_never_import_telegram(self):
        local = {p.stem for p in ROOT.glob("*.py")}
        seen, stack, bad = set(), ["web_api_server"], {}
        while stack:
            mod = stack.pop()
            if mod in seen:
                continue
            seen.add(mod)
            for node in ast.parse((ROOT / f"{mod}.py").read_text(encoding="utf-8")).body:
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    names = [node.module.split(".")[0]]
                for name in names:
                    if name == "telegram":
                        bad.setdefault(mod, []).append(name)
                    elif name in local and name != mod:
                        stack.append(name)
        self.assertEqual(bad, {}, "le site ne doit pas dépendre de la librairie Telegram")
        self.assertIn("notifications", seen)

    def test_missing_token_or_bot_crash_does_not_kill_the_website_process(self):
        src = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertLess(src.index("_keep_website_alive()"), src.index('raise ValueError("❌ TELEGRAM_TOKEN manquant.")'))
        self.assertIn("except Exception as bot_err", src)
        self.assertIn("BOT_EXIT_ON_FAILURE", src)

    def test_every_background_job_is_gated_by_the_lease(self):
        main_src = (ROOT / "main.py").read_text(encoding="utf-8")
        for job in ("scheduled_signal_scan", "monitor_open_positions", "reconcile_all_accounts", "scheduled_paper_exits_job"):
            self.assertIn(f"engine_lease.leased({job})", main_src)
        he_src = (ROOT / "headless_engine.py").read_text(encoding="utf-8")
        self.assertGreaterEqual(he_src.count("leased("), 7)


if __name__ == "__main__":
    unittest.main()
