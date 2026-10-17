"""Espace de recherche : paramètres optimisables, génération des configurations (grid / random), comptage."""
from __future__ import annotations

import inspect
import json
import math
import random
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import strategy_lab as sl

# Les paramètres du modèle « capital » (capital, taille de position, levier, frais, slippage, limites de risque
# opérationnelles) ne sont PAS des décisions de stratégie : on ne les optimise pas (risk management inchangé).
NON_OPTIMIZABLE_MODELS = {"capital"}

MAX_PARAMS = 8
MAX_VALUES_PER_PARAM = 60
MAX_CONFIGS_HARD = 5000      # au-delà : refus explicite (jamais de réduction silencieuse)
WARN_CONFIGS = 400           # au-delà : avertissement de durée
DEFAULT_RANDOM_CONFIGS = 200
SUPPORTED_METHODS = ("grid", "random")

# Un paramètre n'a d'effet que si son interrupteur/mode est actif dans la configuration de base.
PARAM_DEPENDENCIES: Dict[str, Tuple[str, Any]] = {
    "sl_atr_mult": ("sl_mode", "atr"),
    "sl_fixed_pct": ("sl_mode", "fixed_pct"),
    "tp_atr_mult": ("tp_mode", "atr"),
    "tp_fixed_pct": ("tp_mode", "fixed_pct"),
    "partial_tp_rr": ("partial_tp_enabled", True),
    "partial_tp_close_pct": ("partial_tp_enabled", True),
    "breakeven_trigger_rr": ("breakeven_enabled", True),
    "trailing_activation_rr": ("trailing_stop_enabled", True),
    "trailing_distance_atr": ("trailing_stop_enabled", True),
}


class SpaceError(ValueError):
    """Requête d'optimisation invalide (message destiné à l'utilisateur)."""


@lru_cache(maxsize=1)
def consumed_param_keys() -> frozenset:
    """Paramètres de LAB_PARAM_SPECS réellement lus par le moteur (détection sur le code source actuel)."""
    src = "\n".join(
        inspect.getsource(fn)
        for fn in (sl._compute_lab_indicators, sl._evaluate_candle_signal, sl.run_backtest_experiment)
    )
    return frozenset(k for k in sl.LAB_PARAM_SPECS if re.search(r"""["']%s["']""" % re.escape(k), src))


def _suggest_step(spec: Dict[str, Any]) -> Optional[float]:
    lo, hi = spec.get("min"), spec.get("max")
    if spec["type"] not in ("int", "float") or lo is None or hi is None:
        return None
    raw = (hi - lo) / 40.0
    if spec["type"] == "int":
        return float(max(1, round(raw)))
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 0.1
    for m in (1, 2, 5, 10):
        if raw <= m * mag:
            return round(m * mag, 6)
    return round(raw, 6)


def get_optimizable_parameters(style: str = "day") -> List[Dict[str, Any]]:
    """Catalogue des paramètres optimisables + valeur actuelle (preset officiel du style)."""
    base = sl.normalize_lab_params({}, style=style)
    used = consumed_param_keys()
    out: List[Dict[str, Any]] = []
    for key, spec in sl.LAB_PARAM_SPECS.items():
        if spec.get("model") in NON_OPTIMIZABLE_MODELS or key not in used:
            continue
        entry = {
            "key": key,
            "type": spec["type"],
            "model": spec.get("model"),
            "min": spec.get("min"),
            "max": spec.get("max"),
            "choices": spec.get("choices"),
            "unit": spec.get("unit", ""),
            "label_fr": spec.get("label_fr", key),
            "label_en": spec.get("label_en", key),
            "current": base.get(key),
            "suggested_step": _suggest_step(spec),
        }
        dep = PARAM_DEPENDENCIES.get(key)
        if dep:
            entry["active_when"] = {"param": dep[0], "equals": dep[1]}
        out.append(entry)
    return out


def _clean_values(key: str, raw_values: List[Any]) -> List[Any]:
    out: List[Any] = []
    seen = set()
    for raw in raw_values:
        ok, val, err = sl._coerce_strict_param_value(key, raw)
        if not ok:
            raise SpaceError(err or f"Valeur invalide pour {key}: {raw!r}")
        marker = json.dumps(val)
        if marker not in seen:
            seen.add(marker)
            out.append(val)
    return out


def expand_param_values(req: Dict[str, Any]) -> List[Any]:
    """Valeurs candidates d'un paramètre (liste explicite OU min/max/step). Aucune valeur n'est clampée."""
    key = str(req.get("key") or "").strip()
    if key not in sl.LAB_PARAM_SPECS:
        raise SpaceError(f"Paramètre inconnu : {key!r}.")
    spec = sl.LAB_PARAM_SPECS[key]
    if spec.get("model") in NON_OPTIMIZABLE_MODELS:
        raise SpaceError(f"Le paramètre « {key} » (capital/risque/frais) ne peut pas être optimisé.")
    if key not in consumed_param_keys():
        raise SpaceError(f"Le paramètre « {key} » n'est pas utilisé par le moteur actuel : non optimisable.")

    ptype = spec["type"]
    explicit = req.get("values")
    if isinstance(explicit, list) and explicit:
        values = _clean_values(key, explicit)
    elif ptype == "bool":
        values = [True, False]
    elif ptype == "enum":
        values = list(spec.get("choices") or [])
    else:
        try:
            lo, hi, step = float(req["min"]), float(req["max"]), float(req["step"])
        except (KeyError, TypeError, ValueError):
            raise SpaceError(f"« {key} » : indiquez min, max et step (ou une liste de valeurs).")
        if step <= 0 or hi < lo:
            raise SpaceError(f"« {key} » : step doit être > 0 et max ≥ min.")
        n = int(math.floor((hi - lo) / step + 1e-9)) + 1
        if n > MAX_VALUES_PER_PARAM:
            raise SpaceError(
                f"« {key} » génère {n} valeurs (maximum {MAX_VALUES_PER_PARAM}) : augmentez le step ou réduisez la plage."
            )
        raw_vals = [lo + i * step for i in range(n)]
        if ptype == "int":
            if any(abs(v - round(v)) > 1e-9 for v in raw_vals):
                raise SpaceError(f"« {key} » est un entier : min et step doivent être entiers.")
            raw_vals = [int(round(v)) for v in raw_vals]
        else:
            raw_vals = [round(v, 6) for v in raw_vals]
        values = _clean_values(key, raw_vals)
    if len(values) > MAX_VALUES_PER_PARAM:
        raise SpaceError(f"« {key} » : {len(values)} valeurs (maximum {MAX_VALUES_PER_PARAM}).")
    if len(values) < 2:
        raise SpaceError(f"« {key} » : au moins 2 valeurs candidates sont nécessaires pour optimiser.")
    return values


def _decode(index: int, sizes: List[int]) -> List[int]:
    """Index global -> indices par paramètre (base mixte, dernier paramètre = poids faible)."""
    out = [0] * len(sizes)
    for pos in range(len(sizes) - 1, -1, -1):
        index, out[pos] = divmod(index, sizes[pos])
    return out


def config_is_valid(params: Dict[str, Any]) -> bool:
    """Contraintes de cohérence déjà imposées par Strategy Lab (cf. run_parameter_sweep)."""
    try:
        if int(params["sma_fast"]) >= int(params["sma_slow"]):
            return False
        if float(params["rsi_oversold"]) >= float(params["rsi_overbought"]):
            return False
    except (KeyError, TypeError, ValueError):
        return False
    return True


def build_search_space(
    param_requests: List[Dict[str, Any]],
    base_params: Optional[Dict[str, Any]] = None,
    trading_style: str = "day",
    method: str = "grid",
    max_configs: Optional[int] = None,
    seed: int = 42,
) -> Dict[str, Any]:
    """Construit le plan d'optimisation. Lève SpaceError si la demande est invalide ou trop grande."""
    method = (method or "grid").lower()
    if method not in SUPPORTED_METHODS:
        raise SpaceError(f"Méthode inconnue : {method!r} (grid ou random).")
    if not isinstance(param_requests, list) or not param_requests:
        raise SpaceError("Sélectionnez au moins un paramètre à optimiser.")
    if len(param_requests) > MAX_PARAMS:
        raise SpaceError(f"Maximum {MAX_PARAMS} paramètres simultanés.")
    keys = [str(r.get("key") or "").strip() for r in param_requests]
    if len(set(keys)) != len(keys):
        raise SpaceError("Un paramètre est sélectionné plusieurs fois.")

    base = sl.normalize_lab_params(base_params or {}, style=trading_style)
    parameters = [{"key": r.get("key"), "values": expand_param_values(r)} for r in param_requests]
    for p in parameters:
        p["key"] = str(p["key"]).strip()
    sizes = [len(p["values"]) for p in parameters]
    total_grid = 1
    for s in sizes:
        total_grid *= s

    warnings: List[str] = []
    for p in parameters:
        dep = PARAM_DEPENDENCIES.get(p["key"])
        if dep and base.get(dep[0]) != dep[1]:
            warnings.append(
                f"« {p['key']} » n'a aucun effet tant que {dep[0]} ≠ {dep[1]!r} dans la configuration de base : "
                "ses valeurs donneront des résultats identiques."
            )

    def make(index: int) -> Optional[Dict[str, Any]]:
        picks = _decode(index, sizes)
        override = {parameters[i]["key"]: parameters[i]["values"][picks[i]] for i in range(len(parameters))}
        merged = dict(base)
        merged.update(override)
        return override if config_is_valid(merged) else None

    configs: List[Dict[str, Any]] = []
    invalid = 0
    if method == "grid":
        if total_grid > MAX_CONFIGS_HARD:
            raise SpaceError(
                f"Grid Search : {total_grid} combinaisons (limite {MAX_CONFIGS_HARD}). "
                "Réduisez les plages, augmentez les steps, ou utilisez Random Search."
            )
        if max_configs and total_grid > int(max_configs):
            raise SpaceError(
                f"Grid Search : {total_grid} combinaisons dépassent votre maximum de {int(max_configs)}. "
                "Aucune réduction silencieuse n'est appliquée : ajustez la demande ou passez en Random Search."
            )
        for idx in range(total_grid):
            ov = make(idx)
            if ov is None:
                invalid += 1
            else:
                configs.append(ov)
    else:
        target = int(max_configs or DEFAULT_RANDOM_CONFIGS)
        if target < 1 or target > MAX_CONFIGS_HARD:
            raise SpaceError(f"Random Search : max_configs doit être entre 1 et {MAX_CONFIGS_HARD}.")
        rng = random.Random(int(seed))
        pool = list(range(total_grid)) if total_grid <= 200_000 else None
        if pool is not None:
            rng.shuffle(pool)
            order: Any = pool
        else:
            order = (rng.randrange(total_grid) for _ in range(target * 20))
        seen = set()
        for idx in order:
            if len(configs) >= target:
                break
            if idx in seen:
                continue
            seen.add(idx)
            ov = make(idx)
            if ov is None:
                invalid += 1
            else:
                configs.append(ov)
        if total_grid < target:
            warnings.append(f"L'espace ne contient que {total_grid} combinaisons : toutes sont testées.")

    if not configs:
        raise SpaceError("Aucune configuration valide (contraintes SMA/RSI incohérentes pour toutes les combinaisons).")
    if invalid:
        warnings.append(f"{invalid} combinaison(s) écartée(s) car incohérente(s) (SMA rapide ≥ lente ou RSI survente ≥ surachat).")
    if len(configs) > WARN_CONFIGS:
        warnings.append(f"{len(configs)} configurations : l'optimisation peut durer longtemps (traitée en arrière-plan).")

    return {
        "method": method,
        "seed": int(seed),
        "parameters": parameters,
        "total_grid": total_grid,
        "n_configs": len(configs),
        "invalid_skipped": invalid,
        "configs": configs,
        "warnings": warnings,
        "base_params": base,
    }
