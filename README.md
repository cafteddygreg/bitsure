# 🧸 Bitsure Teddy v2.0 — Plateforme & Bot Telegram d'Analyse Quantitative, Paper Trading & AutoTrade Binance

**Bitsure Teddy v2.0** est un écosystème complet de trading algorithmique et d'analyse quantitative multi-actifs (**Crypto & Or / XAUUSD**). Il combine :
1. **Un Bot Telegram institutionnel (`main.py`)** avec menus interactifs, scanner multi-timeframes, Paper Trading, AutoTrade Binance (Spot & Futures USDT-M), Live Trading manuel, gestion du risque dynamique et interpréteur de logs IA (`/logs`).
2. **Une Plateforme Web Quantitative (`server.ts` + `web_api_server.py` + React/Vite)** connectée en temps réel au même moteur Python et à la même base de données (PostgreSQL en production / SQLite autonome en local).

---

## Table des Matières

1. [Architecture Globale du Projet](#-1-architecture-globale-du-projet)
2. [Actifs Officiels & Calibration Walk-Forward](#-2-actifs-officiels--calibration-walk-forward)
3. [Moteur d'Analyse Quantitative (`SignalEngine` & `Teddy Score`)](#-3-moteur-danalyse-quantitative-signalengine--teddy-score)
4. [AutoTrade Binance, Live Trading & Machine d'État Safe Mode](#-4-autotrade-binance-live-trading--machine-détat-safe-mode)
5. [Paper Trading Virtuel](#-5-paper-trading-virtuel)
6. [Variables d'Environnement (`.env` / Render / Railway)](#-6-variables-denvironnement-env--render--railway)
7. [Installation & Lancement (Local & Production)](#-7-installation--lancement-local--production)
8. [Catalogue Exhaustif des Commandes Telegram (Utilisateur & Admin)](#-8-catalogue-exhaustif-des-commandes-telegram-utilisateur--admin)
9. [Plateforme Web & API REST (`/api/*`)](#-9-plateforme-web--api-rest-api)
10. [Diagnostic IA (`/logs`), Watchdog & Sécurité](#-10-diagnostic-ia-logs-watchdog--sécurité)
11. [Tests Unitaires & Validation](#-11-tests-unitaires--validation)

---

## 🏗️ 1. Architecture Globale du Projet

Le dépôt est structuré autour d'un cœur analytique et transactionnel en **Python 3.11+** partagé entre le bot Telegram et le serveur Web :

```text
├── main.py                  # Point d'entrée principal du Bot Telegram (Polling / Webhook + Schedulers APScheduler)
├── config.py                # Configuration centralisée (Variables d'environnement, seuils Teddy Score, risques, quotas)
├── database.py              # Pool de connexions PostgreSQL (psycopg2) avec bascule automatique SQLite (bitsure_teddy.db)
├── sitecustomize.py         # Adaptateurs autonomes & compatibilité SQLite/PostgreSQL pour exécution sans friction
│
├── signal_engine.py         # Moteur quantitatif Teddy Score (0-100), alignement MTF, régimes de marché, SL/TP ATR
├── indicators.py            # Calculs vectorisés : RSI, MACD, Bandes de Bollinger, ATR, ADX (+DI/-DI), SMA 20/50/200, S/R, Fibonacci
├── data_fetcher.py          # Agrégateur multi-sources temps réel (WebSocket & REST Binance, Yahoo Finance, TwelveData)
├── market_hours.py          # Horaires d'ouverture Forex/Gold (24h/5j) vs Crypto (24h/7j)
│
├── execution_engine.py      # Pipeline AutoTrade : scan périodique, validation multi-filtres, sizing et envoi d'ordres
├── binance_manager.py       # Client Binance Spot & Futures USDT-M (Mainnet & Testnet), levier, marge, SL/TP natifs
├── position_manager.py      # Surveillance temps réel (15s), Trailing Stop dynamique, Break-Even et réconciliation (1m)
├── risk_manager.py          # Calcul de taille de position par % de risque, contrôle de perte max journalière et exposition
├── trading_safety.py        # Machine d'état de sécurité (NORMAL, CAUTION, SAFE_MODE, EMERGENCY_STOP) + Auto-downgrade TTL
├── trading_config.py        # Gestion persistante des paramètres AutoTrade par utilisateur (levier, style, whitelist, etc.)
├── security_manager.py      # Protection par code PIN à 6 chiffres (PBKDF2-HMAC-SHA256 + anti-bruteforce) et chiffrement clés API
├── decision_journal.py      # Journalisation d'audit complète de chaque décision d'exécution ou de rejet AutoTrade
│
├── paper_trader.py          # Moteur de Paper Trading ($10,000 initiaux, frais 0.10%, slippage 0.05%, levier x1-x10, SL/TP auto)
├── alert_manager.py         # Surveillance temps réel des alertes de prix (above / below)
├── history_manager.py       # Historique des signaux, suivi automatique des issues (WIN / LOSS / EXPIRED) et statistiques
├── user_manager.py          # Gestion des utilisateurs, rôles (tester, pro, vip, admin), quotas, watchlist et paiements
├── payments.py              # Génération de mémos de paiement Binance Pay (USDC/USDT) et intégration Telegram Stars
│
├── bot_handlers.py          # Handlers Telegram utilisateurs (analyse, menus, alertes, paper trading, abonnements)
├── trading_handlers.py      # Handlers Telegram AutoTrade (/autotrade, /config, /positions, /pnl, /setleverage, etc.)
├── live_handlers.py         # Handlers Telegram Live Trading manuel (/live, /live_long, /live_short, /live_close)
├── admin_handlers.py        # Handlers Telegram Administrateur (/stats, /teddy, /confirm_payment, /dbquery, /exportsignals)
├── bot_command_catalog.py   # Catalogue structuré de toutes les commandes avec rendu cliquable dans Telegram (/help)
│
├── health_monitor.py        # Watchdog système (vérification DB, WebSocket, Scheduler toutes les 60s)
├── log_doctor.py            # Tampon circulaire de logs en mémoire + Diagnostic local 0-token & Interpréteur Gemini IA (/logs)
│
├── web_api_server.py        # Serveur HTTP JSON (port 8001) exposant tout le moteur Python au frontend React
├── server.ts                # Serveur Express/Vite (port 3000) servant l'interface Web et proxyfiant /api/* vers 127.0.0.1:8001
└── src/                     # Interface Web React 19 + TypeScript + Tailwind CSS (Terminal Quantitatif & Console Admin)
```

---

## 🎯 2. Actifs Officiels & Calibration Walk-Forward

Pour garantir une **sélectivité institutionnelle** et éviter le sur-trading sur des paires peu liquides ou bruitées, Bitsure Teddy concentre ses analyses périodiques et son calibrage sur **3 instruments officiels** (`DOCUMENTED_SYMBOLS`) :

| Symbole | Classe d'Actif | Source Primaire | ADX Min | RSI Achat | RSI Vente | ATR Max (%) | Cond. Min |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **`BTCUSDT`** | Crypto (Futures/Spot) | Binance WS / REST | `22` | `48 – 66` | `34 – 52` | `4.5%` | `4 / 6` |
| **`ETHUSDT`** | Crypto (Futures/Spot) | Binance WS / REST | `22` | `48 – 66` | `34 – 52` | `4.8%` | `4 / 6` |
| **`XAUUSD`** | Matière Première (Or) | Yahoo (`GC=F`) / TwelveData | `22` | `48 – 66` | `34 – 52` | `2.5%` | `4 / 6` |

### Paramètres Calibrés par Défaut (`config.py`)
- **Score Teddy Minimum (`DEFAULT_MIN_SCORE`)** : `68 / 100` (calibré par validation walk-forward hors échantillon).
- **Stop-Loss ATR (`ATR_MULTIPLIER_SL`)** : `1.60 × ATR(14)` pour absorber le bruit intra-bougie sans élargir excessivement le risque.
- **Objectif Risk/Reward (`RR_RATIO_TARGET`)** : `2.10R` minimum (Take-Profit calibré à `3.36 × ATR(14)`).
- **Risque par Trade (`DEFAULT_RISK_PER_TRADE`)** : `1.0%` du capital.
- **Perte Journalière Maximale (`DEFAULT_MAX_DAILY_LOSS`)** : `3.0%` (coupe automatiquement la journée en cas de série défavorable).
- **Positions Simultanées Max (`DEFAULT_MAX_POSITIONS`)** : `2` positions max par défaut pour concentrer le capital sur les meilleurs setups.

---

## 🧠 3. Moteur d'Analyse Quantitative (`SignalEngine` & `Teddy Score`)

Chaque appel à `/analyse <symbole>` ou scan périodique exécute un pipeline déterministe en 7 étapes dans `signal_engine.py` :

1. **Vérification des Horaires de Marché (`market_hours.py`)** :
   - Les cryptomonnaies sont analysées 24h/24 et 7j/7.
   - L'Or (`XAUUSD`) et le Forex respectent la fermeture du week-end (vendredi 22h00 UTC à dimanche 22h00 UTC).
2. **Calcul des Indicateurs Techniques (`indicators.py`)** :
   - Moyennes mobiles simples **SMA 20, SMA 50, SMA 200**.
   - **RSI (14)** avec détection de pente et zones d'élan (momentum).
   - **MACD (12, 26, 9)** avec croisement ligne/signal et dynamique de l'histogramme.
   - **ADX (14)** avec **+DI / -DI** et détection d'accélération de tendance (`ADX rising`).
   - **ATR (14)** exprimé en valeur absolue et en pourcentage du prix (`ATR%`).
   - **Bandes de Bollinger (20, 2.0)**, **Supports / Résistances** locaux et niveaux de **Fibonacci** (`23.6%`, `38.2%`, `50.0%`, `61.8%`).
3. **Détection du Régime de Marché** :
   - Classification automatique : `STRONG_TREND`, `MODERATE_TREND`, `RANGING`, `HIGH_VOLATILITY` ou `LOW_VOLATILITY`.
4. **Confluence Multi-Critères (6 Conditions Techniques)** :
   - Alignement de tendance (Prix vs SMA50 & SMA200).
   - Zone de momentum RSI saine (sans surachat extrême à l'achat ni survente extrême à la vente).
   - Confirmation MACD (au-dessus/en-dessous du signal + histogramme).
   - Force directionnelle ADX (`ADX >= 22` et domination `+DI` / `-DI`).
   - Pullback ou structure de prix favorable par rapport à la SMA20 / Bandes de Bollinger.
   - Volatilité maîtrisée (`ATR%` sous le plafond de la classe d'actif).
5. **Alignement Multi-Timeframes (MTF)** :
   - Vérifie la cohérence de la tendance sur l'unité de temps supérieure (`TOTAL`, `PARTIAL`, ou `CONFLICT`).
6. **Calcul du `Teddy Score` (0 à 100%)** :
   - Pondère la tendance, le momentum, la force ADX, la qualité de la volatilité, le ratio Risk/Reward et le bonus/malus multi-timeframes.
7. **Décision Finale (`BUY`, `SELL` ou `WAIT`)** :
   - Si toutes les portes de validation passent, génère un signal actionnable avec **Prix d'entrée**, **Stop-Loss (SL)**, **Take-Profit (TP)**, **Ratio R:R** et **Niveau de Confiance**. Sinon, renvoie `WAIT` avec la raison exacte du rejet (ex: *ADX trop faible*, *Conflit MTF*, *ATR excessif*).

---

## 🤖 4. AutoTrade Binance, Live Trading & Machine d'État Safe Mode

### Modes d'Exécution
- **Binance Futures USDT-M (`futures`)** & **Binance Spot (`spot`)**.
- **Mode Testnet activé par défaut (`BINANCE_TESTNET = True`)** avec clés de démonstration pré-configurées pour permettre de tester immédiatement sans risque financier, ou d'enregistrer ses propres clés via `/setapikeys <api_key> <api_secret>`.
- **Chiffrement des clés API** : Les clés enregistrées par l'utilisateur sont chiffrées en base de données (`encrypted_api_keys`). En prime, le bot supprime automatiquement le message contenant la clé dans la conversation privée Telegram.

### Boucles Automatiques (`APScheduler` dans `main.py`)
- **`scheduled_signal_scan` (toutes les 20s)** : Évalue les signaux générés et déclenche l'exécution AutoTrade pour les comptes actifs.
- **`scheduled_market_analysis` (toutes les 5 ou 10 min)** : Scanne automatiquement les symboles documentés pour les utilisateurs ayant activé `/periodic_analysis on`.
- **`monitor_open_positions` (toutes les 15s)** : Surveille les positions ouvertes, met à jour le PnL latent, active le **Break-Even** et ajuste le **Trailing Stop** dynamique.
- **`reconcile_all_accounts` (toutes les 60s)** : Synchronise l'état de la base de données avec les ordres et positions réellement ouverts sur Binance.
- **`scheduled_health_check` (toutes les 60s)** : Vérifie la santé de la base de données, du scheduler et des flux de marché.

### Machine d'État de Sécurité (`trading_safety.py`)
Pour protéger le capital contre les anomalies de marché ou d'API, chaque compte dispose d'un état de sécurité indépendant :
- 🟢 **`NORMAL`** : Exécution automatique nominale.
- 🟡 **`CAUTION`** : Avertissement enregistré (ex: latence API passagère), surveillance accrue.
- 🔴 **`SAFE_MODE`** : Verrouillage préventif des nouvelles ouvertures (ex: perte max journalière atteinte, échecs d'ordres consécutifs). Déverrouillable via `/clearsafe <PIN>` ou auto-downgrade après expiration du TTL (`DEFAULT_SAFETY_LOCK_TTL_SECONDS = 3600s`).
- 🚨 **`EMERGENCY_STOP`** : Arrêt d'urgence déclenché par `/emergency_stop` — désactive l'AutoTrade et ferme immédiatement toutes les positions ouvertes au marché.

---

## 🧪 5. Paper Trading Virtuel

Accessible à tous les utilisateurs via `/paper` sur Telegram ou l'onglet **Paper Trading** sur le Web :
- **Capital initial** : `$10,000.00` (réinitialisable à tout moment avec `/paper reset`).
- **Simulation réaliste** : Intègre automatiquement les frais de transaction (`0.10%`) et le slippage d'exécution (`0.05%`).
- **Levier configurable** : Jusqu'à `x10` en simulation.
- **Clôture automatique** : Les positions virtuelles sont surveillées en arrière-plan et fermées automatiquement dès que le prix touche le **Stop-Loss (SL)** ou le **Take-Profit (TP)**.

---

## 🔑 6. Variables d'Environnement (`.env` / Render / Railway)

Toute la configuration métier est déjà codée et calibrée dans `config.py`. Vous n'avez besoin que de **3 variables principales** en production :

### Variables Principales (Obligatoires pour le Bot Telegram)
| Variable | Description | Exemple / Défaut |
| :--- | :--- | :--- |
| **`TELEGRAM_TOKEN`** | Token HTTP fourni par `@BotFather` sur Telegram. | `123456789:ABCdefGHIjklMNOpqrSTUvwxYZ` |
| **`ADMIN_ID`** | Votre ID numérique Telegram (obtenu via `/myid`) ou votre `@username`. | `@btsrteddy` ou `8176298717` |
| **`DATABASE_URL`** | URL de connexion PostgreSQL (Render, Supabase, Neon, Railway). *Si absente en local ou sur le Web, bascule automatiquement sur SQLite (`sqlite:///bitsure_teddy.db`).* | `postgresql://user:pass@host:5432/dbname` |

### Variables Optionnelles
| Variable | Description | Exemple / Défaut |
| :--- | :--- | :--- |
| **`TWELVEDATA_API_KEY`** | Clé API TwelveData (flux WebSocket/REST additionnel pour `XAUUSD` / Forex). | *(Vide par défaut, fallback Yahoo Finance)* |
| **`BINANCE_ID`** | Votre identifiant Binance Pay affiché aux utilisateurs lors d'un paiement `/pay_binance`. | `123456789` |
| **`GEMINI_API_KEY`** | Clé API Google Gemini pour enrichir la commande admin `/logs` avec une synthèse IA. *(Si vide, le moteur de diagnostic local fonctionne à 100% avec 0 token).* | `AIzaSy...` |
| **`GEMINI_LOG_MODEL`** | Modèle Gemini utilisé par `/logs`. | `gemini-3.1-flash-lite` |
| **`WEBHOOK_URL`** | URL publique HTTPS si vous souhaitez exécuter le bot en mode Webhook au lieu du mode Polling. | *(Vide = mode Polling automatique)* |
| **`PORT`** | Port d'écoute du Webhook Telegram (si `WEBHOOK_URL` est défini). | `8443` |
| **`PYTHON_API_PORT`** | Port interne du serveur API Python pour la plateforme Web. | `8001` |
| **`SECURITY_CODE_MAX_ATTEMPTS`** | Nombre maximal d'essais de code PIN avant verrouillage temporaire. | `5` |
| **`SECURITY_CODE_LOCK_SECONDS`** | Durée de verrouillage (en secondes) après dépassement des essais PIN. | `900` (15 min) |

---

## 🚀 7. Installation & Lancement (Local & Production)

### A. Lancer le Bot Telegram en Local
```bash
# 1. Installer les dépendances Python
pip install -r requirements.txt

# 2. Copier et configurer le fichier .env
cp .env.example .env
# Éditez .env et renseignez au minimum TELEGRAM_TOKEN et ADMIN_ID

# 3. Démarrer le bot Telegram
python3 main.py
```

### B. Lancer la Plateforme Web Complète (Frontend React + Backend Python)
Le serveur Node/Express (`server.ts`) démarre et supervise automatiquement le serveur Python (`web_api_server.py`) sur le port `8001` et expose l'application complète sur le port `3000` :
```bash
# 1. Installer les dépendances Node.js
npm install

# 2. Démarrer en mode développement (Port 3000)
npm run dev

# 3. Ou compiler et démarrer en mode production
npm run build
npm start
```

### C. Déploiement sur Render / Railway
1. Connectez votre dépôt GitHub à **Render** ou **Railway**.
2. Pour le **Worker Telegram**, utilisez la commande de démarrage :
   ```bash
   python main.py
   ```
   *(Le fichier `render.yaml` est préconfiguré avec `startCommand: python main.py`).*
3. Ajoutez vos variables d'environnement (`TELEGRAM_TOKEN`, `ADMIN_ID`, `DATABASE_URL`) dans l'onglet **Environment**.

---

## 📚 8. Catalogue Exhaustif des Commandes Telegram (Utilisateur & Admin)

Dans Telegram, toutes les commandes affichées par `/help` sont formatées pour être **directement cliquables**.

### 🚀 Général & Compte
- `/start` — Démarrer le bot, accepter les conditions et afficher l'état du compte.
- `/menu` — Ouvrir le menu principal interactif avec boutons inline.
- `/help` — Afficher l'aide complète paginée avec commandes cliquables.
- `/myid` — Afficher votre ID numérique Telegram (accessible même sans approbation préalable).
- `/status` — Vérifier l'état en temps réel des services du bot (Base de données, WebSocket, Scheduler, API).
- `/usage` — Consulter votre consommation journalière et les limites de votre rôle.
- `/upgrade` — Découvrir les offres PRO/VIP et souscrire (Telegram Stars ou Binance Pay).
- `/pay_binance` — Générer un mémo unique pour régler l'abonnement PRO via Binance Pay (USDC/USDT).
- `/historique` — Consulter vos 10 derniers signaux enregistrés et leurs résultats.
- `/support` — Contacter l'administrateur ou le support technique.

### 📊 Analyse Quantitative & Marché
- `/analyse <symbole>` — Analyse technique complète avec **Teddy Score**, confluence MTF, SL, TP et R:R (ex: `/analyse BTCUSDT` ou `/analyse XAUUSD`).
- `/price <symbole>` — Obtenir le cours en temps réel et la variation.
- `/trend <symbole>` — Analyse détaillée de la tendance court, moyen et long terme (SMA 20/50/200, ADX).
- `/volatility <symbole>` — Indicateurs de volatilité (ATR absolu, ATR%, largeur des Bandes de Bollinger).
- `/levels <symbole>` — Niveaux clés de marché (Supports, Résistances et retracements de Fibonacci).
- `/scan` — Lancer un scan instantané sur tous les symboles de votre Watchlist.

### 🔔 Alertes de Prix & Watchlist
- `/alert <symbole> <above|below> <prix>` — Créer une alerte de prix temps réel (ex: `/alert BTCUSDT above 90000`).
- `/alerts` — Lister toutes vos alertes actives.
- `/delalert <id>` — Supprimer une alerte par son identifiant.
- `/clearalerts` — Supprimer toutes vos alertes actives.
- `/watchlist` — Afficher votre liste de suivi personnalisée.
- `/addwatch <symbole>` — Ajouter un symbole à votre Watchlist.
- `/removewatch <symbole>` — Retirer un symbole de votre Watchlist.

### 🧪 Paper Trading (Portefeuille Virtuel)
- `/paper` — Ouvrir le menu interactif de sélection de symbole Paper Trading.
- `/paper status` — Afficher le bilan du portefeuille virtuel (Capital, PnL latent, positions ouvertes).
- `/paper buy <symbole>` — Ouvrir une position virtuelle LONG basée sur l'analyse courante.
- `/paper short <symbole>` — Ouvrir une position virtuelle SHORT basée sur l'analyse courante.
- `/paper close <symbole>` — Fermer manuellement une position virtuelle ouverte.
- `/paper history` — Consulter l'historique des trades virtuels clôturés.
- `/paper stats` — Afficher les statistiques de performance (Winrate, Profit Factor, PnL cumulé).
- `/paper reset` — Réinitialiser le portefeuille virtuel à `$10,000.00`.

### ⚙️ Paramètres & Code PIN de Sécurité
- `/settings` — Afficher vos préférences actuelles (Langue, Timeframe, Style, Risque).
- `/setsecurity <code_6_chiffres>` *(ou `/pin <code_6_chiffres>`)* — Créer ou modifier votre code PIN de sécurité à 6 chiffres.
- `/settimeframe <5m|15m|1h|4h|1d>` — Modifier votre unité de temps d'analyse par défaut.
- `/setstyle <scalping|day|swing|position>` — Modifier votre style de trading par défaut.
- `/setlanguage <fr|en>` — Basculer l'interface entre Français et Anglais.

### 🤖 AutoTrade Binance (Spot & Futures)
- `/setapikeys <api_key> <api_secret>` — Enregistrer et chiffrer vos clés API Binance (message auto-supprimé).
- `/autotrade` — Ouvrir le centre de contrôle interactif AutoTrade.
- `/autotrade on [PIN]` / `/autotrade off` — Activer ou désactiver l'exécution automatique des ordres.
- `/periodic_analysis on [5|10]` / `/periodic_analysis off` — Activer/désactiver le scanner automatique périodique (toutes les 5 ou 10 minutes).
- `/config` — Afficher le récapitulatif complet de votre configuration AutoTrade.
- `/account` *(alias `/balance`, `/solde`)* — Afficher le solde USDT disponible et l'état du compte Binance.
- `/positions` — Lister vos positions AutoTrade actuellement ouvertes avec PnL en direct.
- `/close <id> [PIN]` — Fermer immédiatement une position AutoTrade spécifique.
- `/pnl` — Afficher les statistiques PnL globales (jour, semaine, total).
- `/history_trades` — Consulter les 10 derniers trades réels exécutés.
- `/setleverage <1-125>` — Définir le levier sur Binance Futures.
- `/setrisk <pct>` — Définir le pourcentage du capital risqué par trade (ex: `1.0`).
- `/setmaxpos <1-10>` — Définir le nombre maximal de positions simultanées.
- `/setminscore <0-100>` — Définir le Teddy Score minimal requis pour autoriser un trade (défaut: `68`).
- `/setdailymaxloss <pct>` — Définir la perte maximale journalière autorisée en % (défaut: `3.0`).
- `/setmarket <spot|futures>` — Choisir le marché d'exécution Binance.
- `/settradingstyle <scalping|day|swing|position>` — Adapter les seuils d'analyse AutoTrade au style choisi.
- `/setanalysistf <5m|15m|1h|4h|1d>` — Choisir le timeframe du scanner AutoTrade.
- `/setanalysisinterval <5|10>` — Choisir la fréquence du scanner automatique en minutes.
- `/settrailing <on|off> [pct]` — Activer/désactiver le Trailing Stop dynamique.
- `/setcooldown <secondes>` — Définir le temps d'attente minimal entre deux trades sur le même actif.
- `/settestnet <on|off>` — Basculer entre Binance Testnet (simulation réelle sur serveur Binance) et Mainnet (argent réel).
- `/setdca <off|on> [steps] [step_pct]` — Configurer les paliers de Dollar-Cost Averaging (DCA).
- `/whitelist <add|remove|clear> [symbole]` — Restreindre l'AutoTrade à une liste blanche de symboles.
- `/blacklist <add|remove|clear> [symbole]` — Exclure des symboles spécifiques de l'AutoTrade.
- `/confirmmanual <token>` — Exécuter manuellement un signal proposé par `/analyse`.
- `/editsignal <id> <sl> <tp>` — Modifier le Stop-Loss et le Take-Profit d'un signal en attente.
- `/safestatus` — Consulter l'état du Safe Mode, les avertissements et la raison d'un éventuel verrouillage.
- `/clearsafe <PIN>` — Déverrouiller le Safe Mode à l'aide de votre code PIN à 6 chiffres.
- `/emergency_stop` — 🚨 **Arrêt d'urgence absolu** : coupe l'AutoTrade, annule les ordres ouverts et clôture toutes les positions.

### 🚨 Live Trading Manuel
- `/live` — Ouvrir le tableau de bord interactif Live Trading.
- `/live_long <symbole> <montant_usdt> <sl> <tp> [options]` — Préparer et valider un ordre réel LONG avec calcul de risque.
- `/live_short <symbole> <montant_usdt> <sl> <tp> [options]` — Préparer et valider un ordre réel SHORT.
- `/live_close <id>` — Fermer une position Live spécifique.
- `/live_cancel <symbole> <order_id>` — Annuler un ordre limite en attente sur Binance.

### 🛠️ Commandes Administrateur (Réservées à `ADMIN_ID` / `@btsrteddy`)
- `/teddy <user_id | @username> [pro]` *(alias `/adduser`, `/approve`)* — Approuver immédiatement un utilisateur comme **Testeur** ou activer directement son abonnement **PRO** (fonctionne même si l'utilisateur n'a pas encore démarré le bot grâce au pré-enregistrement par `@username`).
- `/confirm_payment <user_id | @username | memo>` — Confirmer manuellement un paiement Binance Pay et activer l'accès **PRO** avec notification automatique à l'utilisateur.
- `/find_memo <memo>` — Retrouver l'identifiant d'un utilisateur à partir de son code mémo Binance Pay.
- `/stats` — Afficher l'état de santé DB/Scheduler, le nombre total d'utilisateurs par rôle et l'activité détaillée de chaque compte.
- `/logs [question]` *(alias `/diag`)* — 🩺 Lancer un diagnostic complet des logs récents (analyse déterministe locale + explication IA Gemini si configurée).
- `/broadcast <message>` — Envoyer une annonce officielle à tous les utilisateurs inscrits.
- `/switchapi [binance|twelve|real]` — Inspecter ou basculer à chaud la source de données de marché primaire.
- `/trading_stats` — Afficher les statistiques globales d'exécution AutoTrade sur l'ensemble des comptes.
- `/trades` — Lister les derniers trades réels ouverts ou fermés sur le serveur.
- `/forceclose <trade_id>` — Forcer la clôture administrative immédiate d'une position.
- `/exportsignals` — Exporter l'intégralité de l'historique des signaux et résultats au format CSV directement dans Telegram.
- `/refreshhistory` — Forcer la vérification immédiate des issues (TP/SL touchés) sur tous les signaux ouverts.
- `/clearhistory` — Purger l'historique des signaux.
- `/cleanwaits` — Nettoyer les signaux `WAIT` en base de données.
- `/deleteuser <user_id>` — Supprimer un utilisateur et toutes ses données associées.
- `/dbquery <requête_SQL>` — Exécuter une requête SQL d'inspection directement sur la base de données.

---

## 🌐 9. Plateforme Web & API REST (`/api/*`)

L'interface Web (`src/`) offre un terminal visuel complet connecté au serveur Python (`web_api_server.py`) via les routes `/api/*` :

### Comptes de Démonstration Pré-configurés sur le Web
Lors du premier lancement, 4 profils sont automatiquement initialisés pour permettre de tester chaque niveau d'accréditation :
- **Administrateur** : `admin@bitsure.io` / Mot de passe : `teddy2026`
- **Trader PRO** : `pro@bitsure.io` / Mot de passe : `teddy2026`
- **Institutionnel VIP** : `vip@bitsure.io` / Mot de passe : `teddy2026`
- **Analyste Testeur** : `tester@bitsure.io` / Mot de passe : `teddy2026`

### Principales Routes API (`web_api_server.py`)
- `POST /api/auth/login` | `POST /api/auth/register` | `GET /api/auth/me` — Authentification et session utilisateur.
- `GET /api/market/overview` | `POST /api/market/analyse` | `GET /api/market/scan` — Prix en direct, graphiques OHLCV, calcul du Teddy Score, niveaux S/R, Fibonacci, tendance et volatilité.
- `GET /api/paper/state` | `POST /api/paper/open` | `POST /api/paper/close` | `POST /api/paper/reset` — Gestion complète du portefeuille Paper Trading.
- `GET /api/autotrade/state` | `POST /api/autotrade/config` | `POST /api/autotrade/toggle` | `POST /api/autotrade/keys` — Configuration AutoTrade, clés Binance, sécurité PIN, déverrouillage Safe Mode et journal de décisions.
- `POST /api/live/order` | `POST /api/live/close` — Passage d'ordres manuels Live et fermeture de positions.
- `GET /api/alerts` | `POST /api/alerts` | `DELETE /api/alerts` — Création et suppression d'alertes de prix et gestion de la Watchlist.
- `GET /api/signals/history` — Historique complet des signaux et métriques de performance.
- `GET /api/admin/overview` | `POST /api/admin/approve` | `POST /api/admin/confirm-payment` | `POST /api/admin/dbquery` | `GET /api/admin/logs` — Console d'administration Web complète.

---

## 🩺 10. Diagnostic IA (`/logs`), Watchdog & Sécurité

- **Tampon de Logs Circulaire (`log_doctor.py`)** : Capture en temps réel tous les événements `INFO`, `WARNING` et `ERROR` en mémoire sans saturer le disque.
- **Moteur de Diagnostic Hybride** :
  - **Mode Local (0 Token)** : Détecte automatiquement les erreurs PostgreSQL, les déconnexions WebSocket, les rejets d'ordres Binance (marge insuffisante, filtre `LOT_SIZE`, décalage horaire `timestamp`) et fournit immédiatement la marche à suivre en français ou en anglais.
  - **Mode IA Gemini (Optionnel)** : Si `GEMINI_API_KEY` est défini, synthétise les journaux complexes et répond aux questions libres posées via `/logs <votre question>`.
- **Sécurité Critique** :
  - Hachage des codes PIN avec **PBKDF2-HMAC-SHA256** (120 000 itérations + sel aléatoire de 16 octets) et verrouillage anti-bruteforce.
  - Protection des actions sensibles (`/autotrade on`, `/clearsafe`, `/close`) par vérification du code PIN.

---

## ✅ 11. Tests Unitaires & Validation

Le projet inclut une suite de tests automatisés dans le dossier `tests/` couvrant l'approbation des utilisateurs, les commandes administrateur, le catalogue `/help`, le moteur AutoTrade, la sécurité et l'interpréteur de logs :

```bash
# Exécuter l'ensemble de la suite de tests unitaires Python
PYTHONPATH=. python3 -m unittest discover -s tests -v

# Vérifier la compilation TypeScript / Vite de la plateforme Web
npm run build
```
