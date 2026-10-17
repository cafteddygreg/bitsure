"""Point d'entrée du service Railway « Optimization Worker » (même repository que le service web).

    python optimization_worker.py            # boucle infinie (service)
    python optimization_worker.py --once     # traite les jobs en attente puis quitte

Nécessite DATABASE_URL (PostgreSQL partagé avec le service web). TELEGRAM_TOKEN est optionnel (notifications).
Ce processus ne démarre ni le bot, ni le serveur web, ni aucun module d'exécution live.
"""
import argparse
import logging
import signal
import sys
import threading


def main() -> int:
    parser = argparse.ArgumentParser(description="Bitsure Optimization Worker")
    parser.add_argument("--once", action="store_true", help="traite les jobs en attente puis quitte")
    parser.add_argument("--poll", type=float, default=5.0, help="intervalle de polling (secondes)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    stop = threading.Event()

    def _stop(signum, _frame):
        logging.getLogger("optimization.worker").info("Signal %s : arrêt propre après le calcul en cours", signum)
        stop.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    from optimization.worker import worker_loop
    n = worker_loop(stop_event=stop, poll_interval=args.poll, once=args.once)
    logging.getLogger("optimization.worker").info("Worker arrêté (%d job(s) traité(s))", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
