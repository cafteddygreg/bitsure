"""Boucle du worker d'optimisation (processus indépendant du web : `python optimization_worker.py`)."""
from __future__ import annotations

import logging
import os
import socket
import threading
import time
import uuid
from typing import Optional

from . import store
from .engine import run_job
from .notify import TelegramJobNotifier

logger = logging.getLogger("optimization.worker")


def make_worker_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"


def worker_loop(
    stop_event: Optional[threading.Event] = None,
    poll_interval: float = 5.0,
    once: bool = False,
    db=None,
    notifier=None,
    loader=None,
    only_job: Optional[str] = None,
) -> int:
    """Traite les jobs en attente (et reprend ceux dont le worker a disparu). Retourne le nombre de jobs traités."""
    stop_event = stop_event or threading.Event()
    notifier = notifier if notifier is not None else TelegramJobNotifier()
    worker_id = make_worker_id()
    store.ensure_schema(db)
    processed = 0
    logger.info("Optimization Worker démarré (%s)", worker_id)
    while not stop_event.is_set():
        try:
            job_id = store.claim_next_job(worker_id, db=db)
        except Exception as exc:
            logger.error("claim_next_job a échoué: %s", exc)
            job_id = None
            if once:
                raise
        if only_job and job_id and job_id != only_job:
            store.release_job(job_id, worker_id, db=db)
            job_id = None
        if job_id:
            logger.info("Job réservé : %s", job_id)
            status = run_job(job_id, worker_id, db=db, notifier=notifier, loader=loader, stop_flag=stop_event.is_set)
            logger.info("Job %s terminé avec le statut : %s", job_id, status)
            processed += 1
            continue
        if once:
            break
        stop_event.wait(poll_interval)
    return processed
