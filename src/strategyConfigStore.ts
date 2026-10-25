/**
 * Store global de la configuration de stratégie — « Source de Vérité » de l'application.
 *
 * Le Strategy Lab écrit ici via `updateGlobalStrategyConfig` (Valider Raw Config / Sauvegarder Preset).
 * L'Optimization Lab (et tout autre composant) lit ici via `useGlobalStrategyConfig`.
 *
 * Aucune dépendance : store externe + `useSyncExternalStore` (React 18/19).
 * Persistance : localStorage, avec synchronisation entre onglets du navigateur (événement `storage`).
 */
import { useSyncExternalStore } from 'react';

export type StrategyConfigSource = 'raw_config' | 'preset' | 'editor' | 'manual';

export interface GlobalStrategyConfig {
  /** Paramètres au format clé → valeur (ex. { allow_long: false, min_rr_ratio: 1.5 }). */
  params: Record<string, any>;
  /** Style de trading pour lequel cette config a été définie (les params dépendent du style). */
  tradingStyle: string;
  symbol?: string;
  timeframe?: string;
  /** Nom du preset si la config provient d'une sauvegarde de preset. */
  presetName?: string;
  source: StrategyConfigSource;
  /** Epoch ms de la dernière mise à jour. */
  updatedAt: number;
}

export const STRATEGY_CONFIG_STORAGE_KEY = 'bitsure.globalStrategyConfig.v1';

const isPlainObject = (v: unknown): v is Record<string, any> =>
  typeof v === 'object' && v !== null && !Array.isArray(v);

function readFromStorage(): GlobalStrategyConfig | null {
  try {
    const raw = window.localStorage.getItem(STRATEGY_CONFIG_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!isPlainObject(parsed) || !isPlainObject(parsed.params) || typeof parsed.tradingStyle !== 'string') return null;
    return parsed as GlobalStrategyConfig;
  } catch {
    // localStorage indisponible (mode privé, quota) ou JSON corrompu : on repart sans config globale.
    return null;
  }
}

function writeToStorage(cfg: GlobalStrategyConfig | null): void {
  try {
    if (cfg === null) window.localStorage.removeItem(STRATEGY_CONFIG_STORAGE_KEY);
    else window.localStorage.setItem(STRATEGY_CONFIG_STORAGE_KEY, JSON.stringify(cfg));
  } catch {
    /* quota / mode privé : l'état mémoire reste valide pour la session */
  }
}

// Hydratation synchrone au chargement du module → l'état est déjà correct au premier rendu (pas de flash).
let state: GlobalStrategyConfig | null = typeof window !== 'undefined' ? readFromStorage() : null;
const listeners = new Set<() => void>();

const emit = () => listeners.forEach((l) => l());

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

const getSnapshot = () => state; // référence stable tant que rien ne change (exigé par useSyncExternalStore)

// Synchronisation multi-onglets : si un autre onglet met à jour la config, on suit.
if (typeof window !== 'undefined') {
  window.addEventListener('storage', (e) => {
    if (e.key !== STRATEGY_CONFIG_STORAGE_KEY) return;
    state = readFromStorage();
    emit();
  });
}

/**
 * Définit la configuration active comme Source de Vérité (état global + localStorage).
 * À appeler après « Valider Raw Config » réussi et après « Sauvegarder Preset » réussi.
 */
export function updateGlobalStrategyConfig(
  params: Record<string, any>,
  meta: Omit<Partial<GlobalStrategyConfig>, 'params' | 'updatedAt'> & { tradingStyle: string }
): GlobalStrategyConfig {
  const next: GlobalStrategyConfig = {
    source: 'manual',
    ...meta,
    params: { ...params }, // copie : on ne garde jamais une référence vers l'état React du Lab
    updatedAt: Date.now(),
  };
  state = next;
  writeToStorage(next);
  emit();
  return next;
}

/** Lecture ponctuelle hors composant React. */
export function getGlobalStrategyConfig(): GlobalStrategyConfig | null {
  return state;
}

/** Réinitialise la config globale (retour au preset officiel dans l'Optimization Lab). */
export function clearGlobalStrategyConfig(): void {
  state = null;
  writeToStorage(null);
  emit();
}

/** Hook : renvoie la config globale et re-rend le composant à chaque mise à jour. */
export function useGlobalStrategyConfig(): GlobalStrategyConfig | null {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}
