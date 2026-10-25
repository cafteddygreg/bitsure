/**
 * Symbols that are visible but temporarily unavailable in the UI.
 * Every click/selection on one of them shows a message instead of acting on it.
 * To re-enable a symbol, remove it from this set (single place).
 */
export const UNAVAILABLE_SYMBOLS: ReadonlySet<string> = new Set(['XAUUSDT']);

export const isSymbolUnavailable = (symbol: string | null | undefined): boolean =>
  UNAVAILABLE_SYMBOLS.has(String(symbol || '').toUpperCase());

export const unavailableSymbolMessage = (lang: string | undefined, symbol: string): string =>
  lang === 'en' ? `${symbol} is not available for now.` : `${symbol} n'est pas disponible pour le moment.`;

export const unavailableSuffix = (lang: string | undefined, symbol: string): string =>
  isSymbolUnavailable(symbol) ? (lang === 'en' ? ' — unavailable' : ' — indisponible') : '';
