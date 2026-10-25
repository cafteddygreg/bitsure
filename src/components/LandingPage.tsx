import React from 'react';
import {
  ShieldCheck,
  Layers,
  ArrowRight,
  CheckCircle2,
  BarChart3,
  Globe,
} from 'lucide-react';
import { AppLang, tr } from '../i18n';
import { LearnSection } from './LearnSection';

interface LandingPageProps {
  onEnterWorkspace: () => void;
  onOpenAuthModal: (mode: 'login' | 'register') => void;
  onOpenTerms?: () => void;
  lang?: AppLang;
  onToggleLang?: () => void;
}

export const LandingPage: React.FC<LandingPageProps> = ({
  onEnterWorkspace,
  onOpenAuthModal,
  onOpenTerms,
  lang = 'fr',
  onToggleLang,
}) => {
  return (
    <div className="min-h-screen bg-[#080C0F] text-[#E8EEF2] flex flex-col">
      {/* Top Single Navigation Header */}
      <header className="sticky top-0 z-30 border-b border-white/[0.07] bg-[#080C0F]/85">
        <div className="max-w-[1400px] mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-[#20C997]/15 border border-[#20C997]/40 flex items-center justify-center text-[#20C997] font-display font-bold text-lg">
              B
            </div>
            <div>
              <div className="font-display font-bold text-base tracking-tight text-[#E8EEF2] flex items-center gap-2">
                BITSURE TEDDY <span className="text-xs font-mono-tabular text-[#20C997]">v2.0</span>
              </div>
              <div className="text-[11px] text-[#6E7B88]">
                {tr(lang, 'Intelligence Quantitative & Exécution Sécurisée', 'Quantitative Market Intelligence & Execution')}
              </div>
            </div>
          </div>

          <nav className="hidden md:flex items-center gap-8 text-sm text-[#8B98A4]">
            <a href="#engine" className="hover:text-[#E8EEF2] transition-colors">
              {tr(lang, 'Moteur Teddy Score', 'Teddy Score Engine')}
            </a>
            <a href="#safety" className="hover:text-[#E8EEF2] transition-colors">
              {tr(lang, 'Architecture Safety', 'Safety Architecture')}
            </a>
            <a href="#learn" className="hover:text-[#E8EEF2] transition-colors">
              {tr(lang, 'Apprendre', 'Learn')}
            </a>
            <a href="#pricing" className="hover:text-[#E8EEF2] transition-colors">
              {tr(lang, 'Plans & Accès', 'Plans & Access')}
            </a>
            {onOpenTerms && (
              <button
                type="button"
                onClick={onOpenTerms}
                className="text-[#D6A84F] hover:text-[#E2BC6A] font-semibold transition-colors"
              >
                {tr(lang, "Termes & Conditions d'Utilisation", 'Terms & Conditions')}
              </button>
            )}
          </nav>

          <div className="flex items-center gap-2 sm:gap-3">
            {onOpenTerms && (
              <button
                type="button"
                onClick={onOpenTerms}
                className="md:hidden px-2.5 py-2 text-xs font-semibold text-[#D6A84F] border border-[#D6A84F]/30 rounded-lg bg-[#D6A84F]/10"
              >
                CGU
              </button>
            )}
            {onToggleLang && (
              <button
                type="button"
                onClick={onToggleLang}
                className="px-2.5 py-2 text-xs font-mono-tabular font-semibold uppercase text-[#8B98A4] hover:text-[#E8EEF2] border border-white/10 rounded-lg hover:bg-white/[0.04] transition-colors flex items-center gap-1.5"
                title={tr(lang, 'Changer la langue (FR / EN)', 'Switch language (FR / EN)')}
              >
                <Globe className="w-3.5 h-3.5 text-[#20C997]" />
                <span>{lang.toUpperCase()}</span>
              </button>
            )}
            <button
              onClick={() => onOpenAuthModal('login')}
              className="px-3.5 py-2 text-xs font-medium text-[#8B98A4] hover:text-[#E8EEF2] border border-white/10 rounded-lg hover:bg-white/[0.04] transition-colors"
            >
              {tr(lang, 'Connexion', 'Log In')}
            </button>
            <button
              onClick={onEnterWorkspace}
              className="px-4 py-2 text-xs font-semibold bg-[#20C997] hover:bg-[#1AA67D] text-[#080C0F] rounded-lg transition-colors flex items-center gap-1.5"
            >
              <span>{tr(lang, 'Essayer la démo', 'Try the demo')}</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section className="relative pt-14 pb-20 border-b border-white/[0.06] overflow-hidden">
        <div
          className="absolute inset-0 pointer-events-none opacity-25"
          style={{
            background:
              'radial-gradient(circle at 20% 20%, rgba(32, 201, 151, 0.16), transparent 50%), radial-gradient(circle at 80% 30%, rgba(214, 168, 79, 0.10), transparent 45%)',
          }}
        />
        <div className="max-w-[1400px] mx-auto px-6 relative z-10">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
            <div className="lg:col-span-7 space-y-6">
              <div className="inline-flex items-center gap-2 text-xs font-mono-tabular uppercase tracking-wider text-[#20C997] border-l-2 border-[#20C997] pl-3">
                {tr(
                  lang,
                  'Analyse multi-échelles de temps (lecture du marché sur plusieurs durées) • 10 cryptos Binance',
                  'Multi-timeframe analysis (reading the market over several time spans) • 10 Binance cryptos'
                )}
              </div>

              <h1 className="font-display text-4xl sm:text-5xl lg:text-[54px] font-bold tracking-tight leading-[1.08] text-[#E8EEF2]">
                {tr(
                  lang,
                  "Analysez des stratégies crypto, entraînez-vous avec de l'argent virtuel, puis automatisez sur Binance.",
                  'Analyze crypto strategies, practice with virtual money, then automate on Binance.'
                )}
              </h1>

              <p className="text-base sm:text-lg text-[#8B98A4] max-w-[64ch] leading-relaxed">
                {tr(
                  lang,
                  "Un score de 0 à 100 vous dit si les indicateurs techniques sont alignés. Vous testez d'abord en simulation (frais et glissement de prix inclus), sans risque.",
                  'A 0–100 score tells you whether the technical indicators agree. You test in simulation first (fees and price slippage included), with no risk.'
                )}
              </p>

              <div className="flex flex-wrap items-center gap-3 pt-2">
                <button
                  onClick={onEnterWorkspace}
                  className="px-6 py-3.5 bg-[#20C997] hover:bg-[#1AA67D] text-[#080C0F] font-semibold text-sm rounded-lg transition-all flex items-center gap-2 shadow-xl shadow-[#20C997]/20"
                >
                  <span>{tr(lang, 'Essayer la démo gratuite', 'Try the free demo')}</span>
                  <ArrowRight className="w-4 h-4" />
                </button>
                <button
                  onClick={() => onOpenAuthModal('register')}
                  className="px-5 py-3.5 bg-[#0D1318] hover:bg-[#172129] text-[#E8EEF2] border border-white/10 font-medium text-sm rounded-lg transition-colors"
                >
                  {tr(lang, 'Créer un compte', 'Create Account')}
                </button>
                <button
                  onClick={() => onOpenAuthModal('login')}
                  className="px-2 py-3.5 text-sm text-[#8B98A4] hover:text-[#E8EEF2] underline underline-offset-4"
                >
                  {tr(lang, 'Se connecter', 'Log in')}
                </button>
              </div>
              <p className="text-xs text-[#6E7B88]">
                {tr(
                  lang,
                  'Démo : 100 % simulée, sans compte, sans clé API, sans connexion à un exchange.',
                  'Demo: fully simulated, no account, no API key, no exchange connection.'
                )}
              </p>
            </div>

            {/* Right Visual Architectural Card */}
            <div className="lg:col-span-5">
              <div className="bg-[#0D1318] border border-white/[0.09] rounded-xl p-5 space-y-4">
                <div className="flex items-center justify-between border-b border-white/[0.07] pb-3">
                  <div>
                    <div className="text-xs text-[#6E7B88] uppercase tracking-wider">
                      {tr(lang, 'Moteur de Confluence', 'Confluence Engine')}
                    </div>
                    <div className="font-display font-bold text-base text-[#E8EEF2]">
                      {tr(lang, 'Architecture Teddy Score (0–100)', 'Teddy Score Architecture (0–100)')}
                    </div>
                  </div>
                  <span className="font-mono-tabular text-xs text-[#20C997] bg-[#20C997]/10 border border-[#20C997]/30 px-2.5 py-1 rounded">
                    {tr(lang, 'STRATÉGIE v2.0', 'STRATEGY v2.0')}
                  </span>
                </div>

                <div className="space-y-2 text-xs">
                  <div className="text-[#6E7B88]">
                    {tr(lang, '7 lignes groupées = 100 points maximum', '7 grouped rows = 100 points maximum')}
                  </div>
                  {[
                    ['Tendance SMA + retour vers la SMA 20', 'SMA trend + pullback to SMA 20', 25],
                    ['Momentum MACD', 'MACD momentum', 20],
                    ['Force de tendance ADX', 'ADX trend strength', 15],
                    ['Support / résistance (S/R)', 'Support / resistance (S/R)', 15],
                    ['RSI', 'RSI', 10],
                    ['Gain/risque (R:R)', 'Reward/risk (R:R)', 10],
                    ['Volume', 'Volume', 5],
                  ].map(([fr, en, pts]) => (
                    <div key={String(fr)} className="px-3 py-2 rounded-lg bg-[#080C0F] border border-white/[0.06] flex items-center justify-between">
                      <span className="text-[#E8EEF2]">{tr(lang, String(fr), String(en))}</span>
                      <span className="font-mono-tabular text-[#20C997] font-semibold">{pts}</span>
                    </div>
                  ))}
                  <div className="px-3 py-2 rounded-lg bg-[#D6A84F]/10 border border-[#D6A84F]/30 text-[#E2BC6A]">
                    {tr(
                      lang,
                      'Ensuite : bonus multi-timeframes +15 (ou +5, 0, −15). Score final limité à 100.',
                      'Then: multi-timeframe bonus +15 (or +5, 0, −15). Final score capped at 100.'
                    )}
                  </div>
                </div>

                <div className="pt-2 flex items-center justify-between text-xs text-[#8B98A4]">
                  <span>
                    {tr(lang, 'Frais Paper Trading :', 'Paper Trading Fees:')}{' '}
                    <strong className="font-mono-tabular text-[#E8EEF2]">0.04%</strong>
                  </span>
                  <span>
                    {tr(lang, 'Slippage :', 'Slippage:')}{' '}
                    <strong className="font-mono-tabular text-[#E8EEF2]">0.02%</strong>
                  </span>
                  <span>
                    {tr(lang, 'Exposition Max :', 'Max Exposure:')}{' '}
                    <strong className="font-mono-tabular text-[#E8EEF2]">20%</strong>
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Core Capabilities Section */}
      <section id="engine" className="py-16 border-b border-white/[0.06]">
        <div className="max-w-[1400px] mx-auto px-6 space-y-10">
          <div className="max-w-2xl">
            <h2 className="font-display text-2xl sm:text-3xl font-bold text-[#E8EEF2]">
              {tr(lang, 'Conçu pour la discipline opérationnelle', 'Engineered for Operational Discipline')}
            </h2>
            <p className="text-sm text-[#8B98A4] mt-2">
              {tr(
                lang,
                'Chaque module du dépôt Python Bitsure Teddy est directement accessible dans une interface analytique unifiée.',
                'Every module of the Bitsure Teddy Python engine is directly accessible inside a unified analytical terminal.'
              )}
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="bg-[#0D1318] border border-white/[0.07] rounded-xl p-6 space-y-3">
              <div className="w-10 h-10 rounded-lg bg-[#20C997]/10 border border-[#20C997]/30 flex items-center justify-center text-[#20C997]">
                <BarChart3 className="w-5 h-5" />
              </div>
              <h3 className="font-display text-lg font-semibold text-[#E8EEF2]">
                {tr(lang, 'Diagnostic de Signal Transparent', 'Transparent Signal Diagnostics')}
              </h3>
              <p className="text-sm text-[#8B98A4] leading-relaxed">
                {tr(
                  lang,
                  'Visualisez non seulement les signaux BUY/SELL validés, mais aussi la raison exacte de chaque signal WAIT (pullback SMA20 excessif, conflit HTF, ADX en baisse ou R:R insuffisant).',
                  'Inspect not only validated BUY/SELL signals, but also the exact reason for every WAIT decision (excessive SMA20 pullback, HTF conflict, falling ADX, or insufficient R:R).'
                )}
              </p>
            </div>

            <div className="bg-[#0D1318] border border-white/[0.07] rounded-xl p-6 space-y-3">
              <div className="w-10 h-10 rounded-lg bg-[#4EA1FF]/10 border border-[#4EA1FF]/30 flex items-center justify-center text-[#6BB1FF]">
                <Layers className="w-5 h-5" />
              </div>
              <h3 className="font-display text-lg font-semibold text-[#E8EEF2]">
                {tr(lang, 'Paper Trading & Calculateur de Taille', 'Paper Trading & Position Size Calculator')}
              </h3>
              <p className="text-sm text-[#8B98A4] leading-relaxed">
                {tr(
                  lang,
                  'Portefeuille virtuel de 10 000 USDT avec levier 1x–20x, calcul automatique de taille de position selon votre % de risque par trade et clôture automatique sur SL/TP.',
                  '10,000 USDT virtual portfolio with 1x–20x leverage, automatic position sizing based on your risk % per trade, and automatic SL/TP closure.'
                )}
              </p>
            </div>

            <div id="safety" className="bg-[#0D1318] border border-white/[0.07] rounded-xl p-6 space-y-3">
              <div className="w-10 h-10 rounded-lg bg-[#D6A84F]/10 border border-[#D6A84F]/30 flex items-center justify-center text-[#E2BC6A]">
                <ShieldCheck className="w-5 h-5" />
              </div>
              <h3 className="font-display text-lg font-semibold text-[#E8EEF2]">
                {tr(lang, 'Safety Center & Réconciliation Binance', 'Safety Center & Binance Reconciliation')}
              </h3>
              <p className="text-sm text-[#8B98A4] leading-relaxed">
                {tr(
                  lang,
                  "Verrouillage critique Safety Lock persistant jusqu'au déverrouillage manuel par code PIN (avec rappel après 1 heure), et réconciliation des ordres Spot/Futures.",
                  'Persistent Safety Lock requiring manual PIN unlock (with 1-hour reminder), and Spot/Futures order reconciliation.'
                )}
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Plans & Access Tiers */}
      <LearnSection lang={lang} onStartDemo={onEnterWorkspace} onCreateAccount={() => onOpenAuthModal('register')} />

      <section id="pricing" className="py-16">
        <div className="max-w-[1400px] mx-auto px-6 space-y-10">
          <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
            <div>
              <h2 className="font-display text-2xl sm:text-3xl font-bold text-[#E8EEF2]">
                {tr(lang, "Niveaux d'accès & Abonnements", 'Access Tiers & Subscriptions')}
              </h2>
              <p className="text-sm text-[#8B98A4] mt-1">
                {tr(
                  lang,
                  'Paiement instantané via Binance Pay (USDT), Telegram Stars ou code promotionnel.',
                  'Instant activation via Binance Pay (USDT), Telegram Stars, or promotional code.'
                )}
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Standard / Free Tier */}
            <div className="bg-[#0D1318] border border-white/[0.07] rounded-xl p-6 flex flex-col justify-between">
              <div className="space-y-4">
                <div className="text-xs font-mono-tabular uppercase text-[#8B98A4]">
                  {tr(lang, 'Accès Standard', 'Standard Access')}
                </div>
                <div className="font-display text-3xl font-bold text-[#E8EEF2]">
                  {tr(lang, 'Gratuit', 'Free')}{' '}
                  <span className="text-sm font-normal text-[#6E7B88]">
                    {tr(lang, '/ 14 jours', '/ 14 days')}
                  </span>
                </div>
                <ul className="space-y-2.5 text-sm text-[#8B98A4] pt-2">
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-[#20C997]" />{' '}
                    {tr(lang, '5 analyses quantitatives / jour', '5 quantitative analyses / day')}
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-[#20C997]" />{' '}
                    {tr(lang, "Jusqu'à 5 actifs en Watchlist", 'Up to 5 Watchlist assets')}
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-[#20C997]" />{' '}
                    {tr(lang, "Jusqu'à 10 alertes prix actives", 'Up to 10 active price alerts')}
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-[#20C997]" />{' '}
                    {tr(lang, 'Simulateur Paper Trading complet', 'Full Paper Trading simulator')}
                  </li>
                </ul>
              </div>
              <p className="mt-4 text-[11px] leading-relaxed text-[#6E7B88]">
                {tr(lang, "L'essai gratuit court dès la création du compte ; l'approbation par l'administrateur est une étape distincte, nécessaire avant toute utilisation.", 'The free trial runs from account creation; administrator approval is a separate step, required before you can use anything.')}
              </p>
              <button
                onClick={() => onOpenAuthModal('register')}
                className="mt-6 w-full py-2.5 text-xs font-semibold border border-white/15 rounded-lg hover:bg-white/[0.05] text-[#E8EEF2] transition-colors"
              >
                {tr(lang, 'Créer un compte', 'Create Account')}
              </button>
            </div>

            {/* PRO Tier */}
            <div className="bg-[#0D1318] border border-[#20C997]/50 rounded-xl p-6 flex flex-col justify-between relative shadow-xl shadow-[#20C997]/5">
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono-tabular uppercase text-[#20C997] font-semibold">Bitsure PRO</span>
                  <span className="text-[11px] font-mono-tabular text-[#20C997] bg-[#20C997]/10 px-2 py-0.5 rounded">
                    1 000 Stars
                  </span>
                </div>
                <div className="font-display text-3xl font-bold text-[#E8EEF2]">
                  19 USDT{' '}
                  <span className="text-sm font-normal text-[#6E7B88]">{tr(lang, '/ mois', '/ month')}</span>
                </div>
                <ul className="space-y-2.5 text-sm text-[#8B98A4] pt-2">
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-[#20C997]" />{' '}
                    {tr(lang, 'Analyses multi-timeframes illimitées', 'Unlimited multi-timeframe analyses')}
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-[#20C997]" />{' '}
                    {tr(lang, '20 actifs Watchlist & 50 Alertes prix', '20 Watchlist assets & 50 Price alerts')}
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-[#20C997]" />{' '}
                    {tr(lang, 'Scanner multi-actifs en temps réel', 'Real-time multi-asset scanner')}
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-[#20C997]" />{' '}
                    {tr(lang, 'Auto-Trade Binance Spot & Futures', 'Binance Spot & Futures Auto-Trade')}
                  </li>
                </ul>
              </div>
              <p className="mt-4 text-[11px] leading-relaxed text-[#6E7B88]">
                {tr(lang, 'Activation = paiement reçu : 19 USDT (Binance Pay) ou 1 000 Stars Telegram donnent les mêmes 30 jours, sans renouvellement automatique.', 'Activation = payment received: 19 USDT (Binance Pay) or 1,000 Telegram Stars buy the same 30 days, with no automatic renewal.')}
              </p>
              <button
                onClick={() => onOpenAuthModal('register')}
                className="mt-6 w-full py-2.5 text-xs font-semibold bg-[#20C997] hover:bg-[#1AA67D] text-[#080C0F] rounded-lg transition-colors"
              >
                {tr(lang, 'Créer un compte pour le plan Pro', 'Create an account for Pro')}
              </button>
            </div>

            {/* VIP Tier */}
            <div className="bg-[#0D1318] border border-[#D6A84F]/40 rounded-xl p-6 flex flex-col justify-between">
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono-tabular uppercase text-[#D6A84F] font-semibold">Bitsure VIP</span>
                  <span className="text-[11px] font-mono-tabular text-[#D6A84F] bg-[#D6A84F]/10 px-2 py-0.5 rounded">
                    2 500 Stars
                  </span>
                </div>
                <div className="font-display text-3xl font-bold text-[#E8EEF2]">
                  49 USDT{' '}
                  <span className="text-sm font-normal text-[#6E7B88]">{tr(lang, '/ mois', '/ month')}</span>
                </div>
                <ul className="space-y-2.5 text-sm text-[#8B98A4] pt-2">
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-[#D6A84F]" />{' '}
                    {tr(lang, 'Alertes & Watchlist illimitées', 'Unlimited Alerts & Watchlist')}
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-[#D6A84F]" />{' '}
                    {tr(lang, 'Styles Scalping 5m/15m, Day, Swing, Position', 'Scalping 5m/15m, Day, Swing & Position styles')}
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-[#D6A84F]" />{' '}
                    {tr(lang, 'Trailing Stop ATR & DCA intelligent', 'Dynamic ATR Trailing Stop & Smart DCA')}
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-[#D6A84F]" />{' '}
                    {tr(lang, 'Support prioritaire direct Admin', 'Priority Direct Admin Support')}
                  </li>
                </ul>
              </div>
              <p className="mt-4 text-[11px] leading-relaxed text-[#6E7B88]">
                {tr(lang, "49 USDT ou 2 500 Stars pour 30 jours ; renouveler avant l'échéance ajoute 30 jours au temps restant.", '49 USDT or 2,500 Stars for 30 days; renewing early adds 30 days on top of the time remaining.')}
              </p>
              <button
                onClick={() => onOpenAuthModal('register')}
                className="mt-6 w-full py-2.5 text-xs font-semibold bg-[#D6A84F]/15 hover:bg-[#D6A84F]/25 border border-[#D6A84F]/40 text-[#E2BC6A] rounded-lg transition-colors"
              >
                {tr(lang, 'Créer un compte pour le plan VIP', 'Create an account for VIP')}
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Public Footer with Terms & Conditions Link */}
      <footer className="mt-auto py-6 border-t border-white/[0.07] bg-[#080C0F] text-xs text-[#6E7B88]">
        <div className="max-w-[1400px] mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div>
            BITSURE TEDDY QUANT — {tr(lang, 'Plateforme Quantitative & Exécution Sécurisée', 'Quantitative Platform & Secure Execution')}
          </div>
          <div className="flex flex-wrap items-center gap-5">
            {onOpenTerms && (
              <button
                type="button"
                onClick={onOpenTerms}
                className="text-[#D6A84F] hover:text-[#E2BC6A] underline underline-offset-4 font-semibold transition-colors"
              >
                {tr(lang, "Termes et Conditions d'Utilisation (CGU & Collecte des Données)", 'Terms and Conditions of Use & Data Privacy')}
              </button>
            )}
            <button
              type="button"
              onClick={() => onOpenAuthModal('login')}
              className="hover:text-[#E8EEF2] transition-colors"
            >
              {tr(lang, 'Connexion', 'Log In')}
            </button>
            <button
              type="button"
              onClick={() => onOpenAuthModal('register')}
              className="hover:text-[#E8EEF2] transition-colors"
            >
              {tr(lang, 'Créer un compte', 'Create Account')}
            </button>
          </div>
        </div>
      </footer>
    </div>
  );
};
