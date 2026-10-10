import React, { useState } from "react";
import {
  Shield,
  ArrowLeft,
  CheckCircle2,
  AlertTriangle,
  Lock,
  Globe,
  Cpu,
  Database,
  Activity,
  FileText,
  Scale,
  Eye,
  Server,
} from "lucide-react";

interface TermsOfUsePageProps {
  onBack: () => void;
  onAcceptAndReturnToRegister?: () => void;
  showAcceptButton?: boolean;
  isAccepted?: boolean;
}

export const TERMS_VERSION = "2.2.0";

export function TermsOfUsePage({
  onBack,
  onAcceptAndReturnToRegister,
  showAcceptButton = false,
  isAccepted = false,
}: TermsOfUsePageProps) {
  const [activeSection, setActiveSection] = useState<string>("all");

  const sections = [
    { id: "all", label: "Contrat complet (Intégral)" },
    { id: "service", label: "1–3. Objet, Risques & Compte" },
    { id: "privacy", label: "4–6. Données Personnelles, IP, Appareil & Localisation" },
    { id: "sensitive", label: "7–9. Données Sensibles, Clés API & Audit Admin" },
    { id: "rights", label: "10–12. Droits, Responsabilité & Juridiction" },
  ];

  const showSection = (group: string) => activeSection === "all" || activeSection === group;

  return (
    <div className="min-h-screen bg-[#070A12] text-slate-100 flex flex-col">
      {/* Sticky Header */}
      <header className="sticky top-0 z-30 border-b border-slate-800/80 bg-[#0B101D]/95 backdrop-blur-md">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <button
              onClick={onBack}
              className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-700/80 text-slate-200 text-xs font-semibold transition"
            >
              <ArrowLeft className="w-4 h-4 text-amber-400" />
              Retour
            </button>
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-lg bg-amber-500/10 border border-amber-500/30 flex items-center justify-center">
                <Scale className="w-5 h-5 text-amber-400" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h1 className="text-sm sm:text-base font-bold text-white tracking-tight">
                    BITSURE — Termes, Conditions Générales d&apos;Utilisation &amp; Charte de Collecte des Données
                  </h1>
                  <span className="px-2 py-0.5 text-[10px] font-mono font-semibold uppercase rounded bg-amber-500/15 text-amber-300 border border-amber-500/30">
                    v{TERMS_VERSION}
                  </span>
                </div>
                <p className="text-[11px] text-slate-400">
                  Document contractuel public applicable au Bot Telegram Bitsure, au Terminal Web et aux API d&apos;Exécution
                </p>
              </div>
            </div>
          </div>

          {showAcceptButton && onAcceptAndReturnToRegister && (
            <button
              onClick={onAcceptAndReturnToRegister}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs transition shadow-lg shadow-amber-500/10"
            >
              <CheckCircle2 className="w-4 h-4" />
              {isAccepted
                ? "Termes déjà acceptés — Revenir à l'inscription"
                : "J'ai lu et j'accepte ces Termes — Continuer l'inscription"}
            </button>
          )}
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 max-w-6xl w-full mx-auto px-4 sm:px-6 py-8 space-y-6">
        {/* Executive Disclosure Banner */}
        <div className="rounded-xl border border-amber-500/35 bg-gradient-to-br from-amber-500/10 via-slate-900/90 to-slate-950 p-5 sm:p-6 shadow-xl">
          <div className="flex items-start gap-3.5">
            <AlertTriangle className="w-6 h-6 text-amber-400 shrink-0 mt-0.5" />
            <div className="space-y-2">
              <div className="text-xs font-mono uppercase tracking-wider text-amber-300 font-semibold">
                Avis de transparence intégrale &amp; Consentement préalable obligatoire à la création de compte
              </div>
              <p className="text-xs sm:text-sm text-slate-200 leading-relaxed">
                En créant un compte sur <strong>Bitsure</strong> (plateforme Web ou Bot Telegram), en cochant la case{" "}
                <span className="text-amber-300 font-semibold">
                  « J&apos;ai lu et j&apos;accepte les termes et conditions d&apos;utilisation »
                </span>{" "}
                et en accédant à nos services, vous concluez un contrat juridiquement contraignant et vous{" "}
                <strong>
                  autorisez expressément la plateforme Bitsure et son Administrateur à collecter, enregistrer, analyser et
                  consulter l&apos;intégralité de vos données personnelles, techniques, financières, comportementales et
                  sensibles liées à votre utilisation du service
                </strong>
                , telles que détaillées de manière exhaustive ci-dessous.
              </p>
            </div>
          </div>

          {/* Quick summary cards of what is collected */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mt-5">
            <div className="p-3.5 rounded-lg bg-slate-950/80 border border-slate-800/90 space-y-1">
              <div className="flex items-center gap-2 text-amber-400 text-xs font-bold">
                <Eye className="w-4 h-4" /> Identité &amp; Compte
              </div>
              <p className="text-[11px] text-slate-400 leading-relaxed">
                Email, nom d&apos;affichage, pseudonyme Telegram, User ID, rôle, abonnement, codes promo, statut KYC/accès et
                horodatage d&apos;acceptation des CGU.
              </p>
            </div>
            <div className="p-3.5 rounded-lg bg-slate-950/80 border border-slate-800/90 space-y-1">
              <div className="flex items-center gap-2 text-sky-400 text-xs font-bold">
                <Globe className="w-4 h-4" /> Adresse IP &amp; Localisation
              </div>
              <p className="text-[11px] text-slate-400 leading-relaxed">
                Adresse IP publique, historique complet des IP, fournisseur d&apos;accès (FAI/ISP), pays, région, ville,
                fuseau horaire et coordonnées GPS (si autorisées).
              </p>
            </div>
            <div className="p-3.5 rounded-lg bg-slate-950/80 border border-slate-800/90 space-y-1">
              <div className="flex items-center gap-2 text-emerald-400 text-xs font-bold">
                <Cpu className="w-4 h-4" /> Appareil &amp; Empreinte Matérielle
              </div>
              <p className="text-[11px] text-slate-400 leading-relaxed">
                Type d&apos;appareil (Mobile/Desktop), modèle exact, OS, navigateur, User-Agent, écran, processeur (CPU
                cores), RAM, batterie et réseau.
              </p>
            </div>
            <div className="p-3.5 rounded-lg bg-slate-950/80 border border-slate-800/90 space-y-1">
              <div className="flex items-center gap-2 text-rose-400 text-xs font-bold">
                <Database className="w-4 h-4" /> Données Sensibles &amp; Trading
              </div>
              <p className="text-[11px] text-slate-400 leading-relaxed">
                Clés API/Secret Binance (stockées chiffrées AES-128), empreintes PIN/mot de passe, ordres Live &amp; Paper,
                PnL, paiements, alertes et journaux de sécurité.
              </p>
            </div>
          </div>
        </div>

        {/* Filter Navigation */}
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-800 pb-3">
          {sections.map((s) => (
            <button
              key={s.id}
              onClick={() => setActiveSection(s.id)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition border ${
                activeSection === s.id
                  ? "bg-amber-500/20 text-amber-300 border-amber-500/40"
                  : "bg-slate-900/80 text-slate-400 border-slate-800 hover:text-slate-200"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>

        {/* Articles Container */}
        <div className="space-y-5">
          {showSection("service") && (
            <>
              <section className="rounded-xl border border-slate-800/90 bg-[#0C1220] p-5 sm:p-6 space-y-3">
                <div className="flex items-center gap-2.5 text-amber-400 font-bold text-sm">
                  <FileText className="w-4 h-4" />
                  <h2>ARTICLE 1 — OBJET DU CONTRAT ET DESCRIPTION DU SERVICE BITSURE</h2>
                </div>
                <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                  <strong>1.1.</strong> La plateforme <strong>Bitsure</strong> (incluant l&apos;interface Web, le serveur API,
                  le moteur quantitatif <em>Teddy Score</em>, le laboratoire de backtest <em>Strategy Lab</em> et le bot
                  Telegram officiel) fournit des outils d&apos;analyse technique algorithmique, de simulation de portefeuille
                  (<em>Paper Trading</em>) et d&apos;exécution automatisée ou semi-automatisée d&apos;ordres sur les marchés de
                  crypto-actifs et métaux précieux (notamment via l&apos;API Binance).
                </p>
                <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                  <strong>1.2.</strong> L&apos;accès à la plateforme est strictement subordonné à la lecture intégrale et à
                  l&apos;acceptation sans réserve des présents Termes et Conditions d&apos;Utilisation lors de la dernière
                  étape de création du compte. Aucune inscription ne peut être finalisée sans cette acceptation explicite.
                </p>
              </section>

              <section className="rounded-xl border border-slate-800/90 bg-[#0C1220] p-5 sm:p-6 space-y-3">
                <div className="flex items-center gap-2.5 text-amber-400 font-bold text-sm">
                  <AlertTriangle className="w-4 h-4" />
                  <h2>ARTICLE 2 — AVERTISSEMENT SUR LES RISQUES FINANCIERS ET ABSENCE DE CONSEIL EN INVESTISSEMENT</h2>
                </div>
                <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                  <strong>2.1. Nature purement technologique et statistique :</strong> Les signaux (<em>BUY / SELL / WAIT</em>),
                  les scores multi-facteurs (<em>Teddy Score 0–100</em>), les niveaux de <em>Stop-Loss (SL)</em> et{" "}
                  <em>Take-Profit (TP1/TP2)</em> ainsi que les résultats de backtest ne constituent en aucun cas un conseil
                  financier, juridique, fiscal ou une recommandation personnalisée d&apos;investissement.
                </p>
                <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                  <strong>2.2. Risque de perte en capital :</strong> Le trading de crypto-monnaies (BTC, ETH, SOL, etc.) et de
                  contrats avec effet de levier comporte un risque élevé de perte rapide et totale du capital investi. Les
                  performances passées ou simulées en Paper Trading / Strategy Lab ne préjugent jamais des performances futures
                  en conditions réelles de marché. L&apos;Utilisateur agit sous son entière et unique responsabilité.
                </p>
              </section>

              <section className="rounded-xl border border-slate-800/90 bg-[#0C1220] p-5 sm:p-6 space-y-3">
                <div className="flex items-center gap-2.5 text-amber-400 font-bold text-sm">
                  <Shield className="w-4 h-4" />
                  <h2>ARTICLE 3 — CRÉATION DE COMPTE, VÉRIFICATION ET VALIDATION PAR L&apos;ADMINISTRATEUR</h2>
                </div>
                <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                  <strong>3.1. Approbation manuelle :</strong> Tout nouveau compte créé sur Bitsure est initialisé avec le
                  statut <code className="text-amber-300 font-mono">PENDING_APPROVAL</code>. L&apos;Administrateur dispose d&apos;un
                  droit discrétionnaire d&apos;approuver, de refuser, de suspendre ou de révoquer tout compte utilisateur à
                  tout moment, sur la base des informations de sécurité et de profil collectées.
                </p>
                <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                  <strong>3.2. Exactitude des informations :</strong> L&apos;Utilisateur s&apos;engage à fournir une adresse
                  email valide et vérifiable, un identifiant Telegram réel (le cas échéant) et à ne pas usurper l&apos;identité
                  d&apos;un tiers ni utiliser de dispositifs visant à falsifier frauduleusement son identité lors de
                  l&apos;audit de sécurité.
                </p>
              </section>
            </>
          )}

          {showSection("privacy") && (
            <>
              <section className="rounded-xl border border-sky-500/30 bg-[#0C1220] p-5 sm:p-6 space-y-3">
                <div className="flex items-center gap-2.5 text-sky-400 font-bold text-sm">
                  <Eye className="w-4 h-4" />
                  <h2>
                    ARTICLE 4 — COLLECTE EXHAUSTIVE DES DONNÉES PERSONNELLES ET D&apos;IDENTITÉ (CONSENTEMENT EXPLICITE)
                  </h2>
                </div>
                <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                  En acceptant les présents Termes et Conditions lors de la création de votre compte, vous autorisez
                  expressément Bitsure à collecter, stocker en base de données et afficher dans le panneau d&apos;administration
                  les données personnelles suivantes :
                </p>
                <ul className="list-disc pl-5 space-y-1.5 text-xs sm:text-sm text-slate-300">
                  <li>
                    <strong>Identifiants personnels :</strong> Adresse email complète, nom d&apos;affichage (Display Name),
                    pseudonyme Telegram (<code className="text-sky-300 font-mono">@username</code>), identifiant numérique
                    unique (<code className="text-sky-300 font-mono">user_id</code>) et identifiant Google OAuth (
                    <code className="text-sky-300 font-mono">google_sub</code>) en cas de connexion via Google.
                  </li>
                  <li>
                    <strong>Données de preuve contractuelle :</strong> Statut d&apos;acceptation des CGU, version exacte du
                    contrat accepté (<code className="text-sky-300 font-mono">v{TERMS_VERSION}</code>), date et heure exactes
                    d&apos;acceptation à la seconde près, et adresse IP utilisée au moment de la signature électronique.
                  </li>
                  <li>
                    <strong>Données commerciales et d&apos;abonnement :</strong> Plan tarifaire actif (Free, Pro, VIP), date
                    d&apos;expiration, codes promotionnels utilisés, mémos de paiement Binance Pay, historique des transactions
                    Telegram Stars et demandes de support client.
                  </li>
                </ul>
              </section>

              <section className="rounded-xl border border-sky-500/30 bg-[#0C1220] p-5 sm:p-6 space-y-3">
                <div className="flex items-center gap-2.5 text-sky-400 font-bold text-sm">
                  <Globe className="w-4 h-4" />
                  <h2>ARTICLE 5 — COLLECTE DE L&apos;ADRESSE IP, DU RÉSEAU ET DE LA LOCALISATION GÉOGRAPHIQUE</h2>
                </div>
                <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                  Pour garantir la sécurité de la plateforme, prévenir les accès non autorisés, respecter les restrictions
                  géographiques réglementaires et permettre la supervision par l&apos;Administrateur, l&apos;Utilisateur
                  consent expressément à la collecte automatique et continue :
                </p>
                <ul className="list-disc pl-5 space-y-1.5 text-xs sm:text-sm text-slate-300">
                  <li>
                    <strong>Adresses IP et historique réseau :</strong> L&apos;adresse IP publique lors de l&apos;inscription,
                    de chaque connexion et de chaque requête sensible, ainsi que l&apos;historique complet des adresses IP
                    utilisées par le compte (<code className="text-sky-300 font-mono">ip_history</code>), le fournisseur
                    d&apos;accès Internet (FAI / ISP / ASN) et le type de connexion réseau (4G/5G/Wi-Fi, bande passante
                    estimée).
                  </li>
                  <li>
                    <strong>Localisation géographique par IP et fuseau horaire :</strong> Le pays, la région/état, la ville
                    estimée via les en-têtes réseau et le fuseau horaire système du terminal de l&apos;Utilisateur (ex.{" "}
                    <code className="text-sky-300 font-mono">Europe/Paris</code>).
                  </li>
                  <li>
                    <strong>Géolocalisation GPS précise (avec permission du navigateur) :</strong> Lorsque l&apos;Utilisateur
                    accorde la permission de localisation à son navigateur ou appareil, Bitsure collecte et enregistre les
                    coordonnées exactes de <strong>latitude</strong>, <strong>longitude</strong> et le{" "}
                    <strong>rayon de précision en mètres</strong>. L&apos;Utilisateur peut accepter ou refuser l&apos;invite de
                    permission GPS du navigateur ; en cas de refus du GPS, la localisation réseau (IP + fuseau horaire) reste
                    collectée conformément au présent contrat.
                  </li>
                </ul>
              </section>

              <section className="rounded-xl border border-sky-500/30 bg-[#0C1220] p-5 sm:p-6 space-y-3">
                <div className="flex items-center gap-2.5 text-sky-400 font-bold text-sm">
                  <Cpu className="w-4 h-4" />
                  <h2>ARTICLE 6 — COLLECTE DES INFORMATIONS SUR L&apos;APPAREIL ET L&apos;EMPREINTE MATÉRIELLE (TELEMETRY)</h2>
                </div>
                <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                  À chaque session (inscription, connexion et utilisation active du terminal), Bitsure relève automatiquement
                  les caractéristiques techniques de l&apos;appareil de l&apos;Utilisateur :
                </p>
                <ul className="list-disc pl-5 space-y-1.5 text-xs sm:text-sm text-slate-300">
                  <li>
                    <strong>Catégorie et modèle d&apos;appareil :</strong> Type de terminal (Smartphone Mobile, Tablette,
                    Ordinateur Desktop), marque et modèle matériel détecté (ex. Apple iPhone, Mac, Samsung Galaxy, PC Windows,
                    Linux).
                  </li>
                  <li>
                    <strong>Système d&apos;exploitation et Navigateur :</strong> Nom et version exacte de l&apos;OS (iOS,
                    Android, macOS, Windows, Linux), nom et version du navigateur (Chrome, Safari, Firefox, Edge), chaîne{" "}
                    <code className="text-sky-300 font-mono">User-Agent</code> intégrale et plateforme matérielle.
                  </li>
                  <li>
                    <strong>Caractéristiques matérielles et écran :</strong> Résolution physique de l&apos;écran, taille de la
                    fenêtre d&apos;affichage (Viewport), ratio de pixels (<code className="text-sky-300 font-mono">devicePixelRatio</code>
                    ), profondeur de couleur, nombre de cœurs logiques du processeur (<code className="text-sky-300 font-mono">hardwareConcurrency</code>
                    ), mémoire vive estimée (<code className="text-sky-300 font-mono">deviceMemory</code> en Go), nombre de
                    points tactiles (<code className="text-sky-300 font-mono">maxTouchPoints</code>), niveau et état de charge
                    de la batterie (si supporté par le navigateur), langues configurées, état des cookies et URL de provenance
                    (Referrer).
                  </li>
                </ul>
              </section>
            </>
          )}

          {showSection("sensitive") && (
            <>
              <section className="rounded-xl border border-rose-500/30 bg-[#0C1220] p-5 sm:p-6 space-y-3">
                <div className="flex items-center gap-2.5 text-rose-400 font-bold text-sm">
                  <Lock className="w-4 h-4" />
                  <h2>
                    ARTICLE 7 — COLLECTE ET TRAITEMENT DES INFORMATIONS SENSIBLES, FINANCIÈRES ET DE TRADING
                  </h2>
                </div>
                <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                  Dans le cadre des fonctionnalités avancées de trading (Paper Trading et Live Trading Binance) et de sécurité
                  du compte, l&apos;Utilisateur reconnaît et accepte que les informations sensibles suivantes soient enregistrées
                  et auditées :
                </p>
                <ul className="list-disc pl-5 space-y-1.5 text-xs sm:text-sm text-slate-300">
                  <li>
                    <strong>Clés API et Clés Secrètes Binance :</strong> Lorsque l&apos;Utilisateur connecte son compte
                    Binance pour le trading réel, sa clé API (<code className="text-rose-300 font-mono">api_key</code>) et sa
                    clé secrète (<code className="text-rose-300 font-mono">api_secret</code>) sont chiffrées via{" "}
                    <strong>Fernet AES-128-CBC + HMAC-SHA256</strong> avant stockage en base de données, accompagnées de la
                    date de liaison, du mode (Testnet ou Live Production) et de l&apos;empreinte de la clé.
                  </li>
                  <li>
                    <strong>Données d&apos;authentification et de sécurité :</strong> Empreinte cryptographique du mot de
                    passe (<code className="text-rose-300 font-mono">PBKDF2-HMAC-SHA256</code>), statut et empreinte du code
                    PIN de sécurité à 6 chiffres, nombre de tentatives échouées, horodatage de verrouillage anti-bruteforce,
                    jetons de session actifs et jetons CSRF.
                  </li>
                  <li>
                    <strong>Intégralité de l&apos;activité financière et de trading :</strong> Capital Paper Trading,
                    positions ouvertes et fermées, historique complet des ordres Live Binance (prix d&apos;entrée, prix de
                    sortie, quantité, levier, Stop-Loss, Take-Profit, identifiant d&apos;ordre Binance, PnL réalisé et latent,
                    erreurs d&apos;exécution), paramètres de risque (risque par trade, perte journalière maximale, levier max,
                    style de trading), watchlist, alertes de prix et historique de toutes les analyses demandées.
                  </li>
                </ul>
              </section>

              <section className="rounded-xl border border-rose-500/30 bg-[#0C1220] p-5 sm:p-6 space-y-3">
                <div className="flex items-center gap-2.5 text-rose-400 font-bold text-sm">
                  <Server className="w-4 h-4" />
                  <h2>ARTICLE 8 — ACCÈS DE L&apos;ADMINISTRATEUR AU DOSSIER UTILISATEUR 360°</h2>
                </div>
                <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                  <strong>8.1. Visibilité administrative complète :</strong> L&apos;Utilisateur est expressément informé et
                  accepte sans réserve que <strong>l&apos;Administrateur de Bitsure</strong> dispose d&apos;un onglet dédié de
                  supervision (<em>Dossier Utilisateur 360° / User Intelligence</em>) regroupant, pour chaque compte créé :
                  l&apos;identité complète, le statut et la preuve de consentement aux CGU, l&apos;adresse IP actuelle et
                  l&apos;historique des IP, la localisation géographique (pays, ville, coordonnées GPS si autorisées), le type
                  et modèle d&apos;appareil, le système d&apos;exploitation, le navigateur, les caractéristiques matérielles,
                  l&apos;état des clés API et codes de sécurité, les sessions actives, le journal des événements de sécurité,
                  ainsi que l&apos;intégralité des portefeuilles et historiques de trading Paper et Live.
                </p>
                <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                  <strong>8.2. Finalités de cet accès :</strong> Cet accès administratif est utilisé pour : (a) vérifier et
                  approuver les demandes d&apos;ouverture de compte ; (b) détecter les partages de compte, les attaques par
                  force brute ou les connexions suspectes ; (c) fournir un support technique et diagnostiquer les erreurs
                  d&apos;exécution d&apos;ordres ou d&apos;affichage sur l&apos;appareil de l&apos;Utilisateur ; (d) assurer la
                  conformité contractuelle et la sécurité globale de l&apos;infrastructure Bitsure.
                </p>
              </section>

              <section className="rounded-xl border border-rose-500/30 bg-[#0C1220] p-5 sm:p-6 space-y-3">
                <div className="flex items-center gap-2.5 text-rose-400 font-bold text-sm">
                  <Activity className="w-4 h-4" />
                  <h2>ARTICLE 9 — SÉCURITÉ, JOURNALISATION DES ÉVÉNEMENTS ET COUPE-CIRCUIT (SAFE MODE)</h2>
                </div>
                <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                  Toutes les actions critiques (création de compte, connexion, échec de mot de passe ou de PIN, liaison de clé
                  API Binance, activation/désactivation de l&apos;Auto-Trade, déclenchement du Safe Mode ou dépassement de
                  quota) font l&apos;objet d&apos;un enregistrement horodaté inaltérable dans la table{" "}
                  <code className="text-rose-300 font-mono">security_events</code> avec l&apos;adresse IP et les détails de
                  l&apos;opération.
                </p>
              </section>
            </>
          )}

          {showSection("rights") && (
            <>
              <section className="rounded-xl border border-slate-800/90 bg-[#0C1220] p-5 sm:p-6 space-y-3">
                <div className="flex items-center gap-2.5 text-emerald-400 font-bold text-sm">
                  <CheckCircle2 className="w-4 h-4" />
                  <h2>ARTICLE 10 — DROITS DE L&apos;UTILISATEUR, GESTION DES PERMISSIONS ET SUPPRESSION</h2>
                </div>
                <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                  <strong>10.1.</strong> L&apos;Utilisateur peut à tout moment consulter le statut de son consentement, mettre
                  à jour sa permission de géolocalisation GPS ou révoquer ses clés API Binance directement depuis son espace
                  Bitsure.
                </p>
                <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                  <strong>10.2.</strong> L&apos;Utilisateur peut demander la clôture de son compte et la suppression de ses
                  données personnelles en ouvrant un ticket auprès de l&apos;Administrateur via l&apos;onglet Support, sous
                  réserve de la conservation des journaux de sécurité strictement nécessaires à la défense des droits de la
                  plateforme.
                </p>
              </section>

              <section className="rounded-xl border border-slate-800/90 bg-[#0C1220] p-5 sm:p-6 space-y-3">
                <div className="flex items-center gap-2.5 text-emerald-400 font-bold text-sm">
                  <Scale className="w-4 h-4" />
                  <h2>ARTICLE 11 — LIMITATION DE RESPONSABILITÉ ET DISPONIBILITÉ TECHNIQUE</h2>
                </div>
                <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                  Bitsure met en œuvre des mécanismes avancés de résilience (vérification de fraîcheur des données, coupe-circuit
                  de pertes journalières, validation de marge et Safe Mode). Toutefois, Bitsure ne saurait être tenu
                  responsable des interruptions de réseau, des maintenances ou pannes de l&apos;API Binance, des écarts de
                  slippage de marché, ni des pertes financières résultant de la configuration choisie par l&apos;Utilisateur.
                </p>
              </section>

              <section className="rounded-xl border border-slate-800/90 bg-[#0C1220] p-5 sm:p-6 space-y-3">
                <div className="flex items-center gap-2.5 text-emerald-400 font-bold text-sm">
                  <FileText className="w-4 h-4" />
                  <h2>ARTICLE 12 — ENTRÉE EN VIGUEUR, SIGNATURE ÉLECTRONIQUE ET MODIFICATIONS</h2>
                </div>
                <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                  Le fait de cocher la case{" "}
                  <span className="text-amber-300 font-semibold">
                    « J&apos;ai lu et j&apos;accepte les termes et conditions d&apos;utilisation »
                  </span>{" "}
                  lors de la création du compte vaut signature électronique définitive et consentement éclairé au sens de la
                  réglementation applicable sur la protection des données et les services numériques. Version en vigueur :{" "}
                  <strong className="text-amber-300 font-mono">v{TERMS_VERSION}</strong>.
                </p>
              </section>
            </>
          )}
        </div>

        {/* Bottom CTA Bar */}
        <div className="rounded-xl border border-slate-800 bg-[#0B101D] p-5 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="text-xs text-slate-400">
            Document officiel public — <strong className="text-slate-200">Bitsure Quantitative Trading Platform</strong> •
            Version <span className="font-mono text-amber-400">v{TERMS_VERSION}</span>
          </div>
          <div className="flex items-center gap-3 w-full sm:w-auto justify-end">
            <button
              onClick={onBack}
              className="px-4 py-2.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-200 text-xs font-semibold transition"
            >
              Retour
            </button>
            {showAcceptButton && onAcceptAndReturnToRegister && (
              <button
                onClick={onAcceptAndReturnToRegister}
                className="px-5 py-2.5 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs transition flex items-center gap-2 shadow-lg shadow-amber-500/20"
              >
                <CheckCircle2 className="w-4 h-4" />
                J&apos;ai lu et j&apos;accepte les Termes et Conditions
              </button>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
