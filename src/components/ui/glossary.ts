/**
 * Glossaire des métriques affichées dans l'interface.
 * Chaque définition est alignée sur le comportement réel du code Python
 * (backtest/performance.py, strategy_lab.py, optimization/*.py, signal_engine.py).
 * Ne pas modifier une définition sans vérifier le calcul correspondant.
 */
export type GlossaryKey =
  | 'adx'
  | 'rsi'
  | 'atr'
  | 'teddy_score'
  | 'profit_factor'
  | 'sharpe'
  | 'sortino'
  | 'calmar'
  | 'max_drawdown'
  | 'expectancy'
  | 'rr'
  | 'training'
  | 'validation'
  | 'oos'
  | 'robustness'
  | 'sensitivity'
  | 'neighbors'
  | 'monte_carlo'
  | 'overfit';

interface Entry {
  term: string;
  fr: string;
  en: string;
}

export const GLOSSARY: Record<GlossaryKey, Entry> = {
  adx: {
    term: 'ADX',
    fr: "Average Directional Index (14). Mesure la force d'une tendance, pas sa direction ; +DI / -DI donnent le sens dominant. Le bot exige un ADX minimum (22 par défaut sur les symboles documentés).",
    en: "Average Directional Index (14). Measures trend strength, not direction; +DI / -DI give the dominant side. The bot requires a minimum ADX (22 by default on documented symbols).",
  },
  rsi: {
    term: 'RSI',
    fr: "Relative Strength Index (14). Oscillateur de momentum de 0 à 100. Le bot l'utilise pour éviter les achats en surachat extrême et les ventes en survente extrême.",
    en: 'Relative Strength Index (14). Momentum oscillator from 0 to 100. The bot uses it to avoid buying at extreme overbought and selling at extreme oversold levels.',
  },
  atr: {
    term: 'ATR',
    fr: "Average True Range (14). Amplitude moyenne des bougies, exprimée en prix ou en % du prix. Sert de mesure de volatilité et de base de calcul du Stop-Loss et du Take-Profit.",
    en: 'Average True Range (14). Average candle range, in price or as % of price. Used as a volatility measure and as the basis for Stop-Loss and Take-Profit distances.',
  },
  teddy_score: {
    term: 'Teddy Score',
    fr: "Score de 0 à 100 calculé par le SignalEngine. Il pondère tendance, momentum, force ADX, qualité de la volatilité, ratio Risk/Reward et bonus/malus de l'alignement multi-timeframes. Un signal n'est actionnable que s'il dépasse le score minimum configuré.",
    en: 'Score from 0 to 100 computed by the SignalEngine. It weighs trend, momentum, ADX strength, volatility quality, Risk/Reward and the multi-timeframe alignment bonus/penalty. A signal is only actionable above the configured minimum score.',
  },
  profit_factor: {
    term: 'Profit Factor',
    fr: 'Profit brut divisé par la perte brute. Au-dessus de 1, les gains dépassent les pertes. Non défini (N/A) s’il n’y a aucune perte.',
    en: 'Gross profit divided by gross loss. Above 1, gross profits exceed gross losses. Not defined (N/A) when there is no loss.',
  },
  sharpe: {
    term: 'Sharpe Ratio',
    fr: "Moyenne des rendements de la courbe d'équité divisée par leur écart-type, annualisée selon le timeframe. Plus il est élevé, plus le rendement est régulier par unité de volatilité.",
    en: 'Mean of the equity-curve returns divided by their standard deviation, annualised from the timeframe. Higher means steadier returns per unit of volatility.',
  },
  sortino: {
    term: 'Sortino Ratio',
    fr: "Comme le Sharpe, mais le dénominateur ne retient que la volatilité à la baisse (cible 0). Il ne pénalise pas les fortes hausses.",
    en: 'Like Sharpe, but the denominator only counts downside volatility (target 0). It does not penalise large gains.',
  },
  calmar: {
    term: 'Calmar Ratio',
    fr: 'Rendement total divisé par le drawdown maximum. Mesure ce que rapporte la stratégie par point de drawdown subi.',
    en: 'Total return divided by maximum drawdown. Measures return earned per point of drawdown endured.',
  },
  max_drawdown: {
    term: 'Max Drawdown',
    fr: "Plus forte baisse de l'équité depuis un sommet précédent, en %. Valeur négative : -8,7 % signifie une baisse maximale de 8,7 % depuis un pic.",
    en: 'Largest equity decline from a previous peak, in %. Negative value: -8.7% means a maximum 8.7% drop from a peak.',
  },
  expectancy: {
    term: 'Expectancy',
    fr: 'Gain net moyen par trade (en USDT). La version en R exprime ce gain en multiples du risque initial pris sur chaque trade.',
    en: 'Average net gain per trade (in USDT). The R version expresses it as a multiple of the initial risk taken on each trade.',
  },
  rr: {
    term: 'Risk / Reward (RR)',
    fr: 'Distance jusqu’au Take-Profit divisée par la distance jusqu’au Stop-Loss. RR 2,0 : le gain visé vaut deux fois le risque pris.',
    en: 'Distance to Take-Profit divided by distance to Stop-Loss. RR 2.0: the target gain is twice the risk taken.',
  },
  training: {
    term: 'Training',
    fr: "Premières 60 % de la période simulée. Toutes les configurations y sont testées.",
    en: 'First 60% of the simulated period. Every configuration is tested on it.',
  },
  validation: {
    term: 'Validation',
    fr: "20 % suivants de la période. Seules les meilleures configurations du training y passent ; ce résultat sert à la sélection.",
    en: 'Next 20% of the period. Only the best training configurations run on it; this result is used for selection.',
  },
  oos: {
    term: 'OOS (Out-of-Sample)',
    fr: "Derniers 20 % de la période. Jamais utilisés pour choisir une configuration : ils servent uniquement à détecter le surapprentissage.",
    en: 'Last 20% of the period. Never used to pick a configuration: only used to detect overfitting.',
  },
  robustness: {
    term: 'Robustesse',
    fr: "Score de 0 à 100 : 45 % stabilité des configurations voisines, 35 % cohérence training/validation, 20 % facteur de risque (drawdown et nombre de trades).",
    en: 'Score from 0 to 100: 45% neighbour stability, 35% training/validation consistency, 20% risk factor (drawdown and trade count).',
  },
  sensitivity: {
    term: 'Sensibilité',
    fr: "Score training moyen pour chaque valeur d'un paramètre, avec l'amplitude entre valeurs. Une grande amplitude indique un paramètre qui change fortement le résultat.",
    en: 'Mean training score for each value of a parameter, with the spread between values. A large spread means the parameter strongly changes the result.',
  },
  neighbors: {
    term: 'Voisins',
    fr: "Performance des 6 configurations les plus proches dans l'espace des paramètres normalisé. Une bonne configuration entourée de voisines faibles est un pic isolé.",
    en: 'Performance of the 6 closest configurations in normalised parameter space. A good configuration surrounded by weak neighbours is an isolated peak.',
  },
  monte_carlo: {
    term: 'Monte Carlo',
    fr: "Rééchantillonnage avec remise des P&L réels des trades (1 000 simulations) pour estimer la distribution du rendement final et du drawdown. Nécessite au moins 10 trades.",
    en: 'Resampling with replacement of the real trade P&Ls (1,000 simulations) to estimate the distribution of final return and drawdown. Requires at least 10 trades.',
  },
  overfit: {
    term: 'Surapprentissage',
    fr: "Une configuration trop adaptée aux données passées. Signalé quand les résultats chutent en validation ou en OOS, ou quand le meilleur score est un pic isolé.",
    en: 'A configuration too tuned to past data. Flagged when results drop in validation or OOS, or when the best score is an isolated peak.',
  },
};
