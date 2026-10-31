# Indépendance du site vis-à-vis du bot Telegram

Le site (API web + interface) fonctionne **sans le bot**, et le bot fonctionne sans le site. Les deux peuvent tourner
ensemble sans jamais exécuter les mêmes tâches en double.

## Ce qui a changé

| Sujet | Avant | Maintenant |
|---|---|---|
| Tâches de fond (scan des signaux, suivi SL/TP, sorties Paper, réconciliation Binance) | uniquement dans le bot (le site ne les lançait qu'avec `AUTOTRADE_EMBEDDED=1`) | le site les héberge **par défaut** ; `AUTOTRADE_EMBEDDED=0` pour désactiver |
| Alertes de prix créées sur le site | ne se déclenchaient que si le bot tournait | surveillées par le site aussi |
| Résultats gagné/perdu des signaux | suivis seulement par le bot | suivis par le site aussi |
| Éviter les doublons | heartbeat approximatif | **bail en base** (`engine_lease.py`) : un seul processus travaille, l'autre prend le relais en ≤ 45 s s'il tombe |
| Notifications | Telegram uniquement (rien pour les comptes du site sans Telegram) | boîte de réception du site (🔔) pour **tous** les comptes + Telegram en canal supplémentaire |
| `TELEGRAM_TOKEN` absent | `python main.py` quitte, le site tombe avec | le site continue seul |
| Le bot plante (réseau Telegram, conflit de polling) | le processus s'arrête, le site avec | le site continue, son moteur reprend les tâches de fond |
| Messages d'erreur | « Utilise /setapikeys », « /clearsafe »… | indiquent aussi où le faire sur le site |

## Modes de déploiement (tous compatibles)

1. **Un seul processus** : `python main.py` (bot + site). Variable `BOT_EXIT_ON_FAILURE=1` pour retrouver l'ancien
   comportement (quitter si le bot échoue, pour qu'un superviseur relance tout).
2. **Site seul** : `python web_api_server.py` (ou `node server.ts` sans `START_TELEGRAM_BOT`). Aucun token Telegram requis.
3. **Séparés** : site avec `python web_api_server.py`, bot avec `DISABLE_EMBEDDED_WEB=1 python main.py`.

Le moteur de fond tourne dans le **site** (délai de grâce de 45 s) tant qu'aucun bot n'en exécute un, puis le premier qui
obtient le bail travaille. Tester : arrêter le bot → le site continue ; arrêter le site → le bot continue.

## Variables

- `AUTOTRADE_EMBEDDED` (défaut `1`) : le site héberge son moteur de fond.
- `ENGINE_LEASE_TTL` (45 s) / `ENGINE_LEASE_RENEW` (10 s) : durée et renouvellement du bail.
- `ENGINE_LEASE_DISABLED=1` : désactive le bail (déconseillé : risque de doublons si site et bot tournent ensemble).
- `BOT_EXIT_ON_FAILURE=1` : quitter si le bot échoue.

## Ce qui dépend encore de Telegram (par nature)

- Les boutons de **confirmation manuelle** d'un ordre envoyés dans Telegram (clavier inline) : sans bot, il n'y a personne
  pour traiter le clic. Utiliser le mode automatique, ou confirmer depuis le site.
- Le **rapport hebdomadaire** envoyé dans Telegram.
- Le **paiement par Telegram Stars** (le paiement par mémo Binance fonctionne depuis le site).
- Les notifications poussées vers le téléphone : sans bot, elles restent visibles dans la cloche du site.

## Surveillance

L'onglet admin « Santé & sécurité » affiche « Moteur de fond actif » et indique qui l'exécute (site ou bot).
