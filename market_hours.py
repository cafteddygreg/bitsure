"""
market_hours.py — Bitsure Teddy
Bloque les signaux hors des heures de trading liquides.
"""

from datetime import datetime, timezone


def is_market_open(symbol: str) -> bool:
    """
    Retourne True si le marché est ouvert et liquide pour le symbole donné.
    Tous les symboles Binance (crypto et or) sont disponibles 24/7.
    """
    return True
