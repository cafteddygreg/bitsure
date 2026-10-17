"""Optimization Lab : recherche de paramètres robustes sur le moteur de backtest RÉEL de Strategy Lab.

Aucune logique de trading n'est dupliquée ici : toutes les simulations passent par
`strategy_lab.run_backtest_experiment`. Ce package n'importe jamais `live_trader` ni `position_manager`
et ne modifie jamais la configuration de production (les paramètres testés sont injectés via `raw_params`).
"""

OPTIMIZATION_VERSION = "1.0.0"
