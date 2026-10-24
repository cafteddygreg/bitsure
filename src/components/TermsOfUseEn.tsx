import React, { useState } from 'react';
import { ArrowLeft, CheckCircle2, AlertTriangle, Scale } from 'lucide-react';

/**
 * English translation of the Bitsure Terms (French original: TermsOfUsePage.tsx, same version number).
 * Reading this page never records consent: acceptance only happens through the explicit button,
 * and that button is only shown during sign-up or for a pending legacy consent.
 */
interface Props {
  version: string;
  onBack: () => void;
  onAcceptAndReturnToRegister?: () => void;
  showAcceptButton?: boolean;
  isAccepted?: boolean;
}

type Item = string | { label: string; text: string };
interface Article {
  title: string;
  paragraphs?: string[];
  items?: Item[];
}
interface Group {
  id: string;
  label: string;
  articles: Article[];
}

const GROUPS: Group[] = [
  {
    id: 'service',
    label: '1–3. Purpose, Risks & Account',
    articles: [
      {
        title: 'ARTICLE 1 — PURPOSE OF THE CONTRACT AND DESCRIPTION OF THE BITSURE SERVICE',
        paragraphs: [
          '1.1. The Bitsure platform (including the web interface, the API server, the Teddy Score quantitative engine, the Strategy Lab backtesting laboratory and the official Telegram bot) provides algorithmic technical analysis tools, portfolio simulation (Paper Trading) and automated or semi-automated order execution on crypto-asset and precious-metal markets (notably through the Binance API).',
          '1.2. Access to the platform is strictly subject to full reading and unreserved acceptance of these Terms and Conditions of Use at the last step of account creation. No registration can be completed without this explicit acceptance.',
        ],
      },
      {
        title: 'ARTICLE 2 — FINANCIAL RISK WARNING AND NO INVESTMENT ADVICE',
        paragraphs: [
          '2.1. Purely technological and statistical nature: The signals (BUY / SELL / WAIT), the multi-factor scores (Teddy Score 0–100), the Stop-Loss (SL) and Take-Profit (TP1/TP2) levels and the backtest results are in no way financial, legal or tax advice, nor a personalized investment recommendation.',
          '2.2. Risk of capital loss: Trading cryptocurrencies (BTC, ETH, SOL, etc.) and leveraged contracts carries a high risk of rapid and total loss of the invested capital. Past or simulated performance in Paper Trading / Strategy Lab never guarantees future performance in real market conditions. The User acts under their sole and entire responsibility.',
        ],
      },
      {
        title: 'ARTICLE 3 — ACCOUNT CREATION, VERIFICATION AND ADMINISTRATOR VALIDATION',
        paragraphs: [
          '3.1. Manual approval: Every new account created on Bitsure is initialized with the status PENDING_APPROVAL. The Administrator has discretionary power to approve, refuse, suspend or revoke any user account at any time, based on the security and profile information collected.',
          '3.2. Accuracy of information: The User undertakes to provide a valid and verifiable email address and a real Telegram identifier (where applicable), and not to impersonate a third party or use any means intended to fraudulently falsify their identity during the security audit.',
        ],
      },
    ],
  },
  {
    id: 'privacy',
    label: '4–6. Personal Data, IP, Device & Location',
    articles: [
      {
        title: 'ARTICLE 4 — EXHAUSTIVE COLLECTION OF PERSONAL AND IDENTITY DATA (EXPLICIT CONSENT)',
        paragraphs: [
          'By accepting these Terms and Conditions when creating your account, you expressly authorize Bitsure to collect, store in its database and display in the administration panel the following personal data:',
        ],
        items: [
          { label: 'Personal identifiers:', text: 'Full email address, display name, Telegram handle (@username), unique numeric identifier (user_id) and Google OAuth identifier (google_sub) when signing in with Google.' },
          { label: 'Contractual evidence data:', text: `Terms acceptance status, exact version of the accepted contract, exact date and time of acceptance to the second, and the IP address used at the time of the electronic signature.` },
          { label: 'Commercial and subscription data:', text: 'Active pricing plan (Free, Pro, VIP), expiry date, promo codes used, Binance Pay payment memos, Telegram Stars transaction history and customer support requests.' },
        ],
      },
      {
        title: 'ARTICLE 5 — COLLECTION OF IP ADDRESS, NETWORK AND GEOGRAPHIC LOCATION',
        paragraphs: [
          'To guarantee platform security, prevent unauthorized access, comply with regulatory geographic restrictions and enable supervision by the Administrator, the User expressly consents to the automatic and continuous collection of:',
        ],
        items: [
          { label: 'IP addresses and network history:', text: 'The public IP address at sign-up, at each login and at each sensitive request, together with the full history of IP addresses used by the account (ip_history), the Internet service provider (ISP / ASN) and the type of network connection (4G/5G/Wi-Fi, estimated bandwidth).' },
          { label: 'IP-based geolocation and time zone:', text: "The country, region/state and city estimated from network headers, and the system time zone of the User's device (e.g. Europe/Paris)." },
          { label: 'Precise GPS geolocation (with browser permission):', text: "Where the User grants location permission to their browser or device, Bitsure collects and records the exact latitude and longitude coordinates and the accuracy radius in meters. The User may accept or refuse the browser's GPS permission prompt; if GPS is refused, network location (IP + time zone) is still collected in accordance with this contract." },
        ],
      },
      {
        title: 'ARTICLE 6 — COLLECTION OF DEVICE INFORMATION AND HARDWARE FINGERPRINT (TELEMETRY)',
        paragraphs: [
          "At each session (sign-up, login and active use of the terminal), Bitsure automatically records the technical characteristics of the User's device:",
        ],
        items: [
          { label: 'Device category and model:', text: 'Terminal type (mobile smartphone, tablet, desktop computer), detected hardware brand and model (e.g. Apple iPhone, Mac, Samsung Galaxy, Windows PC, Linux).' },
          { label: 'Operating system and browser:', text: 'Name and exact version of the OS (iOS, Android, macOS, Windows, Linux), browser name and version (Chrome, Safari, Firefox, Edge), full User-Agent string and hardware platform.' },
          { label: 'Hardware and screen characteristics:', text: 'Physical screen resolution, viewport size, pixel ratio (devicePixelRatio), color depth, number of logical processor cores (hardwareConcurrency), estimated memory (deviceMemory in GB), number of touch points (maxTouchPoints), battery level and charging state (if supported by the browser), configured languages, cookie state and referring URL (Referrer).' },
        ],
      },
    ],
  },
  {
    id: 'sensitive',
    label: '7–9. Sensitive Data, API Keys & Admin Audit',
    articles: [
      {
        title: 'ARTICLE 7 — COLLECTION AND PROCESSING OF SENSITIVE, FINANCIAL AND TRADING INFORMATION',
        paragraphs: [
          'As part of the advanced trading features (Paper Trading and Binance Live Trading) and account security, the User acknowledges and accepts that the following sensitive information is recorded and audited:',
        ],
        items: [
          { label: 'Binance API keys and secret keys:', text: "When the User connects their Binance account for real trading, their API key (api_key) and secret key (api_secret) are encrypted with Fernet AES-128-CBC + HMAC-SHA256 before being stored in the database, together with the linking date, the mode (Testnet or Live Production) and the key fingerprint." },
          { label: 'Authentication and security data:', text: 'Cryptographic hash of the password (PBKDF2-HMAC-SHA256), status and fingerprint of the 6-digit security PIN, number of failed attempts, anti-brute-force lockout timestamp, active session tokens and CSRF tokens.' },
          { label: 'All financial and trading activity:', text: 'Paper Trading capital, open and closed positions, full history of Binance Live orders (entry price, exit price, quantity, leverage, Stop-Loss, Take-Profit, Binance order ID, realized and unrealized PnL, execution errors), risk settings (risk per trade, maximum daily loss, maximum leverage, trading style), watchlist, price alerts and the history of all analyses requested.' },
        ],
      },
      {
        title: 'ARTICLE 8 — ADMINISTRATOR ACCESS TO THE 360° USER FILE',
        paragraphs: [
          "8.1. Full administrative visibility: The User is expressly informed of, and accepts without reservation, that the Bitsure Administrator has a dedicated supervision tab (360° User File / User Intelligence) grouping, for each account created: full identity, status and proof of consent to the Terms, current IP address and IP history, geographic location (country, city, GPS coordinates if authorized), device type and model, operating system, browser, hardware characteristics, status of API keys and security codes, active sessions, the security event log, and all Paper and Live trading portfolios and histories.",
          "8.2. Purposes of this access: This administrative access is used to: (a) verify and approve account opening requests; (b) detect account sharing, brute-force attacks or suspicious logins; (c) provide technical support and diagnose order execution or display errors on the User's device; (d) ensure contractual compliance and the overall security of the Bitsure infrastructure.",
        ],
      },
      {
        title: 'ARTICLE 9 — SECURITY, EVENT LOGGING AND CIRCUIT BREAKER (SAFE MODE)',
        paragraphs: [
          'All critical actions (account creation, login, password or PIN failure, linking of a Binance API key, enabling/disabling Auto-Trade, triggering of Safe Mode or quota overrun) are recorded with an unalterable timestamp in the security_events table, with the IP address and details of the operation.',
        ],
      },
    ],
  },
  {
    id: 'rights',
    label: '10–12. Rights, Liability & Jurisdiction',
    articles: [
      {
        title: 'ARTICLE 10 — USER RIGHTS, PERMISSION MANAGEMENT AND DELETION',
        paragraphs: [
          '10.1. The User may at any time check the status of their consent, update their GPS geolocation permission or revoke their Binance API keys directly from their Bitsure space.',
          '10.2. The User may request closure of their account and deletion of their personal data by opening a ticket with the Administrator via the Support tab, subject to retention of the security logs strictly necessary for the defense of the platform’s rights.',
        ],
      },
      {
        title: 'ARTICLE 11 — LIMITATION OF LIABILITY AND TECHNICAL AVAILABILITY',
        paragraphs: [
          'Bitsure implements advanced resilience mechanisms (data freshness checks, daily-loss circuit breaker, margin validation and Safe Mode). However, Bitsure cannot be held liable for network interruptions, maintenance or outages of the Binance API, market slippage differences, or financial losses resulting from the configuration chosen by the User.',
        ],
      },
      {
        title: 'ARTICLE 12 — ENTRY INTO FORCE, ELECTRONIC SIGNATURE AND AMENDMENTS',
        paragraphs: [
          'Ticking the box “I have read and I accept the terms and conditions of use” when creating the account constitutes a final electronic signature and informed consent within the meaning of the applicable regulations on data protection and digital services. Version in force: v{VERSION}.',
        ],
      },
    ],
  },
];

export function TermsOfUseEn({ version, onBack, onAcceptAndReturnToRegister, showAcceptButton = false, isAccepted = false }: Props) {
  const [active, setActive] = useState<string>('all');
  const visible = GROUPS.filter((g) => active === 'all' || active === g.id);
  const AcceptButton = showAcceptButton && onAcceptAndReturnToRegister && (
    <button
      type="button"
      onClick={onAcceptAndReturnToRegister}
      className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs transition"
    >
      <CheckCircle2 className="w-4 h-4" />
      {isAccepted ? 'Terms already accepted — Back to sign-up' : 'I have read and I accept these Terms — Continue sign-up'}
    </button>
  );

  return (
    <div className="min-h-screen bg-[#080C0F] text-slate-100 flex flex-col">
      <header className="sticky top-0 z-30 border-b border-slate-800/80 bg-[#0D1318]/95">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onBack}
              className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-700/80 text-slate-200 text-xs font-semibold transition"
            >
              <ArrowLeft className="w-4 h-4 text-amber-400" />
              Back
            </button>
            <Scale className="w-5 h-5 text-amber-400" />
            <div>
              <h1 className="text-sm sm:text-base font-bold text-white tracking-tight">
                BITSURE — Terms, General Conditions of Use &amp; Data Collection Charter{' '}
                <span className="px-2 py-0.5 text-[10px] font-mono font-semibold rounded bg-amber-500/15 text-amber-300 border border-amber-500/30">v{version}</span>
              </h1>
              <p className="text-[11px] text-slate-400">English translation of the French original. Reading this page does not accept the Terms.</p>
            </div>
          </div>
          {AcceptButton}
        </div>
      </header>

      <main className="flex-1 max-w-6xl w-full mx-auto px-4 sm:px-6 py-8 space-y-6">
        <div className="rounded-xl border border-amber-500/35 bg-slate-900/90 p-5 flex items-start gap-3.5">
          <AlertTriangle className="w-6 h-6 text-amber-400 shrink-0 mt-0.5" />
          <div className="space-y-2 text-xs sm:text-sm text-slate-200 leading-relaxed">
            <div className="text-xs font-mono uppercase tracking-wider text-amber-300 font-semibold">
              Full transparency notice &amp; mandatory prior consent to account creation
            </div>
            <p>
              By creating an account on <strong>Bitsure</strong> (web platform or Telegram bot), ticking the box “I have read and I accept the terms and conditions of use” and using our services, you enter into a legally binding contract and{' '}
              <strong>
                expressly authorize the Bitsure platform and its Administrator to collect, record, analyze and view all of your personal, technical, financial, behavioral and sensitive data related to your use of the service
              </strong>
              , as set out exhaustively below.
            </p>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          {[{ id: 'all', label: 'Full contract' }, ...GROUPS].map((g) => (
            <button
              key={g.id}
              type="button"
              onClick={() => setActive(g.id)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition border ${
                active === g.id ? 'bg-amber-500/20 text-amber-300 border-amber-500/40' : 'bg-slate-900/80 text-slate-400 border-slate-800 hover:text-slate-200'
              }`}
            >
              {g.label}
            </button>
          ))}
        </div>

        {visible.map((g) =>
          g.articles.map((a) => (
            <article key={a.title} className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 space-y-3">
              <h2 className="text-sm font-bold text-amber-300">{a.title}</h2>
              {a.paragraphs?.map((p, i) => (
                <p key={i} className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                  {p.replace('{VERSION}', version)}
                </p>
              ))}
              {a.items && (
                <ul className="list-disc pl-5 space-y-2 text-xs sm:text-sm text-slate-300 leading-relaxed">
                  {a.items.map((it, i) =>
                    typeof it === 'string' ? (
                      <li key={i}>{it}</li>
                    ) : (
                      <li key={i}>
                        <strong>{it.label}</strong> {it.text}
                      </li>
                    )
                  )}
                </ul>
              )}
            </article>
          ))
        )}

        <div className="rounded-xl border border-slate-800 bg-[#0D1318] p-5 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="text-xs text-slate-400">
            Official public document — <strong className="text-slate-200">Bitsure Quantitative Trading Platform</strong> • Version{' '}
            <span className="font-mono text-amber-400">v{version}</span>
          </div>
          <div className="flex gap-3">
            <button type="button" onClick={onBack} className="px-4 py-2.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-200 text-xs font-semibold transition">
              Back
            </button>
            {AcceptButton}
          </div>
        </div>
      </main>
    </div>
  );
}
