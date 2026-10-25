# Bitsure — Cartographie UI (état audité avant refonte)

Source de vérité : `src/App.tsx` (shell + 10 onglets), `src/components/*`, `web_api_server.py` (API).
Stack : React 19 + TypeScript + Tailwind 4 (Vite), icônes lucide-react, pas de lib de graphiques (SVG maison).

## Shell
| Zone | Où | Contenu |
|---|---|---|
| Sidebar desktop | `App.tsx` ~2495 | `navItems` (10 entrées), sélecteur « Marchés Documentés » (10 cryptos + XAU « indisponible » : message à chaque clic via `symbolAvailability.ts`, + prix live), profil/quota, Présentation, Quitter |
| Header desktop | ~2677 | symbole, timeframes 5m→1d, style (scalping…position), Actualiser, ticker live WS, Paper equity/PnL, Utilisateurs 360° (admin), CGU, langue FR/EN |
| Mobile | ~2895 / ~6718 | barre basse de 4–5 « hubs » + barre de sous-onglets (`mobileHubGroups`) |
| Feedback | ~2930 | toast + actions en cours (`pendingActions` / `isPending`) |
| Modale PIN | ~6758 | confirmation PIN (enable_autotrade, execute_live_order, clearsafe) |

## Onglets (`ActiveTab`) → fonctionnalités
| id | Libellé actuel | Contenu | API principales |
|---|---|---|---|
| `intelligence` | Market Intelligence | KPI (prix, signal/Teddy Score, MTF, sizing), graphique, indicateurs, explicabilité SL/TP/RR, ticket paper rapide, multi-scan | `/api/market/tickers`, analyse + multi-scan |
| `paper` | Paper Trading | positions ouvertes, historique fermé, ouvrir/fermer/reset | `/api/paper/overview|open|close|reset` |
| `alerts` | Alertes & Watchlist | alertes prix (ajout/suppression/clear) | `/api/alerts*` |
| `safety` | Auto-Trade & Safety | état safety, config AutoTrade (marché, style, analyse périodique, levier, risque, max positions, min score, perte jour, cooldown, trailing, DCA, whitelist/blacklist), clés Binance, compte live, ordre live manuel, positions/ordres Binance | `/api/trading/*` |
| `strategy_lab` | Strategy Lab (Backtest) | sous-onglets : setup, params, raw, ai, overview, chart, trades, diagnostics, compare (A/B), sweep, **optimization (Optimization Lab)**, history | `/api/admin/strategy-lab/*`, `/api/admin/strategy-lab/optimization/*` |
| `history` | Historique & Journal | historique signaux, journal de décisions | `/api/signals/history` |
| `account` | Compte, Plans & PIN | plans, promo, Binance Pay, PIN, support | `/api/user/*`, `/api/support/tickets` |
| `terms` | CGU | `TermsOfUsePage` | `/api/user/accept-terms` |
| `users_intelligence` | Utilisateurs 360° (admin) | `AdminUsersIntelligenceTab` | `/api/admin/users-intelligence` |
| `admin` | Admin & Log Doctor | users/rôles/quotas, audit sécurité, broadcast, log doctor, stats AutoTrade globales, memo/paiements, maintenance signaux, SQL inspector | `/api/admin/*` |

## Écarts avec la taxonomie cible (OVERVIEW / RESEARCH / TRADING / MONITORING / SYSTEM)
- Pas de routes séparées Signals/Scanner/Analysis : tout est dans `intelligence`.
- Positions/Orders/Live Trading/AutoTrade sont tous dans `safety` (un seul onglet très long).
- Optimization Lab n'est accessible que via un sous-onglet de Strategy Lab (découvrabilité faible).
- Binance (clés) est dans `safety`, Subscription dans `account`.
- Mobile : la barre basse « cycle » entre sous-onglets au tap répété (peu découvrable).

## Règles de la refonte
Aucune route/onglet/API supprimé. Regroupement de la navigation = présentation uniquement (mêmes `ActiveTab`).

## Avancement de la refonte (session de reprise)
- Strategy Lab : 5 phases (Configuration / Stratégie / Backtest / Comparaison / Interprétation) au-dessus des onglets existants ; aucun onglet retiré. Zoom de période + toucher sur la courbe d'équité ; comparateur A/B avec superposition des équités et liste des paramètres différents ; encadré « Interprétation » (règles déterministes sur les métriques du run).
- Optimization Lab : comparaison côte à côte référence vs meilleures configurations (training/validation/OOS, robustesse, surapprentissage, paramètres différents) ; panneau Monte Carlo (données `details[idx].monte_carlo_all`).
- Tableaux mobiles : classe `bs-stack` + `components/ui/stackTables.ts` (étiquettes de colonnes) → cartes sous 768 px ; historique Paper en cartes dédiées.
- Non fait : distinction toast « requête envoyée » / « opération terminée » (dépend du backend), vérification visuelle (aucun build/navigateur disponible dans cet environnement).
- Après build : `python scripts/gen_frontend_bundle.py` régénère `web_frontend_bundle_data.py`.
