"""
Bail (« lease ») du moteur de fond : un seul processus à la fois exécute les tâches de trading et de surveillance.

Pourquoi : ces tâches (scan des signaux, suivi des positions SL/TP, sorties Paper, réconciliation Binance, alertes de
prix, suivi des résultats de signaux) tournaient uniquement dans le processus du bot Telegram. Le site peut maintenant
les héberger aussi (headless_engine.py), donc le site comme le bot peuvent travailler seuls, mais JAMAIS en double :
le processus qui détient le bail exécute les tâches, l'autre reste en veille et reprend la main si le bail expire
(processus arrêté ou planté).

Fonctionnement : une ligne en base (`engine_lease`) avec un propriétaire et une date d'expiration. Chaque processus
tente de l'acquérir ou de le renouveler toutes les `RENEW_EVERY` secondes. L'acquisition est atomique (une seule
requête SQL), donc deux processus ne peuvent pas tenir le bail en même temps. Si la base est injoignable, le bail
n'est plus renouvelé et les tâches s'arrêtent d'elles-mêmes à l'expiration : on préfère ne rien faire plutôt que
risquer un double ordre.

Désactivation (déconseillé) : ENGINE_LEASE_DISABLED=1 rend `lease_held()` toujours vrai (ancien comportement).
"""
from __future__ import annotations

import asyncio
import functools
import logging
import os
import socket
import threading
import time
import uuid
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

LEASE_NAME = "background-engine"
LEASE_TTL = float(os.getenv("ENGINE_LEASE_TTL", "45") or 45)
RENEW_EVERY = float(os.getenv("ENGINE_LEASE_RENEW", "10") or 10)
DISABLED = os.getenv("ENGINE_LEASE_DISABLED", "").strip().lower() in {"1", "true", "yes", "on"}


class PgLeaseStore:
    """Stockage du bail dans PostgreSQL (acquisition atomique)."""

    def ensure_table(self) -> None:
        from database import get_connection

        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "CREATE TABLE IF NOT EXISTS engine_lease (name TEXT PRIMARY KEY, owner TEXT NOT NULL, "
                    "expires_at DOUBLE PRECISION NOT NULL)"
                )
            conn.commit()
        finally:
            conn.close()

    def acquire(self, owner: str, now: float, ttl: float) -> bool:
        from database import get_connection

        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO engine_lease (name, owner, expires_at) VALUES (%s, %s, %s) "
                    "ON CONFLICT (name) DO UPDATE SET owner = EXCLUDED.owner, expires_at = EXCLUDED.expires_at "
                    "WHERE engine_lease.owner = EXCLUDED.owner OR engine_lease.expires_at < %s "
                    "RETURNING owner",
                    (LEASE_NAME, owner, now + ttl, now),
                )
                row = cur.fetchone()
            conn.commit()
            return bool(row and row[0] == owner)
        finally:
            conn.close()

    def release(self, owner: str) -> None:
        from database import get_connection

        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE engine_lease SET expires_at = 0 WHERE name = %s AND owner = %s", (LEASE_NAME, owner))
            conn.commit()
        finally:
            conn.close()


class LeaseManager:
    def __init__(self, store: Any = None, ttl: float = LEASE_TTL, renew_every: float = RENEW_EVERY, clock: Callable[[], float] = time.time):
        self.store = store or PgLeaseStore()
        self.ttl = ttl
        self.renew_every = renew_every
        self.clock = clock
        self.owner = ""
        self.role = ""
        self.held_until = 0.0
        self.decided = threading.Event()  # vrai après la première tentative (réussie ou non)
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    # -- état -------------------------------------------------------------------------------------------------
    def held(self) -> bool:
        return DISABLED or self.clock() < self.held_until

    def tick(self) -> bool:
        """Une tentative d'acquisition / de renouvellement. Ne lève jamais."""
        had = self.held()
        try:
            ok = bool(self.store.acquire(self.owner, self.clock(), self.ttl))
        except Exception as exc:  # noqa: BLE001 (base injoignable : on laisse le bail expirer)
            logger.warning("bail moteur: acquisition impossible (%s) ; il expirera sans renouvellement", exc)
            ok = False
        if ok:
            self.held_until = self.clock() + self.ttl
            if not had:
                logger.info("bail moteur ACQUIS par %s : ce processus exécute les tâches de fond", self.owner)
        else:
            if had and self.clock() >= self.held_until:
                logger.warning("bail moteur PERDU par %s : tâches de fond suspendues dans ce processus", self.owner)
        self.decided.set()
        return ok

    # -- cycle de vie -----------------------------------------------------------------------------------------
    def start(self, role: str) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.role = role
        self.owner = f"{role}:{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        if DISABLED:
            self.decided.set()
            return
        try:
            self.store.ensure_table()
        except Exception as exc:  # noqa: BLE001
            logger.warning("bail moteur: création de la table impossible: %s", exc)
        self._stop.clear()

        def loop() -> None:
            while not self._stop.is_set():
                self.tick()
                self._stop.wait(self.renew_every)

        self._thread = threading.Thread(target=loop, name=f"engine-lease-{role}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive() and self._thread is not threading.current_thread():
            self._thread.join(timeout=3)
        try:
            if self.owner and not DISABLED:
                self.store.release(self.owner)
        except Exception:  # noqa: BLE001
            pass
        self.held_until = 0.0

    def wait_decision(self, timeout: float = 10.0) -> bool:
        """Attend la première tentative d'acquisition ; retourne True si le bail est tenu."""
        self.decided.wait(timeout)
        return self.held()


_manager = LeaseManager()


def start(role: str) -> None:
    _manager.start(role)


def stop() -> None:
    _manager.stop()


def lease_held() -> bool:
    return _manager.held()


def wait_decision(timeout: float = 10.0) -> bool:
    return _manager.wait_decision(timeout)


def leased(fn: Callable) -> Callable:
    """Décorateur : la tâche ne s'exécute que si ce processus détient le bail (sinon elle est ignorée en silence)."""
    if asyncio.iscoroutinefunction(fn):
        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            if not lease_held():
                return None
            return await fn(*args, **kwargs)

        return async_wrapper

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if not lease_held():
            return None
        return fn(*args, **kwargs)

    return wrapper
