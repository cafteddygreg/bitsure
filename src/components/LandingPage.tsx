import React from 'react';
import {
  ShieldCheck,
  TrendingUp,
  Layers,
  Activity,
  Lock,
  ArrowRight,
  CheckCircle2,
  BarChart3,
  Cpu,
  Globe,
} from 'lucide-react';
import { DemoAccount } from '../types';

interface LandingPageProps {
  onEnterWorkspace: () => void;
  onQuickLogin: (userId: number) => void;
  onOpenAuthModal: (mode: 'login' | 'register') => void;
  demoAccounts: DemoAccount[];
}

export const LandingPage: React.FC<LandingPageProps> = ({
  onEnterWorkspace,
  onQuickLogin,
  onOpenAuthModal,
  demoAccounts,
}) => {
  return (
    <div className="min-h-screen bg-[#090D16] text-[#F1F5F9] flex flex-col">
      {/* Top Single Navigation Header */}
      <header className="sticky top-0 z-30 border-b border-white/[0.07] bg-[#090D16]/85 backdrop-blur-md">
        <div className="max-w-[1400px] mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-[#10B981]/15 border border-[#10B981]/40 flex items-center justify-center text-[#10B981] font-display font-bold text-lg">
              B
            </div>
            <div>
              <div className="font-display font-bold text-base tracking-tight text-[#F1F5F9] flex items-center gap-2">
                BITSURE TEDDY <span className="text-xs font-mono-tabular text-[#10B981]">v2.0</span>
              </div>
              <div className="text-[11px] text-[#64748B]">Quantitative Market Intelligence & Execution</div>
            </div>
          </div>

          <nav className="hidden md:flex items-center gap-8 text-sm text-[#94A3B8]">
            <a href="#engine" className="hover:text-[#F1F5F9] transition-colors">Teddy Score Engine</a>
            <a href="#safety" className="hover:text-[#F1F5F9] transition-colors">Safety Architecture</a>
            <a href="#pricing" className="hover:text-[#F1F5F9] transition-colors">Plans & Accès</a>
          </nav>

          <div className="flex items-center gap-3">
            <button
              onClick={() => onOpenAuthModal('login')}
              className="px-3.5 py-2 text-xs font-medium text-[#94A3B8] hover:text-[#F1F5F9] border border-white/10 rounded-lg hover:bg-white/[0.04] transition-colors"
            >
              Connexion
            </button>
            <button
              onClick={onEnterWorkspace}
              className="px-4 py-2 text-xs font-semibold bg-[#10B981] hover:bg-[#059669] text-[#090D16] rounded-lg transition-colors flex items-center gap-1.5 shadow-lg shadow-[#10B981]/15"
            >
              Ouvrir le Terminal <ArrowRight className="w-3.5 h-3.5" />
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
              'radial-gradient(circle at 20% 20%, rgba(16, 185, 129, 0.16), transparent 50%), radial-gradient(circle at 80% 30%, rgba(245, 158, 11, 0.10), transparent 45%)',
          }}
        />
        <div className="max-w-[1400px] mx-auto px-6 relative z-10">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
            <div className="lg:col-span-7 space-y-6">
              <div className="inline-flex items-center gap-2 text-xs font-mono-tabular uppercase tracking-wider text-[#10B981] border-l-2 border-[#10B981] pl-3">
                Architecture Quantitative Multi-Timeframe • BTC • ETH • XAU/USD
              </div>

              <h1 className="font-display text-4xl sm:text-5xl lg:text-[54px] font-bold tracking-tight leading-[1.08] text-[#F1F5F9]">
                Analyse de marché explicable, gestion du risque ATR et exécution sécurisée.
              </h1>

              <p className="text-base sm:text-lg text-[#94A3B8] max-w-[64ch] leading-relaxed">
                Bitsure Teddy combine un moteur de confluence technique à 5 conditions, un score de confiance transparent sur 100 points, un simulateur Paper Trading réaliste (frais et slippage inclus) et une machine à états de sécurité pour Binance Spot et Futures.
              </p>

              <div className="flex flex-wrap items-center gap-3 pt-2">
                <button
                  onClick={onEnterWorkspace}
                  className="px-6 py-3.5 bg-[#10B981] hover:bg-[#059669] text-[#090D16] font-semibold text-sm rounded-lg transition-all flex items-center gap-2 shadow-xl shadow-[#10B981]/20"
                >
                  Lancer le Terminal Live <ArrowRight className="w-4 h-4" />
                </button>
                <button
                  onClick={() => onOpenAuthModal('register')}
                  className="px-5 py-3.5 bg-[#111827] hover:bg-[#1E293B] text-[#F1F5F9] border border-white/10 font-medium text-sm rounded-lg transition-colors"
                >
                  Créer un compte Essai (14 jours)
                </button>
              </div>

              {/* Instant Role Switcher Bar for Immediate Evaluation */}
              {demoAccounts.length > 0 && (
                <div className="pt-4 border-t border-white/[0.07]">
                  <div className="text-xs text-[#64748B] mb-2.5">
                    Accès rapide aux profils pré-configurés (Paper Trading, Alertes & Console Admin) :
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {demoAccounts.map((acc) => (
                      <button
                        key={acc.user_id}
                        onClick={() => onQuickLogin(acc.user_id)}
                        className="px-3 py-1.5 text-xs bg-[#111827] hover:bg-[#1E293B] border border-white/10 hover:border-[#10B981]/40 rounded-md text-[#F1F5F9] transition-colors flex items-center gap-2"
                      >
                        <span className="w-1.5 h-1.5 rounded-full bg-[#10B981]" />
                        <span>{acc.label}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Right Visual Architectural Card */}
            <div className="lg:col-span-5">
              <div className="bg-[#111827] border border-white/[0.09] rounded-xl p-5 shadow-2xl space-y-4">
                <div className="flex items-center justify-between border-b border-white/[0.07] pb-3">
                  <div>
                    <div className="text-xs text-[#64748B] uppercase tracking-wider">Moteur de Confluence</div>
                    <div className="font-display font-bold text-base text-[#F1F5F9]">Architecture Teddy Score (0–100)</div>
                  </div>
                  <span className="font-mono-tabular text-xs text-[#10B981] bg-[#10B981]/10 border border-[#10B981]/30 px-2.5 py-1 rounded">
                    STRATÉGIE v2.0
                  </span>
                </div>

                <div className="space-y-2.5 text-xs">
                  <div className="p-3 rounded-lg bg-[#090D16] border border-white/[0.06] flex items-center justify-between">
                    <div>
                      <div className="font-medium text-[#F1F5F9]">1. Alignement Tendance SMA 20 / SMA 50</div>
                      <div className="text-[#64748B]">Hiérarchie Multi-Timeframe (1H • 4H • 1D)</div>
                    </div>
                    <span className="font-mono-tabular text-[#10B981] font-semibold">25 pts + Bonus +15</span>
                  </div>

                  <div className="p-3 rounded-lg bg-[#090D16] border border-white/[0.06] flex items-center justify-between">
                    <div>
                      <div className="font-medium text-[#F1F5F9]">2. Fenêtre RSI(14) & Momentum MACD(12,26,9)</div>
                      <div className="text-[#64748B]">Filtrage des zones de surachat / survente</div>
                    </div>
                    <span className="font-mono-tabular text-[#38BDF8] font-semibold">40 pts cumulés</span>
                  </div>

                  <div className="p-3 rounded-lg bg-[#090D16] border border-white/[0.06] flex items-center justify-between">
                    <div>
                      <div className="font-medium text-[#F1F5F9]">3. Force Directionnelle ADX(14) & DI+/DI-</div>
                      <div className="text-[#64748B]">Rejet strict des marchés sans tendance (&lt; 22 ADX)</div>
                    </div>
                    <span className="font-mono-tabular text-[#F59E0B] font-semibold">20 pts</span>
                  </div>

                  <div className="p-3 rounded-lg bg-[#090D16] border border-white/[0.06] flex items-center justify-between">
                    <div>
                      <div className="font-medium text-[#F1F5F9]">4. Volatilité ATR(14) & Ratio Risque/Rendement</div>
                      <div className="text-[#64748B]">Stop-Loss dynamique ATR + filtrage S/R (&ge; 1:2.00 R:R)</div>
                    </div>
                    <span className="font-mono-tabular text-[#10B981] font-semibold">15 pts + Garde-fous</span>
                  </div>
                </div>

                <div className="pt-2 flex items-center justify-between text-xs text-[#94A3B8]">
                  <span>Frais Paper Trading : <strong className="font-mono-tabular text-[#F1F5F9]">0.04%</strong></span>
                  <span>Slippage : <strong className="font-mono-tabular text-[#F1F5F9]">0.02%</strong></span>
                  <span>Exposition Max : <strong className="font-mono-tabular text-[#F1F5F9]">20%</strong></span>
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
            <h2 className="font-display text-2xl sm:text-3xl font-bold text-[#F1F5F9]">
              Conçu pour la discipline opérationnelle
            </h2>
            <p className="text-sm text-[#94A3B8] mt-2">
              Chaque module du dépôt Python Bitsure Teddy est directement accessible dans une interface analytique unifiée.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-6 space-y-3">
              <div className="w-10 h-10 rounded-lg bg-[#10B981]/10 border border-[#10B981]/30 flex items-center justify-center text-[#10B981]">
                <BarChart3 className="w-5 h-5" />
              </div>
              <h3 className="font-display text-lg font-semibold text-[#F1F5F9]">
                Diagnostic de Signal Transparent
              </h3>
              <p className="text-sm text-[#94A3B8] leading-relaxed">
                Visualisez non seulement les signaux BUY/SELL validés, mais aussi la raison exacte de chaque signal WAIT (pullback SMA20 excessif, conflit HTF, ADX en baisse ou R:R insuffisant).
              </p>
            </div>

            <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-6 space-y-3">
              <div className="w-10 h-10 rounded-lg bg-[#3B82F6]/10 border border-[#3B82F6]/30 flex items-center justify-center text-[#60A5FA]">
                <Layers className="w-5 h-5" />
              </div>
              <h3 className="font-display text-lg font-semibold text-[#F1F5F9]">
                Paper Trading & Calculateur de Taille
              </h3>
              <p className="text-sm text-[#94A3B8] leading-relaxed">
                Portefeuille virtuel de 10 000 USDT avec levier 1x–20x, calcul automatique de taille de position selon votre % de risque par trade et clôture automatique sur SL/TP.
              </p>
            </div>

            <div id="safety" className="bg-[#111827] border border-white/[0.07] rounded-xl p-6 space-y-3">
              <div className="w-10 h-10 rounded-lg bg-[#F59E0B]/10 border border-[#F59E0B]/30 flex items-center justify-center text-[#FBBF24]">
                <ShieldCheck className="w-5 h-5" />
              </div>
              <h3 className="font-display text-lg font-semibold text-[#F1F5F9]">
                Safety Center & Réconciliation Binance
              </h3>
              <p className="text-sm text-[#94A3B8] leading-relaxed">
                Verrouillage automatique Safety Lock avec TTL d'une heure et rétrogradation en Safety Warn, protection par code PIN à 4 chiffres et réconciliation des ordres Spot/Futures.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Plans & Access Tiers */}
      <section id="pricing" className="py-16">
        <div className="max-w-[1400px] mx-auto px-6 space-y-10">
          <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
            <div>
              <h2 className="font-display text-2xl sm:text-3xl font-bold text-[#F1F5F9]">
                Niveaux d'accès & Abonnements
              </h2>
              <p className="text-sm text-[#94A3B8] mt-1">
                Paiement instantané via Binance Pay (USDT), Telegram Stars ou code promotionnel.
              </p>
            </div>
            <div className="text-xs font-mono-tabular text-[#94A3B8] bg-[#111827] border border-white/10 px-3.5 py-2 rounded-lg">
              Codes Promo Démo : <strong className="text-[#10B981]">TEDDYPRO</strong> • <strong className="text-[#F59E0B]">TEDDYVIP</strong>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Tester / Free Tier */}
            <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-6 flex flex-col justify-between">
              <div className="space-y-4">
                <div className="text-xs font-mono-tabular uppercase text-[#94A3B8]">Découverte / Essai</div>
                <div className="font-display text-3xl font-bold text-[#F1F5F9]">
                  Gratuit <span className="text-sm font-normal text-[#64748B]">/ 14 jours</span>
                </div>
                <ul className="space-y-2.5 text-sm text-[#94A3B8] pt-2">
                  <li className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-[#10B981]" /> 5 analyses quantitatives / jour</li>
                  <li className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-[#10B981]" /> Jusqu'à 5 actifs en Watchlist</li>
                  <li className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-[#10B981]" /> Jusqu'à 10 alertes prix actives</li>
                  <li className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-[#10B981]" /> Simulateur Paper Trading complet</li>
                </ul>
              </div>
              <button
                onClick={() => onOpenAuthModal('register')}
                className="mt-6 w-full py-2.5 text-xs font-semibold border border-white/15 rounded-lg hover:bg-white/[0.05] text-[#F1F5F9] transition-colors"
              >
                Démarrer l'essai gratuit
              </button>
            </div>

            {/* PRO Tier */}
            <div className="bg-[#111827] border border-[#10B981]/50 rounded-xl p-6 flex flex-col justify-between relative shadow-xl shadow-[#10B981]/5">
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono-tabular uppercase text-[#10B981] font-semibold">Bitsure PRO</span>
                  <span className="text-[11px] font-mono-tabular text-[#10B981] bg-[#10B981]/10 px-2 py-0.5 rounded">1 000 Stars</span>
                </div>
                <div className="font-display text-3xl font-bold text-[#F1F5F9]">
                  19 USDT <span className="text-sm font-normal text-[#64748B]">/ mois</span>
                </div>
                <ul className="space-y-2.5 text-sm text-[#94A3B8] pt-2">
                  <li className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-[#10B981]" /> Analyses multi-timeframes illimitées</li>
                  <li className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-[#10B981]" /> 20 actifs Watchlist & 50 Alertes prix</li>
                  <li className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-[#10B981]" /> Scanner multi-actifs en temps réel</li>
                  <li className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-[#10B981]" /> Auto-Trade Binance Spot & Futures</li>
                </ul>
              </div>
              <button
                onClick={() => onQuickLogin(100201)}
                className="mt-6 w-full py-2.5 text-xs font-semibold bg-[#10B981] hover:bg-[#059669] text-[#090D16] rounded-lg transition-colors"
              >
                Tester avec le compte PRO
              </button>
            </div>

            {/* VIP Tier */}
            <div className="bg-[#111827] border border-[#F59E0B]/40 rounded-xl p-6 flex flex-col justify-between">
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono-tabular uppercase text-[#F59E0B] font-semibold">Bitsure VIP</span>
                  <span className="text-[11px] font-mono-tabular text-[#F59E0B] bg-[#F59E0B]/10 px-2 py-0.5 rounded">2 500 Stars</span>
                </div>
                <div className="font-display text-3xl font-bold text-[#F1F5F9]">
                  49 USDT <span className="text-sm font-normal text-[#64748B]">/ mois</span>
                </div>
                <ul className="space-y-2.5 text-sm text-[#94A3B8] pt-2">
                  <li className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-[#F59E0B]" /> Alertes & Watchlist illimitées</li>
                  <li className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-[#F59E0B]" /> Styles Scalping 5m/15m, Day, Swing, Position</li>
                  <li className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-[#F59E0B]" /> Trailing Stop ATR & DCA intelligent</li>
                  <li className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-[#F59E0B]" /> Support prioritaire direct Admin</li>
                </ul>
              </div>
              <button
                onClick={() => onQuickLogin(100202)}
                className="mt-6 w-full py-2.5 text-xs font-semibold bg-[#F59E0B]/15 hover:bg-[#F59E0B]/25 border border-[#F59E0B]/40 text-[#FBBF24] rounded-lg transition-colors"
              >
                Tester avec le compte VIP
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};
