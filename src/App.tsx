import React, { useState, useEffect, useCallback } from 'react';
import './index.css';
import { apiFetch, setStoredSession } from './api';
import {
  UserProfile,
  DemoAccount,
  MarketAnalysis,
  PaperStats,
  PaperPosition,
  PriceAlert,
  HistoricalSignal,
  TradingConfigState,
  SupportTicket,
  WebNotification,
} from './types';
import { PriceChart } from './components/PriceChart';
import { LandingPage } from './components/LandingPage';
import {
  Activity,
  AlertTriangle,
  Bell,
  BookOpen,
  CheckCircle2,
  ChevronRight,
  Clock,
  Compass,
  CreditCard,
  DollarSign,
  Key,
  Layers,
  Lock,
  LogOut,
  MessageSquare,
  Play,
  Plus,
  RefreshCw,
  Search,
  Settings,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Sliders,
  Sparkles,
  Star,
  Terminal,
  Trash2,
  TrendingDown,
  TrendingUp,
  Unlock,
  UserCheck,
  Users,
  Wallet,
  XCircle,
} from 'lucide-react';

type ActiveTab =
  | 'intelligence'
  | 'paper'
  | 'alerts'
  | 'safety'
  | 'history'
  | 'account'
  | 'admin';

const SYMBOLS = [
  { id: 'BTCUSDT', label: 'BTC / USDT', category: 'Crypto Spot/Perp' },
  { id: 'ETHUSDT', label: 'ETH / USDT', category: 'Crypto Spot/Perp' },
  { id: 'XAUUSD', label: 'XAU / USD (Or)', category: 'Matières Premières' },
];

const TIMEFRAMES = ['5m', '15m', '1h', '4h', '1d'];
const STYLES = [
  { id: 'scalping', label: 'Scalping (5m)' },
  { id: 'scalping_15m', label: 'Scalping (15m)' },
  { id: 'day', label: 'Day Trading (1h)' },
  { id: 'swing', label: 'Swing (4h)' },
  { id: 'position', label: 'Position (1D)' },
];

export function App() {
  const [viewMode, setViewMode] = useState<'landing' | 'workspace'>('workspace');
  const [activeTab, setActiveTab] = useState<ActiveTab>('intelligence');

  // Auth & User State
  const [user, setUser] = useState<UserProfile | null>(null);
  const [demoAccounts, setDemoAccounts] = useState<DemoAccount[]>([]);
  const [authModal, setAuthModal] = useState<'login' | 'register' | null>(null);
  const [authEmail, setAuthEmail] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [authName, setAuthName] = useState('');
  const [authTelegram, setAuthTelegram] = useState('');

  // Market Intelligence State
  const [selectedSymbol, setSelectedSymbol] = useState('BTCUSDT');
  const [selectedTimeframe, setSelectedTimeframe] = useState('1h');
  const [selectedStyle, setSelectedStyle] = useState('day');
  const [analysis, setAnalysis] = useState<MarketAnalysis | null>(null);
  const [multiScans, setMultiScans] = useState<MarketAnalysis[]>([]);
  const [loadingAnalysis, setLoadingAnalysis] = useState(false);
  const [loadingScan, setLoadingScan] = useState(false);

  // Paper Trading State
  const [paperStats, setPaperStats] = useState<PaperStats | null>(null);
  const [openPaper, setOpenPaper] = useState<PaperPosition[]>([]);
  const [closedPaper, setClosedPaper] = useState<PaperPosition[]>([]);
  const [orderSide, setOrderSide] = useState<'BUY' | 'SELL'>('BUY');
  const [orderQty, setOrderQty] = useState('0.04');
  const [orderLeverage, setOrderLeverage] = useState('2');
  const [orderSL, setOrderSL] = useState('');
  const [orderTP, setOrderTP] = useState('');

  // Alerts State
  const [alerts, setAlerts] = useState<PriceAlert[]>([]);
  const [alertLimit, setAlertLimit] = useState(50);
  const [newAlertSymbol, setNewAlertSymbol] = useState('BTCUSDT');
  const [newAlertCond, setNewAlertCond] = useState<'above' | 'below'>('above');
  const [newAlertPrice, setNewAlertPrice] = useState('');

  // Signals History & Decision Journal
  const [signalHistory, setSignalHistory] = useState<HistoricalSignal[]>([]);
  const [decisionJournal, setDecisionJournal] = useState<any[]>([]);

  // Live Trading & Safety Center
  const [tradingCfg, setTradingCfg] = useState<TradingConfigState | null>(null);
  const [liveTrades, setLiveTrades] = useState<{ open: any[]; closed: any[] }>({ open: [], closed: [] });
  const [binanceKey, setBinanceKey] = useState('');
  const [binanceSecret, setBinanceSecret] = useState('');
  const [binanceTestnet, setBinanceTestnet] = useState(true);
  const [safetyPinInput, setSafetyPinInput] = useState('');
  const [testingApiConn, setTestingApiConn] = useState(false);
  const [liveAccount, setLiveAccount] = useState<any | null>(null);
  const [liveOpenOrders, setLiveOpenOrders] = useState<any[]>([]);
  const [loadingLiveAccount, setLoadingLiveAccount] = useState(false);
  const [liveOrderSymbol, setLiveOrderSymbol] = useState('BTCUSDT');
  const [liveOrderSide, setLiveOrderSide] = useState<'BUY' | 'SELL'>('BUY');
  const [liveOrderAmount, setLiveOrderAmount] = useState('25');
  const [liveOrderAmountMode, setLiveOrderAmountMode] = useState<'fixed' | 'percentage'>('fixed');
  const [liveOrderType, setLiveOrderType] = useState<'MARKET' | 'LIMIT'>('MARKET');
  const [liveOrderEntryPrice, setLiveOrderEntryPrice] = useState('');
  const [liveOrderSL, setLiveOrderSL] = useState('');
  const [liveOrderTP, setLiveOrderTP] = useState('');
  const [liveOrderLeverage, setLiveOrderLeverage] = useState('5');
  const [liveOrderMarginType, setLiveOrderMarginType] = useState<'ISOLATED' | 'CROSS'>('ISOLATED');
  const [liveOrderReduceOnly, setLiveOrderReduceOnly] = useState(false);
  const [liveOrderDraftCheck, setLiveOrderDraftCheck] = useState<any | null>(null);

  // Account, Security PIN, Promo & Support
  const [promoCodeInput, setPromoCodeInput] = useState('');
  const [paymentInfo, setPaymentInfo] = useState<any | null>(null);
  const [newPin, setNewPin] = useState('');
  const [oldPin, setOldPin] = useState('');
  const [tickets, setTickets] = useState<SupportTicket[]>([]);
  const [ticketSubject, setTicketSubject] = useState('');
  const [ticketMessage, setTicketMessage] = useState('');
  const [notifications, setNotifications] = useState<WebNotification[]>([]);

  // Admin Console State
  const [adminData, setAdminData] = useState<any | null>(null);
  const [doctorQuestion, setDoctorQuestion] = useState('');
  const [doctorReport, setDoctorReport] = useState('');
  const [broadcastTitle, setBroadcastTitle] = useState('');
  const [broadcastBody, setBroadcastBody] = useState('');
  const [adminReplyMap, setAdminReplyMap] = useState<Record<number, string>>({});

  // Toast feedback banner
  const [toast, setToast] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(null);

  const showToast = useCallback((text: string, type: 'success' | 'error' | 'info' = 'info') => {
    setToast({ text, type });
    setTimeout(() => {
      setToast((prev) => (prev?.text === text ? null : prev));
    }, 4500);
  }, []);

  const loadUserAndCoreData = useCallback(async () => {
    try {
      const meRes = await apiFetch('/api/auth/me');
      setUser(meRes.user);
      setDemoAccounts(meRes.demo_accounts || []);

      const [paperRes, alertsRes, cfgRes, notifRes] = await Promise.all([
        apiFetch('/api/paper/overview'),
        apiFetch('/api/alerts'),
        apiFetch('/api/trading/config'),
        apiFetch('/api/notifications'),
      ]);

      setPaperStats(paperRes.stats);
      setOpenPaper(paperRes.open_positions || []);
      setClosedPaper(paperRes.closed_positions || []);
      setAlerts(alertsRes.alerts || []);
      setAlertLimit(alertsRes.limit || 50);
      setTradingCfg(cfgRes.config);
      setLiveTrades(cfgRes.live_trades || { open: [], closed: [] });
      setNotifications(notifRes.notifications || []);
    } catch (err: any) {
      console.error('Initial data load error:', err);
    }
  }, []);

  const runAnalysis = useCallback(
    async (sym = selectedSymbol, tf = selectedTimeframe, st = selectedStyle) => {
      setLoadingAnalysis(true);
      try {
        const res = await apiFetch(
          `/api/market/analyze?symbol=${encodeURIComponent(sym)}&timeframe=${encodeURIComponent(tf)}&style=${encodeURIComponent(st)}&lang=${user?.lang || 'fr'}`
        );
        const ana: MarketAnalysis = res.analysis;
        setAnalysis(ana);
        if (ana.sizing_recommendation?.position_size > 0) {
          setOrderQty(String(ana.sizing_recommendation.position_size));
        }
        if (ana.sl) {
          setOrderSL(String(ana.sl));
        } else if (ana.current_price) {
          setOrderSL((ana.current_price * 0.985).toFixed(2));
        }
        if (ana.tp1) {
          setOrderTP(String(ana.tp1));
        } else if (ana.current_price) {
          setOrderTP((ana.current_price * 1.03).toFixed(2));
        }
        if (!newAlertPrice && ana.current_price) {
          setNewAlertPrice((ana.current_price * 1.015).toFixed(2));
        }
      } catch (err: any) {
        showToast(err.message, 'error');
      } finally {
        setLoadingAnalysis(false);
      }
    },
    [selectedSymbol, selectedTimeframe, selectedStyle, user?.lang, newAlertPrice, showToast]
  );

  const runMultiScan = useCallback(async () => {
    setLoadingScan(true);
    try {
      const res = await apiFetch(
        `/api/market/multi-scan?timeframe=${encodeURIComponent(selectedTimeframe)}&style=${encodeURIComponent(selectedStyle)}&lang=${user?.lang || 'fr'}`
      );
      setMultiScans(res.scans || []);
    } catch (err: any) {
      showToast(err.message, 'error');
    } finally {
      setLoadingScan(false);
    }
  }, [selectedTimeframe, selectedStyle, user?.lang, showToast]);

  const loadHistoryAndJournal = useCallback(async () => {
    try {
      const res = await apiFetch('/api/signals/history?scope=all&limit=50');
      setSignalHistory(res.signals || []);
      setDecisionJournal(res.decision_journal || []);
    } catch (err: any) {
      console.error(err);
    }
  }, []);

  const loadTickets = useCallback(async () => {
    try {
      const res = await apiFetch('/api/support/tickets');
      setTickets(res.tickets || []);
    } catch (err: any) {
      console.error(err);
    }
  }, []);

  const loadAdminOverview = useCallback(async () => {
    try {
      const res = await apiFetch('/api/admin/overview');
      setAdminData(res);
      setDoctorReport(res.log_doctor || '');
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  }, [showToast]);

  const loadLiveAccountAndOrders = useCallback(async () => {
    setLoadingLiveAccount(true);
    try {
      const [cfgRes, accRes] = await Promise.all([
        apiFetch('/api/trading/config'),
        apiFetch('/api/trading/account'),
      ]);
      setTradingCfg(cfgRes.config);
      setLiveTrades(cfgRes.live_trades || { open: [], closed: [] });
      if (accRes.connected && accRes.account) {
        setLiveAccount(accRes.account);
      } else {
        setLiveAccount(null);
      }
      setLiveOpenOrders(accRes.open_orders || []);
    } catch (err: any) {
      console.error(err);
    } finally {
      setLoadingLiveAccount(false);
    }
  }, []);

  useEffect(() => {
    loadUserAndCoreData();
    runAnalysis('BTCUSDT', '1h', 'day');
    const intervalId = setInterval(() => {
      apiFetch('/api/trading/config')
        .then((res) => {
          setTradingCfg(res.config);
          setLiveTrades(res.live_trades || { open: [], closed: [] });
        })
        .catch(() => {});
    }, 15000);
    return () => clearInterval(intervalId);
  }, []);

  useEffect(() => {
    if (activeTab === 'safety') loadLiveAccountAndOrders();
    if (activeTab === 'history') loadHistoryAndJournal();
    if (activeTab === 'account') loadTickets();
    if (activeTab === 'admin') {
      loadAdminOverview();
      loadTickets();
    }
  }, [activeTab, loadLiveAccountAndOrders, loadHistoryAndJournal, loadTickets, loadAdminOverview]);

  // Handlers
  const handleQuickSwitch = async (targetUid: number) => {
    try {
      const res = await apiFetch('/api/auth/quick-switch', {
        method: 'POST',
        body: JSON.stringify({ user_id: targetUid }),
      });
      setStoredSession(res.token, res.user.user_id);
      setUser(res.user);
      setViewMode('workspace');
      await loadUserAndCoreData();
      showToast(`Connecté en tant que ${res.user.display_name} (${res.user.role.toUpperCase()})`, 'success');
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  const handleAuthSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const endpoint = authModal === 'login' ? '/api/auth/login' : '/api/auth/register';
      const res = await apiFetch(endpoint, {
        method: 'POST',
        body: JSON.stringify({
          email: authEmail,
          password: authPassword,
          display_name: authName,
          telegram_handle: authTelegram,
        }),
      });
      setStoredSession(res.token, res.user.user_id);
      setUser(res.user);
      setAuthModal(null);
      setViewMode('workspace');
      await loadUserAndCoreData();
      showToast(`Bienvenue sur Bitsure Teddy, ${res.user.display_name}`, 'success');
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  const handleOpenPaperOrder = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await apiFetch('/api/paper/open', {
        method: 'POST',
        body: JSON.stringify({
          symbol: selectedSymbol,
          side: orderSide,
          qty: parseFloat(orderQty) || 0.02,
          leverage: parseFloat(orderLeverage) || 1,
          entry_price: analysis?.current_price || 0,
          sl: parseFloat(orderSL) || 0,
          tp: parseFloat(orderTP) || 0,
        }),
      });
      setPaperStats(res.stats);
      setOpenPaper(res.open_positions || []);
      showToast(
        `Position Paper ${orderSide} ouverte sur ${selectedSymbol} (${orderQty} @ ${analysis?.current_price?.toLocaleString()})`,
        'success'
      );
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  const handleClosePaperPosition = async (positionId: string) => {
    try {
      const res = await apiFetch('/api/paper/close', {
        method: 'POST',
        body: JSON.stringify({ position_id: positionId }),
      });
      setPaperStats(res.stats);
      setOpenPaper(res.open_positions || []);
      setClosedPaper(res.closed_positions || []);
      showToast(`Position #${positionId} clôturée au prix du marché.`, 'success');
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  const handleResetPaperAccount = async () => {
    try {
      const res = await apiFetch('/api/paper/reset', {
        method: 'POST',
        body: JSON.stringify({ amount: 10000 }),
      });
      setPaperStats(res.stats);
      setOpenPaper(res.open_positions || []);
      setClosedPaper(res.closed_positions || []);
      showToast('Portefeuille Paper Trading réinitialisé à 10 000.00 USDT.', 'info');
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  const handleAddAlert = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await apiFetch('/api/alerts/add', {
        method: 'POST',
        body: JSON.stringify({
          symbol: newAlertSymbol,
          condition: newAlertCond,
          price: parseFloat(newAlertPrice),
        }),
      });
      setAlerts(res.alerts || []);
      showToast(`Alerte enregistrée : ${newAlertSymbol} ${newAlertCond.toUpperCase()} ${newAlertPrice}`, 'success');
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  const handleDeleteAlert = async (alertId: number) => {
    try {
      const res = await apiFetch('/api/alerts/delete', {
        method: 'POST',
        body: JSON.stringify({ alert_id: alertId }),
      });
      setAlerts(res.alerts || []);
      showToast('Alerte supprimée.', 'info');
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  const handleUpdateTradingConfig = async (patch: Partial<TradingConfigState> & { pin?: string }) => {
    try {
      await apiFetch('/api/trading/config', {
        method: 'POST',
        body: JSON.stringify(patch),
      });
      const cfgRes = await apiFetch('/api/trading/config');
      setTradingCfg(cfgRes.config);
      setLiveTrades(cfgRes.live_trades || { open: [], closed: [] });
      showToast('Paramètres de trading mis à jour.', 'success');
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  const handleSafetyAction = async (action: string, reason?: string) => {
    try {
      const res = await apiFetch('/api/trading/safety', {
        method: 'POST',
        body: JSON.stringify({ action, reason, pin: safetyPinInput }),
      });
      const cfgRes = await apiFetch('/api/trading/config');
      setTradingCfg(cfgRes.config);
      setLiveTrades(cfgRes.live_trades || { open: [], closed: [] });
      showToast(res.message, 'success');
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  const handleSaveBinanceKeys = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await apiFetch('/api/trading/credentials', {
        method: 'POST',
        body: JSON.stringify({
          api_key: binanceKey,
          api_secret: binanceSecret,
          testnet: binanceTestnet,
        }),
      });
      await loadLiveAccountAndOrders();
      setBinanceKey('');
      setBinanceSecret('');
      showToast(res.message, res.credentials_valid ? 'success' : 'error');
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  const handleTestBinanceConnection = async () => {
    setTestingApiConn(true);
    try {
      const res = await apiFetch('/api/trading/test-connection', { method: 'POST' });
      await loadLiveAccountAndOrders();
      showToast(res.message, res.credentials_valid ? 'success' : 'error');
    } catch (err: any) {
      showToast(err.message, 'error');
    } finally {
      setTestingApiConn(false);
    }
  };

  const handleCloseLivePosition = async (tradeId: number) => {
    try {
      const res = await apiFetch('/api/trading/close-position', {
        method: 'POST',
        body: JSON.stringify({ trade_id: tradeId }),
      });
      await loadLiveAccountAndOrders();
      showToast(res.message, 'success');
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  const handleCancelLiveOrder = async (symbol: string, orderId: string) => {
    try {
      const res = await apiFetch('/api/trading/cancel-order', {
        method: 'POST',
        body: JSON.stringify({ symbol, order_id: orderId }),
      });
      await loadLiveAccountAndOrders();
      showToast(res.message, 'info');
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  const handleLiveOrderAction = async (action: 'validate' | 'execute') => {
    try {
      const res = await apiFetch('/api/trading/live-order', {
        method: 'POST',
        body: JSON.stringify({
          action,
          symbol: liveOrderSymbol,
          side: liveOrderSide,
          amount: parseFloat(liveOrderAmount) || 0,
          amount_mode: liveOrderAmountMode,
          order_type: liveOrderType,
          entry_price: liveOrderType === 'LIMIT' ? parseFloat(liveOrderEntryPrice) || null : null,
          sl_price: liveOrderSL ? parseFloat(liveOrderSL) : null,
          tp_price: liveOrderTP ? parseFloat(liveOrderTP) : null,
          leverage: parseInt(liveOrderLeverage, 10) || 1,
          margin_type: liveOrderMarginType,
          reduce_only: liveOrderReduceOnly,
        }),
      });
      if (action === 'validate') {
        setLiveOrderDraftCheck(res.checks);
        showToast(res.message, 'info');
      } else {
        setLiveOrderDraftCheck(null);
        await loadLiveAccountAndOrders();
        showToast(res.message, 'success');
      }
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  const handleRedeemPromo = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await apiFetch('/api/user/promo', {
        method: 'POST',
        body: JSON.stringify({ code: promoCodeInput }),
      });
      setUser(res.user);
      setPromoCodeInput('');
      showToast(res.message, res.ok ? 'success' : 'error');
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  const handleGenerateBinancePay = async (plan: 'pro' | 'vip') => {
    try {
      const res = await apiFetch('/api/user/binance-pay', {
        method: 'POST',
        body: JSON.stringify({ plan }),
      });
      setPaymentInfo(res);
      setUser(res.user);
      showToast(`Mémo de paiement Binance généré : ${res.memo}`, 'info');
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  const handleSavePin = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await apiFetch('/api/user/pin', {
        method: 'POST',
        body: JSON.stringify({ action: 'set', pin: newPin, old_pin: oldPin }),
      });
      setUser(res.user);
      setNewPin('');
      setOldPin('');
      showToast(res.message, 'success');
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  const handleCreateSupportTicket = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await apiFetch('/api/support/tickets', {
        method: 'POST',
        body: JSON.stringify({ action: 'create', subject: ticketSubject, message: ticketMessage }),
      });
      setTicketSubject('');
      setTicketMessage('');
      await loadTickets();
      showToast(res.message, 'success');
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  if (viewMode === 'landing') {
    return (
      <>
        <LandingPage
          onEnterWorkspace={() => setViewMode('workspace')}
          onQuickLogin={handleQuickSwitch}
          onOpenAuthModal={(m) => setAuthModal(m)}
          demoAccounts={demoAccounts}
        />
        {authModal && (
          <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-[#111827] border border-white/15 rounded-xl max-w-md w-full p-6 space-y-5">
              <div className="flex items-center justify-between">
                <h3 className="font-display text-lg font-bold text-[#F1F5F9]">
                  {authModal === 'login' ? 'Connexion Bitsure Teddy' : 'Créer un compte Bitsure Teddy'}
                </h3>
                <button onClick={() => setAuthModal(null)} className="text-[#64748B] hover:text-[#F1F5F9]">
                  <XCircle className="w-5 h-5" />
                </button>
              </div>
              <form onSubmit={handleAuthSubmit} className="space-y-3.5 text-sm">
                {authModal === 'register' && (
                  <>
                    <div>
                      <label className="block text-xs text-[#94A3B8] mb-1">Nom ou Pseudonyme</label>
                      <input
                        type="text"
                        value={authName}
                        onChange={(e) => setAuthName(e.target.value)}
                        placeholder="Alex Quant"
                        className="w-full px-3 py-2 bg-[#090D16] border border-white/10 rounded-lg text-[#F1F5F9]"
                        required
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-[#94A3B8] mb-1">Identifiant Telegram (optionnel)</label>
                      <input
                        type="text"
                        value={authTelegram}
                        onChange={(e) => setAuthTelegram(e.target.value)}
                        placeholder="@votre_pseudo"
                        className="w-full px-3 py-2 bg-[#090D16] border border-white/10 rounded-lg text-[#F1F5F9]"
                      />
                    </div>
                  </>
                )}
                <div>
                  <label className="block text-xs text-[#94A3B8] mb-1">Adresse Email</label>
                  <input
                    type="email"
                    value={authEmail}
                    onChange={(e) => setAuthEmail(e.target.value)}
                    placeholder="pro@bitsure.io"
                    className="w-full px-3 py-2 bg-[#090D16] border border-white/10 rounded-lg text-[#F1F5F9]"
                    required
                  />
                </div>
                <div>
                  <label className="block text-xs text-[#94A3B8] mb-1">Mot de passe</label>
                  <input
                    type="password"
                    value={authPassword}
                    onChange={(e) => setAuthPassword(e.target.value)}
                    placeholder="••••••••"
                    className="w-full px-3 py-2 bg-[#090D16] border border-white/10 rounded-lg text-[#F1F5F9]"
                    required
                  />
                </div>
                <button
                  type="submit"
                  className="w-full py-2.5 bg-[#10B981] hover:bg-[#059669] text-[#090D16] font-semibold rounded-lg transition-colors"
                >
                  {authModal === 'login' ? 'Se connecter' : 'Activer mon compte'}
                </button>
              </form>
            </div>
          </div>
        )}
      </>
    );
  }

  const ind = analysis?.indicators || {};
  const tfTrends = ind.timeframe_trends || {};
  const tfAlign = ind.tf_alignment || {};

  return (
    <div className="min-h-screen bg-[#090D16] text-[#F1F5F9] flex">
      {/* Left Single Navigation Sidebar */}
      <aside className="w-64 shrink-0 border-r border-white/[0.07] bg-[#0B101B] flex flex-col justify-between">
        <div>
          {/* Brand Logo */}
          <div className="h-16 px-5 border-b border-white/[0.07] flex items-center justify-between">
            <button
              onClick={() => setViewMode('landing')}
              className="flex items-center gap-2.5 text-left group"
            >
              <div className="w-8 h-8 rounded-lg bg-[#10B981]/15 border border-[#10B981]/40 flex items-center justify-center text-[#10B981] font-display font-bold">
                B
              </div>
              <div>
                <div className="font-display font-bold text-sm tracking-tight text-[#F1F5F9] group-hover:text-[#10B981] transition-colors">
                  BITSURE TEDDY
                </div>
                <div className="text-[10px] font-mono-tabular text-[#64748B]">QUANT ENGINE v2.0</div>
              </div>
            </button>
          </div>

          {/* Primary Navigation Items */}
          <nav className="p-3 space-y-1">
            {[
              { id: 'intelligence', label: 'Market Intelligence', icon: Activity },
              { id: 'paper', label: 'Paper Trading', icon: Layers, count: openPaper.length },
              { id: 'alerts', label: 'Alertes & Watchlist', icon: Bell, count: alerts.length },
              {
                id: 'safety',
                label: 'Auto-Trade & Safety',
                icon: ShieldCheck,
                warn: tradingCfg?.safety_lock || tradingCfg?.safety_warn,
                apiConnected: Boolean(tradingCfg?.credentials_valid),
              },
              { id: 'history', label: 'Historique & Journal', icon: BookOpen },
              { id: 'account', label: 'Compte, Plans & PIN', icon: CreditCard },
              { id: 'admin', label: 'Admin & Log Doctor', icon: Terminal },
            ].map((item) => {
              const Icon = item.icon;
              const active = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => setActiveTab(item.id as ActiveTab)}
                  className={`w-full px-3 py-2.5 rounded-lg text-xs font-medium flex items-center justify-between transition-colors ${
                    active
                      ? 'bg-[#10B981]/15 text-[#10B981] border border-[#10B981]/30'
                      : 'text-[#94A3B8] hover:text-[#F1F5F9] hover:bg-white/[0.04] border border-transparent'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <Icon className="w-4 h-4 shrink-0" />
                    <span className="truncate">{item.label}</span>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {item.id === 'safety' && (
                      <span
                        title={
                          item.apiConnected
                            ? `Clés API Binance chargées et opérationnelles (${tradingCfg?.testnet ? 'TESTNET' : 'LIVE'})`
                            : 'Clés API Binance absentes ou non opérationnelles'
                        }
                        className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-mono-tabular font-bold border ${
                          item.apiConnected
                            ? 'bg-[#10B981]/15 text-[#10B981] border-[#10B981]/40'
                            : 'bg-[#F43F5E]/15 text-[#FB7185] border-[#F43F5E]/40'
                        }`}
                      >
                        <span
                          className={`w-1.5 h-1.5 rounded-full ${
                            item.apiConnected ? 'bg-[#10B981] animate-pulse' : 'bg-[#F43F5E]'
                          }`}
                        />
                        {item.apiConnected ? 'API OK' : 'API OFF'}
                      </span>
                    )}
                    {item.count !== undefined && item.count > 0 && (
                      <span className="font-mono-tabular text-[11px] text-[#94A3B8]">{item.count}</span>
                    )}
                    {item.warn && <span className="w-2 h-2 rounded-full bg-[#F59E0B]" title="Avertissement ou Safety Lock actif" />}
                  </div>
                </button>
              );
            })}
          </nav>

          {/* Watchlist Quick Selector */}
          <div className="px-4 pt-4 pb-2">
            <div className="text-[11px] font-mono-tabular uppercase tracking-wider text-[#64748B] mb-2">
              Marchés Documentés
            </div>
            <div className="space-y-1">
              {SYMBOLS.map((s) => {
                const isSelected = selectedSymbol === s.id;
                return (
                  <button
                    key={s.id}
                    onClick={() => {
                      setSelectedSymbol(s.id);
                      setActiveTab('intelligence');
                      runAnalysis(s.id, selectedTimeframe, selectedStyle);
                    }}
                    className={`w-full px-2.5 py-1.5 rounded text-xs flex items-center justify-between transition-colors ${
                      isSelected
                        ? 'bg-[#1E293B] text-[#F1F5F9] font-medium'
                        : 'text-[#94A3B8] hover:bg-white/[0.03] hover:text-[#F1F5F9]'
                    }`}
                  >
                    <span className="font-mono-tabular">{s.label}</span>
                    <ChevronRight className="w-3.5 h-3.5 text-[#64748B]" />
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Bottom User Profile & Quick Role Switcher */}
        <div className="p-3.5 border-t border-white/[0.07] bg-[#090D16]/60 space-y-3">
          {user && (
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-[#F1F5F9] truncate">{user.display_name}</span>
                <span className="text-[10px] font-mono-tabular uppercase px-1.5 py-0.5 rounded bg-[#10B981]/15 text-[#10B981] border border-[#10B981]/30">
                  {user.role}
                </span>
              </div>
              <div className="text-[11px] text-[#64748B] font-mono-tabular flex items-center justify-between">
                <span>{user.telegram_handle}</span>
                <span>
                  Quota: {user.remaining_requests < 0 || user.remaining_requests >= 999 ? 'Illimité' : `${user.remaining_requests}/${user.daily_limit}`}
                </span>
              </div>
            </div>
          )}

          <div>
            <label className="block text-[10px] uppercase tracking-wider text-[#64748B] mb-1">
              Changer de profil (Démo)
            </label>
            <select
              value={user?.user_id || 100201}
              onChange={(e) => handleQuickSwitch(Number(e.target.value))}
              className="w-full px-2.5 py-1.5 text-xs bg-[#111827] border border-white/10 rounded text-[#F1F5F9] font-mono-tabular"
            >
              {demoAccounts.map((d) => (
                <option key={d.user_id} value={d.user_id}>
                  {d.label}
                </option>
              ))}
            </select>
          </div>

          <button
            onClick={() => setViewMode('landing')}
            className="w-full py-1.5 text-xs text-[#94A3B8] hover:text-[#F1F5F9] border border-white/10 rounded hover:bg-white/[0.04] transition-colors"
          >
            Présentation & Tarifs
          </button>
        </div>
      </aside>

      {/* Main Workspace Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top Utility & Market Bar */}
        <header className="h-16 px-6 border-b border-white/[0.07] bg-[#0B101B]/90 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 flex-wrap">
            <select
              value={selectedSymbol}
              onChange={(e) => {
                setSelectedSymbol(e.target.value);
                runAnalysis(e.target.value, selectedTimeframe, selectedStyle);
              }}
              className="px-3 py-1.5 bg-[#111827] border border-white/15 rounded-lg text-xs font-mono-tabular font-semibold text-[#F1F5F9]"
            >
              {SYMBOLS.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>

            <div className="flex items-center bg-[#111827] border border-white/10 rounded-lg p-0.5">
              {TIMEFRAMES.map((tf) => (
                <button
                  key={tf}
                  onClick={() => {
                    setSelectedTimeframe(tf);
                    runAnalysis(selectedSymbol, tf, selectedStyle);
                  }}
                  className={`px-2.5 py-1 rounded-md text-xs font-mono-tabular transition-colors ${
                    selectedTimeframe === tf
                      ? 'bg-[#10B981] text-[#090D16] font-semibold'
                      : 'text-[#94A3B8] hover:text-[#F1F5F9]'
                  }`}
                >
                  {tf.toUpperCase()}
                </button>
              ))}
            </div>

            <select
              value={selectedStyle}
              onChange={(e) => {
                setSelectedStyle(e.target.value);
                runAnalysis(selectedSymbol, selectedTimeframe, e.target.value);
              }}
              className="px-3 py-1.5 bg-[#111827] border border-white/10 rounded-lg text-xs text-[#F1F5F9]"
            >
              {STYLES.map((st) => (
                <option key={st.id} value={st.id}>
                  Style : {st.label}
                </option>
              ))}
            </select>

            <button
              onClick={() => runAnalysis(selectedSymbol, selectedTimeframe, selectedStyle)}
              disabled={loadingAnalysis}
              className="px-3 py-1.5 bg-[#1E293B] hover:bg-[#334155] border border-white/10 rounded-lg text-xs text-[#F1F5F9] flex items-center gap-1.5 transition-colors"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loadingAnalysis ? 'animate-spin text-[#10B981]' : ''}`} />
              <span>Actualiser</span>
            </button>
          </div>

          <div className="flex items-center gap-4 text-xs">
            {paperStats && (
              <div className="hidden lg:flex items-center gap-4 font-mono-tabular bg-[#111827] border border-white/[0.07] px-3.5 py-1.5 rounded-lg">
                <span className="text-[#94A3B8]">
                  Équité Paper : <strong className="text-[#F1F5F9]">{Number(paperStats.equity ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USDT</strong>
                </span>
                <span className={(paperStats.total_pnl ?? 0) >= 0 ? 'text-[#10B981]' : 'text-[#F43F5E]'}>
                  PnL : {(paperStats.total_pnl ?? 0) >= 0 ? '+' : ''}
                  {Number(paperStats.total_pnl ?? 0).toFixed(2)} USDT
                </span>
              </div>
            )}

            <button
              onClick={() => {
                const nextLang = user?.lang === 'fr' ? 'en' : 'fr';
                apiFetch('/api/user/preferences', {
                  method: 'POST',
                  body: JSON.stringify({ lang: nextLang }),
                }).then((r) => {
                  setUser(r.user);
                  runAnalysis(selectedSymbol, selectedTimeframe, selectedStyle);
                });
              }}
              className="px-2.5 py-1.5 bg-[#111827] border border-white/10 rounded-lg font-mono-tabular uppercase text-[#94A3B8] hover:text-[#F1F5F9]"
            >
              {user?.lang || 'fr'}
            </button>
          </div>
        </header>

        {/* Toast Notification Banner */}
        {toast && (
          <div
            className={`mx-6 mt-4 px-4 py-2.5 rounded-lg border text-xs flex items-center justify-between ${
              toast.type === 'success'
                ? 'bg-[#10B981]/15 border-[#10B981]/40 text-[#34D399]'
                : toast.type === 'error'
                ? 'bg-[#F43F5E]/15 border-[#F43F5E]/40 text-[#FB7185]'
                : 'bg-[#3B82F6]/15 border-[#3B82F6]/40 text-[#60A5FA]'
            }`}
          >
            <span>{toast.text}</span>
            <button onClick={() => setToast(null)} className="opacity-70 hover:opacity-100">
              ✕
            </button>
          </div>
        )}

        {/* Main Scrollable Content */}
        <main className="p-6 space-y-6 max-w-[1600px] w-full mx-auto">
          {/* =========================================================
              TAB 1: MARKET INTELLIGENCE & TEDDY SCORE WORKSPACE
             ========================================================= */}
          {activeTab === 'intelligence' && (
            <>
              {/* Top 4 KPI Cards (Max 3 data points per card, 24px gap) */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
                {/* KPI 1: Live Price & Market Status */}
                <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-5 space-y-2">
                  <div className="flex items-center justify-between text-xs text-[#94A3B8]">
                    <span>Cours Temps Réel ({analysis?.symbol || selectedSymbol})</span>
                    <span className="font-mono-tabular text-[#10B981]">
                      {analysis?.market_status?.is_open ? '● OUVERT' : '○ FERMÉ'}
                    </span>
                  </div>
                  <div className="font-mono-tabular text-2xl font-bold text-[#F1F5F9]">
                    {analysis?.current_price
                      ? analysis.current_price.toLocaleString('en-US', {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 2,
                        })
                      : '—'}{' '}
                    <span className="text-xs font-normal text-[#64748B]">USD</span>
                  </div>
                  <div className="text-xs text-[#64748B] font-mono-tabular">
                    ATR(14) : {ind.atr ? ind.atr.toFixed(2) : '—'} • Classe : {(analysis?.asset_class || 'crypto').toUpperCase()}
                  </div>
                </div>

                {/* KPI 2: Signal & Teddy Score */}
                <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-5 space-y-2">
                  <div className="flex items-center justify-between text-xs text-[#94A3B8]">
                    <span>Signal & Teddy Score</span>
                    <span className="font-mono-tabular text-[#94A3B8]">Confiance : {analysis?.confidence || '—'}</span>
                  </div>
                  <div className="flex items-baseline gap-3">
                    <span
                      className={`font-display text-2xl font-bold ${
                        analysis?.signal === 'BUY'
                          ? 'text-[#10B981]'
                          : analysis?.signal === 'SELL'
                          ? 'text-[#F43F5E]'
                          : 'text-[#F59E0B]'
                      }`}
                    >
                      {analysis?.signal || 'WAIT'}
                    </span>
                    <span className="font-mono-tabular text-xl font-semibold text-[#F1F5F9]">
                      {analysis?.teddy_score ?? 0} <span className="text-xs text-[#64748B]">/ 100</span>
                    </span>
                  </div>
                  <div className="w-full h-1.5 bg-[#090D16] rounded-full overflow-hidden">
                    <div
                      className="h-full bg-[#10B981] transition-all"
                      style={{ width: `${Math.min(100, Math.max(8, analysis?.teddy_score || 0))}%` }}
                    />
                  </div>
                </div>

                {/* KPI 3: Multi-Timeframe Hierarchy */}
                <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-5 space-y-2">
                  <div className="flex items-center justify-between text-xs text-[#94A3B8]">
                    <span>Alignement Multi-Timeframes</span>
                    <span className="font-mono-tabular text-[#F59E0B]">
                      {tfAlign.status || 'NEUTRAL'} ({tfAlign.modifier >= 0 ? `+${tfAlign.modifier || 0}` : tfAlign.modifier} pts)
                    </span>
                  </div>
                  <div className="grid grid-cols-3 gap-2 pt-1 font-mono-tabular text-xs">
                    {(['1h', '4h', '1d'] as const).map((k) => {
                      const val = tfTrends[k] || 'NEUTRE';
                      return (
                        <div key={k} className="bg-[#090D16] border border-white/[0.06] rounded px-2.5 py-1.5 text-center">
                          <div className="text-[10px] text-[#64748B] uppercase">{k}</div>
                          <div
                            className={`font-semibold text-[11px] ${
                              val === 'HAUSSIER'
                                ? 'text-[#10B981]'
                                : val === 'BAISSIER'
                                ? 'text-[#F43F5E]'
                                : 'text-[#94A3B8]'
                            }`}
                          >
                            {val}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* KPI 4: Risk Sizing Recommendation */}
                <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-5 space-y-2">
                  <div className="flex items-center justify-between text-xs text-[#94A3B8]">
                    <span>Taille Position Recommandée</span>
                    <span className="font-mono-tabular text-[#10B981]">
                      Risque {analysis?.sizing_recommendation?.risk_pct || 1}%
                    </span>
                  </div>
                  <div className="font-mono-tabular text-2xl font-bold text-[#F1F5F9]">
                    {analysis?.sizing_recommendation?.position_size ?? 0}{' '}
                    <span className="text-xs font-normal text-[#64748B]">unités</span>
                  </div>
                  <div className="text-xs text-[#64748B] font-mono-tabular">
                    Risque max : {analysis?.sizing_recommendation?.risk_amount_usd ?? 100} USDT • Marge :{' '}
                    {analysis?.sizing_recommendation?.margin_required_usd ?? 0} USDT
                  </div>
                </div>
              </div>

              {/* Main Chart + Right Signal Diagnostic & Quick Paper Execution */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                <div className="lg:col-span-8 space-y-4">
                  <PriceChart
                    candles={analysis?.candles || []}
                    symbol={analysis?.symbol || selectedSymbol}
                    timeframe={selectedTimeframe}
                    sl={analysis?.sl}
                    tp1={analysis?.tp1}
                    tp2={analysis?.tp2}
                    support={ind.support}
                    resistance={ind.resistance}
                  />

                  {/* Technical Indicators Breakdown Strip */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                    <div className="bg-[#111827] border border-white/[0.07] rounded-lg p-3.5">
                      <div className="text-xs text-[#64748B]">RSI (14) & Stochastique</div>
                      <div className="font-mono-tabular text-base font-semibold text-[#F1F5F9] mt-1">
                        {ind.rsi ? ind.rsi.toFixed(2) : '—'}
                      </div>
                      <div className="text-[11px] text-[#94A3B8] mt-0.5">
                        {ind.rsi > 70 ? 'Zone de surachat (>70)' : ind.rsi < 30 ? 'Zone de survente (<30)' : 'Zone neutre équilibrée'}
                      </div>
                    </div>

                    <div className="bg-[#111827] border border-white/[0.07] rounded-lg p-3.5">
                      <div className="text-xs text-[#64748B]">MACD (12, 26, 9)</div>
                      <div className="font-mono-tabular text-base font-semibold text-[#F1F5F9] mt-1">
                        {ind.macd ? ind.macd.toFixed(2) : '—'}
                      </div>
                      <div className="text-[11px] text-[#94A3B8] mt-0.5 font-mono-tabular">
                        Hist: {ind.macd_hist ? ind.macd_hist.toFixed(2) : '—'}
                      </div>
                    </div>

                    <div className="bg-[#111827] border border-white/[0.07] rounded-lg p-3.5">
                      <div className="text-xs text-[#64748B]">ADX (14) • Force Tendance</div>
                      <div className="font-mono-tabular text-base font-semibold text-[#F1F5F9] mt-1">
                        {ind.adx ? ind.adx.toFixed(2) : '—'}{' '}
                        <span className="text-xs text-[#10B981]">{ind.adx_rising ? '↑ En hausse' : '↓ En repli'}</span>
                      </div>
                      <div className="text-[11px] text-[#94A3B8] mt-0.5 font-mono-tabular">
                        +DI: {ind.plus_di ? ind.plus_di.toFixed(1) : '—'} / -DI: {ind.minus_di ? ind.minus_di.toFixed(1) : '—'}
                      </div>
                    </div>

                    <div className="bg-[#111827] border border-white/[0.07] rounded-lg p-3.5">
                      <div className="text-xs text-[#64748B]">Support / Résistance (50p)</div>
                      <div className="font-mono-tabular text-sm font-semibold text-[#10B981] mt-1">
                        S: {ind.support ? ind.support.toLocaleString('en-US', { maximumFractionDigits: 2 }) : '—'}
                      </div>
                      <div className="font-mono-tabular text-sm font-semibold text-[#F59E0B]">
                        R: {ind.resistance ? ind.resistance.toLocaleString('en-US', { maximumFractionDigits: 2 }) : '—'}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Right Column: Signal Explainability & Direct Paper Trade Box */}
                <div className="lg:col-span-4 space-y-6">
                  {/* Explainability Box */}
                  <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-5 space-y-4">
                    <div className="flex items-center justify-between border-b border-white/[0.07] pb-3">
                      <h3 className="font-display font-semibold text-sm text-[#F1F5F9]">
                        Diagnostic du Moteur Teddy
                      </h3>
                      <span className="font-mono-tabular text-xs text-[#94A3B8]">
                        Statut : {analysis?.validation_status || '—'}
                      </span>
                    </div>

                    <div className="p-3.5 rounded-lg bg-[#090D16] border border-white/[0.06] text-xs text-[#F1F5F9] leading-relaxed">
                      {analysis?.reason || 'Analyse en cours...'}
                    </div>

                    {/* Levels SL / TP1 / TP2 / RR */}
                    <div className="grid grid-cols-2 gap-2.5 text-xs font-mono-tabular">
                      <div className="p-2.5 rounded bg-[#090D16] border border-white/[0.05]">
                        <div className="text-[#64748B] text-[10px]">STOP LOSS (ATR)</div>
                        <div className="text-[#F43F5E] font-semibold mt-0.5">
                          {analysis?.sl ? analysis.sl.toLocaleString('en-US', { maximumFractionDigits: 2 }) : 'Non actif (WAIT)'}
                        </div>
                      </div>
                      <div className="p-2.5 rounded bg-[#090D16] border border-white/[0.05]">
                        <div className="text-[#64748B] text-[10px]">TAKE PROFIT 1</div>
                        <div className="text-[#10B981] font-semibold mt-0.5">
                          {analysis?.tp1 ? analysis.tp1.toLocaleString('en-US', { maximumFractionDigits: 2 }) : 'Non actif (WAIT)'}
                        </div>
                      </div>
                      <div className="p-2.5 rounded bg-[#090D16] border border-white/[0.05]">
                        <div className="text-[#64748B] text-[10px]">TAKE PROFIT 2</div>
                        <div className="text-[#34D399] font-semibold mt-0.5">
                          {analysis?.tp2 ? analysis.tp2.toLocaleString('en-US', { maximumFractionDigits: 2 }) : '—'}
                        </div>
                      </div>
                      <div className="p-2.5 rounded bg-[#090D16] border border-white/[0.05]">
                        <div className="text-[#64748B] text-[10px]">RATIO R:R</div>
                        <div className="text-[#F59E0B] font-semibold mt-0.5">
                          {analysis?.rr_ratio ? `1 : ${analysis.rr_ratio.toFixed(2)}` : '—'}
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Quick Paper Order Ticket */}
                  <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-5 space-y-4">
                    <div className="flex items-center justify-between border-b border-white/[0.07] pb-3">
                      <h3 className="font-display font-semibold text-sm text-[#F1F5F9]">
                        Exécution Rapide Paper Trading
                      </h3>
                      <span className="font-mono-tabular text-xs text-[#10B981]">
                        Cap: {Number(paperStats?.capital ?? 10000).toFixed(0)} USDT
                      </span>
                    </div>

                    <form onSubmit={handleOpenPaperOrder} className="space-y-3 text-xs">
                      <div className="grid grid-cols-2 gap-2">
                        <button
                          type="button"
                          onClick={() => setOrderSide('BUY')}
                          className={`py-2 rounded-lg font-semibold border transition-colors ${
                            orderSide === 'BUY'
                              ? 'bg-[#10B981] text-[#090D16] border-[#10B981]'
                              : 'bg-[#090D16] text-[#94A3B8] border-white/10'
                          }`}
                        >
                          LONG / BUY
                        </button>
                        <button
                          type="button"
                          onClick={() => setOrderSide('SELL')}
                          className={`py-2 rounded-lg font-semibold border transition-colors ${
                            orderSide === 'SELL'
                              ? 'bg-[#F43F5E] text-white border-[#F43F5E]'
                              : 'bg-[#090D16] text-[#94A3B8] border-white/10'
                          }`}
                        >
                          SHORT / SELL
                        </button>
                      </div>

                      <div className="grid grid-cols-2 gap-2.5">
                        <div>
                          <label className="block text-[11px] text-[#94A3B8] mb-1">Quantité ({selectedSymbol})</label>
                          <input
                            type="number"
                            step="any"
                            value={orderQty}
                            onChange={(e) => setOrderQty(e.target.value)}
                            className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/10 rounded font-mono-tabular text-[#F1F5F9]"
                            required
                          />
                        </div>
                        <div>
                          <label className="block text-[11px] text-[#94A3B8] mb-1">Levier (1x–20x)</label>
                          <input
                            type="number"
                            min="1"
                            max="20"
                            value={orderLeverage}
                            onChange={(e) => setOrderLeverage(e.target.value)}
                            className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/10 rounded font-mono-tabular text-[#F1F5F9]"
                            required
                          />
                        </div>
                      </div>

                      <div className="grid grid-cols-2 gap-2.5">
                        <div>
                          <label className="block text-[11px] text-[#94A3B8] mb-1">Stop Loss (SL)</label>
                          <input
                            type="number"
                            step="any"
                            value={orderSL}
                            onChange={(e) => setOrderSL(e.target.value)}
                            className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/10 rounded font-mono-tabular text-[#F43F5E]"
                            required
                          />
                        </div>
                        <div>
                          <label className="block text-[11px] text-[#94A3B8] mb-1">Take Profit (TP)</label>
                          <input
                            type="number"
                            step="any"
                            value={orderTP}
                            onChange={(e) => setOrderTP(e.target.value)}
                            className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/10 rounded font-mono-tabular text-[#10B981]"
                            required
                          />
                        </div>
                      </div>

                      <button
                        type="submit"
                        className="w-full py-2.5 bg-[#10B981] hover:bg-[#059669] text-[#090D16] font-semibold rounded-lg transition-colors"
                      >
                        Ouvrir Position Paper ({selectedSymbol})
                      </button>
                    </form>
                  </div>
                </div>
              </div>

              {/* Multi-Symbol Scanner Section */}
              <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-5 space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h3 className="font-display font-semibold text-base text-[#F1F5F9]">
                      Scanner Multi-Marchés (BTCUSDT • ETHUSDT • XAUUSD)
                    </h3>
                    <p className="text-xs text-[#64748B]">
                      Analyse simultanée de la confluence technique sur les actifs documentés.
                    </p>
                  </div>
                  <button
                    onClick={runMultiScan}
                    disabled={loadingScan}
                    className="px-4 py-2 bg-[#10B981]/15 hover:bg-[#10B981]/25 border border-[#10B981]/40 text-[#10B981] rounded-lg text-xs font-semibold flex items-center gap-2 transition-colors"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${loadingScan ? 'animate-spin' : ''}`} />
                    <span>Lancer le Scan Global ({selectedTimeframe.toUpperCase()})</span>
                  </button>
                </div>

                {multiScans.length > 0 && (
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
                    {multiScans.map((sc) => (
                      <div
                        key={sc.symbol}
                        onClick={() => {
                          setSelectedSymbol(sc.symbol);
                          runAnalysis(sc.symbol, selectedTimeframe, selectedStyle);
                        }}
                        className="p-4 rounded-lg bg-[#090D16] border border-white/[0.07] hover:border-[#10B981]/40 cursor-pointer transition-colors space-y-2"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-mono-tabular font-bold text-sm text-[#F1F5F9]">{sc.symbol}</span>
                          <span
                            className={`font-mono-tabular text-xs font-semibold ${
                              sc.signal === 'BUY'
                                ? 'text-[#10B981]'
                                : sc.signal === 'SELL'
                                ? 'text-[#F43F5E]'
                                : 'text-[#F59E0B]'
                            }`}
                          >
                            {sc.signal} • Score {sc.teddy_score}/100
                          </span>
                        </div>
                        <div className="font-mono-tabular text-lg font-bold text-[#F1F5F9]">
                          {sc.current_price?.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USD
                        </div>
                        <div className="text-xs text-[#94A3B8] line-clamp-2">{sc.reason}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}

          {/* =========================================================
              TAB 2: PAPER TRADING SIMULATOR
             ========================================================= */}
          {activeTab === 'paper' && (
            <div className="space-y-6">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <h2 className="font-display text-2xl font-bold text-[#F1F5F9]">
                    Portefeuille Paper Trading Réaliste
                  </h2>
                  <p className="text-xs text-[#94A3B8]">
                    Simulation fidèle avec frais d'ouverture/clôture (0.04%), slippage (0.02%) et surveillance automatique des seuils SL/TP.
                  </p>
                </div>
                <button
                  onClick={handleResetPaperAccount}
                  className="px-3.5 py-2 bg-[#1E293B] hover:bg-[#334155] border border-white/10 rounded-lg text-xs text-[#F1F5F9] transition-colors"
                >
                  Réinitialiser le capital (10 000 USDT)
                </button>
              </div>

              {paperStats && (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
                  <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-5">
                    <div className="text-xs text-[#94A3B8]">Capital Disponible</div>
                    <div className="font-mono-tabular text-2xl font-bold text-[#F1F5F9] mt-1">
                      {Number(paperStats.capital ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USDT
                    </div>
                  </div>
                  <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-5">
                    <div className="text-xs text-[#94A3B8]">Équité Totale (Marge + Latent)</div>
                    <div className="font-mono-tabular text-2xl font-bold text-[#10B981] mt-1">
                      {Number(paperStats.equity ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USDT
                    </div>
                  </div>
                  <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-5">
                    <div className="text-xs text-[#94A3B8]">PnL Réalisé Cumulé</div>
                    <div
                      className={`font-mono-tabular text-2xl font-bold mt-1 ${
                        (paperStats.total_pnl ?? 0) >= 0 ? 'text-[#10B981]' : 'text-[#F43F5E]'
                      }`}
                    >
                      {(paperStats.total_pnl ?? 0) >= 0 ? '+' : ''}
                      {Number(paperStats.total_pnl ?? 0).toFixed(2)} USDT
                    </div>
                  </div>
                  <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-5">
                    <div className="text-xs text-[#94A3B8]">Taux de Réussite (Win Rate)</div>
                    <div className="font-mono-tabular text-2xl font-bold text-[#F59E0B] mt-1">
                      {Number(paperStats.win_rate ?? 0).toFixed(1)}%{' '}
                      <span className="text-xs font-normal text-[#64748B]">
                        ({paperStats.wins ?? 0}W / {paperStats.losses ?? 0}L)
                      </span>
                    </div>
                  </div>
                </div>
              )}

              {/* Open Positions Table */}
              <div className="bg-[#111827] border border-white/[0.07] rounded-xl overflow-hidden">
                <div className="px-5 py-4 border-b border-white/[0.07] flex items-center justify-between">
                  <h3 className="font-display font-semibold text-sm text-[#F1F5F9]">
                    Positions Ouvertes ({openPaper.length})
                  </h3>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="border-b border-white/[0.07] text-[#64748B] font-mono-tabular uppercase">
                        <th className="py-3 px-4">Actif</th>
                        <th className="py-3 px-4">Sens & Levier</th>
                        <th className="py-3 px-4 text-right">Entrée</th>
                        <th className="py-3 px-4 text-right">Cours Actuel</th>
                        <th className="py-3 px-4 text-right">SL / TP</th>
                        <th className="py-3 px-4 text-right">Marge</th>
                        <th className="py-3 px-4 text-right">PnL Latent</th>
                        <th className="py-3 px-4 text-right">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/[0.05] font-mono-tabular">
                      {openPaper.length === 0 ? (
                        <tr>
                          <td colSpan={8} className="py-8 text-center text-[#64748B] font-sans">
                            Aucune position Paper ouverte. Utilisez le ticket d'ordre depuis l'onglet Market Intelligence.
                          </td>
                        </tr>
                      ) : (
                        openPaper.map((pos) => {
                          const entryVal = Number(pos.entry ?? pos.entry_price ?? 0);
                          const currVal = Number(pos.current_price ?? entryVal);
                          const slVal = Number(pos.sl ?? 0);
                          const tpVal = Number(pos.tp ?? 0);
                          const marginVal = Number(
                            pos.margin_used ?? (entryVal * Number(pos.qty ?? 0)) / Math.max(1, Number(pos.leverage ?? 1))
                          );
                          const upnl = Number(pos.unrealized_pnl ?? pos.pnl_usdt ?? 0);
                          const upnlPct = Number(pos.unrealized_pnl_pct ?? pos.pnl_pct ?? 0);
                          return (
                            <tr key={pos.id} className="hover:bg-white/[0.02]">
                              <td className="py-3.5 px-4 font-semibold text-[#F1F5F9]">{pos.symbol}</td>
                              <td className="py-3.5 px-4">
                                <span className={pos.side === 'BUY' ? 'text-[#10B981]' : 'text-[#F43F5E]'}>
                                  {pos.side} {pos.leverage}x
                                </span>
                              </td>
                              <td className="py-3.5 px-4 text-right">{entryVal.toLocaleString()}</td>
                              <td className="py-3.5 px-4 text-right">{currVal.toLocaleString()}</td>
                              <td className="py-3.5 px-4 text-right">
                                <span className="text-[#F43F5E]">{slVal ? slVal.toLocaleString() : '—'}</span> /{' '}
                                <span className="text-[#10B981]">{tpVal ? tpVal.toLocaleString() : '—'}</span>
                              </td>
                              <td className="py-3.5 px-4 text-right">{marginVal.toFixed(2)} USDT</td>
                              <td
                                className={`py-3.5 px-4 text-right font-semibold ${
                                  upnl >= 0 ? 'text-[#10B981]' : 'text-[#F43F5E]'
                                }`}
                              >
                                {upnl >= 0 ? '+' : ''}
                                {upnl.toFixed(2)} USDT ({upnlPct.toFixed(2)}%)
                              </td>
                              <td className="py-3.5 px-4 text-right">
                                <button
                                  onClick={() => handleClosePaperPosition(pos.id)}
                                  className="px-2.5 py-1 bg-[#F43F5E]/15 hover:bg-[#F43F5E]/25 border border-[#F43F5E]/40 text-[#FB7185] rounded text-[11px]"
                                >
                                  Clôturer
                                </button>
                              </td>
                            </tr>
                          );
                        })
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Closed Positions History */}
              <div className="bg-[#111827] border border-white/[0.07] rounded-xl overflow-hidden">
                <div className="px-5 py-4 border-b border-white/[0.07]">
                  <h3 className="font-display font-semibold text-sm text-[#F1F5F9]">
                    Historique des Positions Clôturées ({closedPaper.length})
                  </h3>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="border-b border-white/[0.07] text-[#64748B] font-mono-tabular uppercase">
                        <th className="py-3 px-4">Actif</th>
                        <th className="py-3 px-4">Sens</th>
                        <th className="py-3 px-4 text-right">Entrée</th>
                        <th className="py-3 px-4 text-right">Sortie</th>
                        <th className="py-3 px-4">Raison</th>
                        <th className="py-3 px-4 text-right">PnL Réalisé</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/[0.05] font-mono-tabular">
                      {closedPaper.slice(0, 20).map((pos) => {
                        const entryVal = Number(pos.entry ?? pos.entry_price ?? 0);
                        const exitVal = Number(pos.exit_price ?? 0);
                        const pnlVal = Number(pos.pnl ?? pos.pnl_usdt ?? 0);
                        const pnlPctVal = Number(pos.pnl_pct ?? 0);
                        return (
                          <tr key={pos.id} className="hover:bg-white/[0.02]">
                            <td className="py-3 px-4 font-semibold text-[#F1F5F9]">{pos.symbol}</td>
                            <td className="py-3 px-4">
                              <span className={pos.side === 'BUY' ? 'text-[#10B981]' : 'text-[#F43F5E]'}>
                                {pos.side} {pos.leverage}x
                              </span>
                            </td>
                            <td className="py-3 px-4 text-right">{entryVal.toLocaleString()}</td>
                            <td className="py-3 px-4 text-right">{exitVal ? exitVal.toLocaleString() : '—'}</td>
                            <td className="py-3 px-4 text-[#94A3B8]">{pos.close_reason ?? pos.exit_reason ?? '—'}</td>
                            <td
                              className={`py-3 px-4 text-right font-semibold ${
                                pnlVal >= 0 ? 'text-[#10B981]' : 'text-[#F43F5E]'
                              }`}
                            >
                              {pnlVal >= 0 ? '+' : ''}
                              {pnlVal.toFixed(2)} USDT ({pnlPctVal.toFixed(2)}%)
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* =========================================================
              TAB 3: ALERTS & WATCHLIST
             ========================================================= */}
          {activeTab === 'alerts' && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              <div className="lg:col-span-5 bg-[#111827] border border-white/[0.07] rounded-xl p-5 space-y-4">
                <h3 className="font-display font-semibold text-base text-[#F1F5F9]">
                  Créer une Alerte de Prix
                </h3>
                <p className="text-xs text-[#94A3B8]">
                  Quota actuel : {alerts.length} / {alertLimit} alertes actives ({user?.role.toUpperCase()}).
                </p>
                <form onSubmit={handleAddAlert} className="space-y-3.5 text-xs">
                  <div>
                    <label className="block text-[#94A3B8] mb-1">Symbole</label>
                    <select
                      value={newAlertSymbol}
                      onChange={(e) => setNewAlertSymbol(e.target.value)}
                      className="w-full px-3 py-2 bg-[#090D16] border border-white/10 rounded-lg font-mono-tabular text-[#F1F5F9]"
                    >
                      {SYMBOLS.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-[#94A3B8] mb-1">Condition de franchissement</label>
                    <select
                      value={newAlertCond}
                      onChange={(e) => setNewAlertCond(e.target.value as 'above' | 'below')}
                      className="w-full px-3 py-2 bg-[#090D16] border border-white/10 rounded-lg text-[#F1F5F9]"
                    >
                      <option value="above">Franchissement à la hausse (ABOVE &ge;)</option>
                      <option value="below">Franchissement à la baisse (BELOW &le;)</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-[#94A3B8] mb-1">Prix Cible (USD / USDT)</label>
                    <input
                      type="number"
                      step="any"
                      value={newAlertPrice}
                      onChange={(e) => setNewAlertPrice(e.target.value)}
                      placeholder="85000"
                      className="w-full px-3 py-2 bg-[#090D16] border border-white/10 rounded-lg font-mono-tabular text-[#F1F5F9]"
                      required
                    />
                  </div>
                  <button
                    type="submit"
                    className="w-full py-2.5 bg-[#10B981] hover:bg-[#059669] text-[#090D16] font-semibold rounded-lg transition-colors"
                  >
                    Activer l'Alerte Prix
                  </button>
                </form>
              </div>

              <div className="lg:col-span-7 bg-[#111827] border border-white/[0.07] rounded-xl p-5 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="font-display font-semibold text-base text-[#F1F5F9]">
                    Alertes Actives ({alerts.length})
                  </h3>
                  {alerts.length > 0 && (
                    <button
                      onClick={() =>
                        apiFetch('/api/alerts/clear', { method: 'POST' }).then((r) => {
                          setAlerts(r.alerts || []);
                          showToast('Toutes les alertes ont été supprimées.', 'info');
                        })
                      }
                      className="text-xs text-[#F43F5E] hover:underline"
                    >
                      Tout effacer
                    </button>
                  )}
                </div>

                <div className="divide-y divide-white/[0.06]">
                  {alerts.length === 0 ? (
                    <div className="py-10 text-center text-xs text-[#64748B]">
                      Aucune alerte active pour le moment.
                    </div>
                  ) : (
                    alerts.map((a) => (
                      <div key={a.id} className="py-3 flex items-center justify-between text-xs">
                        <div className="flex items-center gap-3">
                          <span className="font-mono-tabular font-bold text-sm text-[#F1F5F9]">{a.symbol}</span>
                          <span
                            className={`font-mono-tabular px-2 py-0.5 rounded ${
                              a.condition === 'above'
                                ? 'bg-[#10B981]/15 text-[#10B981]'
                                : 'bg-[#F43F5E]/15 text-[#F43F5E]'
                            }`}
                          >
                            {a.condition === 'above' ? '≥ HAUSSE' : '≤ BAISSE'}
                          </span>
                          <span className="font-mono-tabular text-sm font-semibold text-[#F1F5F9]">
                            {Number(a.price ?? 0).toLocaleString()} USD
                          </span>
                        </div>
                        <button
                          onClick={() => handleDeleteAlert(a.id)}
                          className="p-1.5 text-[#64748B] hover:text-[#F43F5E] transition-colors"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          )}

          {/* =========================================================
              TAB 4: AUTO-TRADE & SAFETY CENTER
             ========================================================= */}
          {activeTab === 'safety' && tradingCfg && (
            <div className="space-y-6">
              {/* Top Status & Safety State Banner */}
              <div
                className={`p-5 rounded-xl border flex flex-wrap items-center justify-between gap-4 ${
                  tradingCfg.safety_lock
                    ? 'bg-[#F43F5E]/10 border-[#F43F5E]/40'
                    : tradingCfg.safety_warn
                    ? 'bg-[#F59E0B]/10 border-[#F59E0B]/40'
                    : 'bg-[#10B981]/10 border-[#10B981]/30'
                }`}
              >
                <div className="space-y-1.5">
                  <div className="flex flex-wrap items-center gap-2.5 font-display font-bold text-base">
                    {tradingCfg.safety_lock ? (
                      <>
                        <ShieldAlert className="w-5 h-5 text-[#F43F5E]" />
                        <span className="text-[#FB7185]">SAFETY LOCK ACTIF (Auto-Trade Suspendu)</span>
                      </>
                    ) : tradingCfg.safety_warn ? (
                      <>
                        <AlertTriangle className="w-5 h-5 text-[#F59E0B]" />
                        <span className="text-[#FBBF24]">SAFETY WARN (Avertissement Temporaire Actif)</span>
                      </>
                    ) : (
                      <>
                        <ShieldCheck className="w-5 h-5 text-[#10B981]" />
                        <span className="text-[#34D399]">SAFETY CENTER OPÉRATIONNEL</span>
                      </>
                    )}

                    <span
                      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-md text-xs font-mono-tabular border ${
                        tradingCfg.credentials_valid
                          ? 'bg-[#10B981]/20 text-[#34D399] border-[#10B981]/40'
                          : 'bg-[#F43F5E]/20 text-[#FB7185] border-[#F43F5E]/40'
                      }`}
                    >
                      <span
                        className={`w-2 h-2 rounded-full ${
                          tradingCfg.credentials_valid ? 'bg-[#10B981] animate-pulse' : 'bg-[#F43F5E]'
                        }`}
                      />
                      {tradingCfg.credentials_valid
                        ? `API BINANCE CONNECTÉE (${tradingCfg.market_type.toUpperCase()} • ${
                            tradingCfg.testnet ? 'TESTNET' : 'LIVE RÉEL'
                          })`
                        : 'API BINANCE DÉCONNECTÉE / CLÉS REQUISES'}
                    </span>
                  </div>

                  <div className="text-xs text-[#94A3B8]">
                    {tradingCfg.safety_lock_reason ||
                      tradingCfg.safety_warn_reason ||
                      tradingCfg.api_status_message ||
                      'Tous les garde-fous de risque (exposition max 20%, fraîcheur de signal 180s, TTL 3600s) sont actifs.'}
                  </div>
                  {(tradingCfg.safety_lock_at || tradingCfg.safety_warn_at) && (
                    <div className="text-[11px] font-mono-tabular text-[#64748B]">
                      {tradingCfg.safety_lock_at && (
                        <span>
                          Lock activé il y a {Math.round(tradingCfg.safety_lock_age_seconds || 0)}s (TTL:{' '}
                          {tradingCfg.safety_lock_ttl_seconds}s){' '}
                        </span>
                      )}
                      {tradingCfg.safety_warn_at && (
                        <span>
                          • Warn horodaté : {new Date(tradingCfg.safety_warn_at * 1000).toLocaleTimeString()}
                        </span>
                      )}
                    </div>
                  )}
                </div>

                <div className="flex flex-wrap items-center gap-2 text-xs">
                  {(tradingCfg.safety_lock || tradingCfg.safety_warn || user?.has_pin) && (
                    <input
                      type="password"
                      maxLength={6}
                      placeholder="PIN (6 chiffres)"
                      value={safetyPinInput}
                      onChange={(e) => setSafetyPinInput(e.target.value)}
                      className="w-32 px-2.5 py-2 bg-[#090D16] border border-white/15 rounded-lg font-mono-tabular text-[#F1F5F9]"
                    />
                  )}
                  {(tradingCfg.safety_lock || tradingCfg.safety_warn) && (
                    <button
                      onClick={() => handleSafetyAction('clearsafe')}
                      className="px-3.5 py-2 bg-[#10B981] hover:bg-[#059669] text-[#090D16] font-semibold rounded-lg transition-colors"
                    >
                      Acquitter / Déverrouiller (/clearsafe)
                    </button>
                  )}
                  {!tradingCfg.safety_lock && (
                    <button
                      onClick={() => handleSafetyAction('engage_lock', 'Verrouillage d’urgence manuel par l’opérateur')}
                      className="px-3.5 py-2 bg-[#F43F5E]/20 hover:bg-[#F43F5E]/30 border border-[#F43F5E]/40 text-[#FB7185] font-semibold rounded-lg transition-colors"
                    >
                      Verrouiller Safe Mode
                    </button>
                  )}
                  <button
                    onClick={() => handleSafetyAction('emergency_stop')}
                    className="px-3.5 py-2 bg-[#F43F5E] hover:bg-[#E11D48] text-white font-semibold rounded-lg transition-colors"
                    title="Ferme toutes les positions ouvertes et désactive AutoTrade (/emergency)"
                  >
                    🛑 Emergency Stop All (/emergency)
                  </button>
                  <button
                    onClick={() =>
                      apiFetch('/api/trading/reconcile', { method: 'POST' }).then(() => {
                        loadLiveAccountAndOrders();
                        showToast('Réconciliation DB ↔ Binance exécutée.', 'success');
                      })
                    }
                    className="px-3.5 py-2 bg-[#111827] hover:bg-[#1E293B] border border-white/15 text-[#F1F5F9] rounded-lg transition-colors"
                  >
                    Réconcilier DB ↔ Binance
                  </button>
                </div>
              </div>

              {/* Row 1: Complete Bot Auto-Trade Parameters + API Keys & Real-Time Account */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                {/* Left (7 cols): Full Bot Configuration (/config, /autotrade, /periodic_analysis) */}
                <div className="lg:col-span-7 bg-[#111827] border border-white/[0.07] rounded-xl p-5 space-y-5">
                  <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.07] pb-3.5">
                    <div>
                      <h3 className="font-display font-semibold text-base text-[#F1F5F9]">
                        Configuration Complète Auto-Trade & Stratégie (Miroir Bot Telegram)
                      </h3>
                      <p className="text-xs text-[#64748B]">
                        Synchronisé en temps réel avec `/config`, `/autotrade` et `/periodic_analysis`. Toute modification critique suspend Auto-Trade par sécurité.
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() =>
                          handleUpdateTradingConfig({
                            enabled: !tradingCfg.enabled,
                            pin: safetyPinInput,
                          })
                        }
                        className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                          tradingCfg.enabled
                            ? 'bg-[#10B981] text-[#090D16]'
                            : 'bg-[#1E293B] text-[#94A3B8] border border-white/10 hover:text-[#F1F5F9]'
                        }`}
                      >
                        Auto-Trade : {tradingCfg.enabled ? 'ON ✅' : 'OFF ❌'}
                      </button>
                      <button
                        onClick={() => handleUpdateTradingConfig({ testnet: !tradingCfg.testnet })}
                        className={`px-3 py-1.5 rounded-lg text-xs font-mono-tabular font-semibold border transition-colors ${
                          tradingCfg.testnet
                            ? 'bg-[#3B82F6]/15 text-[#60A5FA] border-[#3B82F6]/40'
                            : 'bg-[#F59E0B]/15 text-[#FBBF24] border-[#F59E0B]/40'
                        }`}
                      >
                        {tradingCfg.testnet ? 'MODE: TESTNET' : 'MODE: LIVE RÉEL'}
                      </button>
                    </div>
                  </div>

                  {/* Section 1: Market, Style & Periodic Analysis (/setmarket, /settradingstyle, /setanalysistf, /setanalysisinterval) */}
                  <div className="space-y-3">
                    <div className="text-xs font-mono-tabular uppercase tracking-wider text-[#10B981]">
                      1. Marché, Style & Analyse Périodique
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
                      <div>
                        <label className="block text-[#94A3B8] mb-1">Marché (/setmarket)</label>
                        <select
                          value={tradingCfg.market_type}
                          onChange={(e) =>
                            handleUpdateTradingConfig({ market_type: e.target.value as 'futures' | 'spot' })
                          }
                          className="w-full px-3 py-2 bg-[#090D16] border border-white/10 rounded-lg text-[#F1F5F9]"
                        >
                          <option value="futures">FUTURES (USDT-M)</option>
                          <option value="spot">SPOT</option>
                        </select>
                      </div>

                      <div>
                        <label className="block text-[#94A3B8] mb-1">Style (/settradingstyle)</label>
                        <select
                          value={tradingCfg.trading_style}
                          onChange={(e) => {
                            const st = e.target.value;
                            const patch: Partial<TradingConfigState> = { trading_style: st };
                            if (st === 'scalping') patch.analysis_timeframe = '5m';
                            if (st === 'scalping_15m') patch.analysis_timeframe = '15m';
                            handleUpdateTradingConfig(patch);
                          }}
                          className="w-full px-3 py-2 bg-[#090D16] border border-white/10 rounded-lg text-[#F1F5F9]"
                        >
                          {STYLES.map((st) => (
                            <option key={st.id} value={st.id}>
                              {st.label}
                            </option>
                          ))}
                        </select>
                      </div>

                      <div>
                        <label className="block text-[#94A3B8] mb-1">Timeframe (/setanalysistf)</label>
                        <select
                          value={tradingCfg.analysis_timeframe}
                          onChange={(e) => handleUpdateTradingConfig({ analysis_timeframe: e.target.value })}
                          className="w-full px-3 py-2 bg-[#090D16] border border-white/10 rounded-lg font-mono-tabular text-[#F1F5F9]"
                        >
                          {TIMEFRAMES.map((tf) => (
                            <option key={tf} value={tf}>
                              {tf.toUpperCase()}
                            </option>
                          ))}
                        </select>
                      </div>

                      <div>
                        <label className="block text-[#94A3B8] mb-1">Intervalle Scan (/setanalysisinterval)</label>
                        <div className="flex gap-1.5">
                          {[5, 10].map((mins) => (
                            <button
                              key={mins}
                              type="button"
                              onClick={() => handleUpdateTradingConfig({ analysis_interval_minutes: mins })}
                              className={`flex-1 py-2 rounded-lg font-mono-tabular font-semibold border transition-colors ${
                                tradingCfg.analysis_interval_minutes === mins
                                  ? 'bg-[#10B981]/20 border-[#10B981] text-[#10B981]'
                                  : 'bg-[#090D16] border-white/10 text-[#94A3B8] hover:text-[#F1F5F9]'
                              }`}
                            >
                              {mins} min
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-lg bg-[#090D16] border border-white/[0.06] text-xs">
                      <label className="flex items-center gap-2.5 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={tradingCfg.periodic_analysis_enabled}
                          onChange={(e) =>
                            handleUpdateTradingConfig({ periodic_analysis_enabled: e.target.checked })
                          }
                        />
                        <span className="font-medium text-[#F1F5F9]">
                          Analyse Périodique Automatique (/periodic_analysis) — toutes les{' '}
                          {tradingCfg.analysis_interval_minutes} min en {tradingCfg.analysis_timeframe.toUpperCase()}
                        </span>
                      </label>
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedTimeframe(tradingCfg.analysis_timeframe);
                          setSelectedStyle(tradingCfg.trading_style);
                          runMultiScan();
                          showToast(
                            `Scan périodique immédiat lancé (${tradingCfg.analysis_timeframe.toUpperCase()} • ${tradingCfg.trading_style})`,
                            'info'
                          );
                        }}
                        className="px-3 py-1.5 bg-[#10B981]/15 hover:bg-[#10B981]/25 border border-[#10B981]/40 text-[#10B981] rounded-md font-semibold flex items-center gap-1.5"
                      >
                        <Play className="w-3.5 h-3.5" />
                        <span>Scanner Maintenant (/periodic_analysis now)</span>
                      </button>
                    </div>
                  </div>

                  {/* Section 2: Leverage, Risk, Max Positions, Min Score, Daily Max Loss, Cooldown */}
                  <div className="space-y-3 pt-2 border-t border-white/[0.06]">
                    <div className="text-xs font-mono-tabular uppercase tracking-wider text-[#10B981]">
                      2. Paramètres de Risque, Levier & Filtres d'Exécution
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 text-xs">
                      {/* Leverage */}
                      <div className="p-3 rounded-lg bg-[#090D16] border border-white/[0.06] space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-[#94A3B8]">Levier (/setleverage 1–125)</span>
                          <span className="font-mono-tabular font-bold text-[#10B981]">x{tradingCfg.leverage}</span>
                        </div>
                        <div className="flex flex-wrap gap-1">
                          {[1, 2, 5, 10, 20, 50].map((lev) => (
                            <button
                              key={lev}
                              type="button"
                              onClick={() => handleUpdateTradingConfig({ leverage: lev })}
                              className={`px-2 py-1 rounded font-mono-tabular text-[11px] border ${
                                tradingCfg.leverage === lev
                                  ? 'bg-[#10B981] text-[#090D16] border-[#10B981] font-bold'
                                  : 'bg-[#111827] text-[#94A3B8] border-white/10 hover:text-[#F1F5F9]'
                              }`}
                            >
                              x{lev}
                            </button>
                          ))}
                        </div>
                        <input
                          type="number"
                          min="1"
                          max="125"
                          value={tradingCfg.leverage}
                          onChange={(e) =>
                            handleUpdateTradingConfig({
                              leverage: Math.min(125, Math.max(1, Number(e.target.value) || 1)),
                            })
                          }
                          className="w-full px-2.5 py-1.5 bg-[#111827] border border-white/10 rounded font-mono-tabular text-[#F1F5F9]"
                        />
                      </div>

                      {/* Risk per trade */}
                      <div className="p-3 rounded-lg bg-[#090D16] border border-white/[0.06] space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-[#94A3B8]">Risque / Trade (/setrisk)</span>
                          <span className="font-mono-tabular font-bold text-[#10B981]">
                            {tradingCfg.risk_per_trade}%
                          </span>
                        </div>
                        <div className="flex flex-wrap gap-1">
                          {[1, 2, 5, 10].map((r) => (
                            <button
                              key={r}
                              type="button"
                              onClick={() => handleUpdateTradingConfig({ risk_per_trade: r })}
                              className={`px-2 py-1 rounded font-mono-tabular text-[11px] border ${
                                tradingCfg.risk_per_trade === r
                                  ? 'bg-[#10B981] text-[#090D16] border-[#10B981] font-bold'
                                  : 'bg-[#111827] text-[#94A3B8] border-white/10 hover:text-[#F1F5F9]'
                              }`}
                            >
                              {r}%
                            </button>
                          ))}
                        </div>
                        <input
                          type="number"
                          step="0.25"
                          min="0.25"
                          max="20"
                          value={tradingCfg.risk_per_trade}
                          onChange={(e) =>
                            handleUpdateTradingConfig({
                              risk_per_trade: Math.min(20, Math.max(0.25, Number(e.target.value) || 1)),
                            })
                          }
                          className="w-full px-2.5 py-1.5 bg-[#111827] border border-white/10 rounded font-mono-tabular text-[#F1F5F9]"
                        />
                      </div>

                      {/* Max Positions */}
                      <div className="p-3 rounded-lg bg-[#090D16] border border-white/[0.06] space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-[#94A3B8]">Max Positions (/setmaxpos)</span>
                          <span className="font-mono-tabular font-bold text-[#10B981]">
                            {tradingCfg.max_positions}
                          </span>
                        </div>
                        <div className="flex flex-wrap gap-1">
                          {[1, 3, 5, 10].map((mp) => (
                            <button
                              key={mp}
                              type="button"
                              onClick={() => handleUpdateTradingConfig({ max_positions: mp })}
                              className={`px-2.5 py-1 rounded font-mono-tabular text-[11px] border ${
                                tradingCfg.max_positions === mp
                                  ? 'bg-[#10B981] text-[#090D16] border-[#10B981] font-bold'
                                  : 'bg-[#111827] text-[#94A3B8] border-white/10 hover:text-[#F1F5F9]'
                              }`}
                            >
                              {mp}
                            </button>
                          ))}
                        </div>
                        <input
                          type="number"
                          min="1"
                          max="10"
                          value={tradingCfg.max_positions}
                          onChange={(e) =>
                            handleUpdateTradingConfig({
                              max_positions: Math.min(10, Math.max(1, Number(e.target.value) || 1)),
                            })
                          }
                          className="w-full px-2.5 py-1.5 bg-[#111827] border border-white/10 rounded font-mono-tabular text-[#F1F5F9]"
                        />
                      </div>

                      {/* Min Score */}
                      <div className="p-3 rounded-lg bg-[#090D16] border border-white/[0.06] space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-[#94A3B8]">Score Min (/setminscore)</span>
                          <span className="font-mono-tabular font-bold text-[#10B981]">
                            {tradingCfg.min_score}/100
                          </span>
                        </div>
                        <div className="flex flex-wrap gap-1">
                          {[65, 68, 72, 78].map((sc) => (
                            <button
                              key={sc}
                              type="button"
                              onClick={() => handleUpdateTradingConfig({ min_score: sc })}
                              className={`px-2 py-1 rounded font-mono-tabular text-[11px] border ${
                                tradingCfg.min_score === sc
                                  ? 'bg-[#10B981] text-[#090D16] border-[#10B981] font-bold'
                                  : 'bg-[#111827] text-[#94A3B8] border-white/10 hover:text-[#F1F5F9]'
                              }`}
                            >
                              {sc}
                            </button>
                          ))}
                        </div>
                        <input
                          type="number"
                          min="0"
                          max="100"
                          value={tradingCfg.min_score}
                          onChange={(e) =>
                            handleUpdateTradingConfig({
                              min_score: Math.min(100, Math.max(0, Number(e.target.value) || 68)),
                            })
                          }
                          className="w-full px-2.5 py-1.5 bg-[#111827] border border-white/10 rounded font-mono-tabular text-[#F1F5F9]"
                        />
                      </div>

                      {/* Daily Max Loss */}
                      <div className="p-3 rounded-lg bg-[#090D16] border border-white/[0.06] space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-[#94A3B8]">Perte Max/Jour (/setdailymaxloss)</span>
                          <span className="font-mono-tabular font-bold text-[#F43F5E]">
                            {tradingCfg.max_daily_loss}%
                          </span>
                        </div>
                        <div className="text-[11px] font-mono-tabular text-[#64748B]">
                          Cumul jour : {(tradingCfg.daily_loss_tracked || 0).toFixed(2)} USDT
                        </div>
                        <div className="flex gap-1.5">
                          <input
                            type="number"
                            step="0.5"
                            min="0.5"
                            max="100"
                            value={tradingCfg.max_daily_loss}
                            onChange={(e) =>
                              handleUpdateTradingConfig({
                                max_daily_loss: Math.min(100, Math.max(0.5, Number(e.target.value) || 5)),
                              })
                            }
                            className="flex-1 px-2.5 py-1.5 bg-[#111827] border border-white/10 rounded font-mono-tabular text-[#F1F5F9]"
                          />
                          <button
                            type="button"
                            onClick={() => handleSafetyAction('reset_daily_loss')}
                            className="px-2.5 py-1.5 bg-[#1E293B] hover:bg-[#334155] rounded text-[11px] text-[#F1F5F9]"
                          >
                            Reset
                          </button>
                        </div>
                      </div>

                      {/* Cooldown */}
                      <div className="p-3 rounded-lg bg-[#090D16] border border-white/[0.06] space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-[#94A3B8]">Cooldown (/setcooldown)</span>
                          <span className="font-mono-tabular font-bold text-[#F59E0B]">
                            {tradingCfg.cooldown_seconds || 0}s
                          </span>
                        </div>
                        <div className="flex flex-wrap gap-1">
                          {[0, 60, 300, 900, 3600].map((cd) => (
                            <button
                              key={cd}
                              type="button"
                              onClick={() => handleUpdateTradingConfig({ cooldown_seconds: cd })}
                              className={`px-2 py-1 rounded font-mono-tabular text-[11px] border ${
                                (tradingCfg.cooldown_seconds || 0) === cd
                                  ? 'bg-[#10B981] text-[#090D16] border-[#10B981] font-bold'
                                  : 'bg-[#111827] text-[#94A3B8] border-white/10 hover:text-[#F1F5F9]'
                              }`}
                            >
                              {cd === 0 ? '0s' : cd < 3600 ? `${cd / 60}m` : '1h'}
                            </button>
                          ))}
                        </div>
                        <input
                          type="number"
                          min="0"
                          max="86400"
                          value={tradingCfg.cooldown_seconds || 0}
                          onChange={(e) =>
                            handleUpdateTradingConfig({
                              cooldown_seconds: Math.min(86400, Math.max(0, Number(e.target.value) || 0)),
                            })
                          }
                          className="w-full px-2.5 py-1.5 bg-[#111827] border border-white/10 rounded font-mono-tabular text-[#F1F5F9]"
                        />
                      </div>
                    </div>
                  </div>

                  {/* Section 3: Trailing Stop ATR & DCA Parameters (/settrailing, /setdca) */}
                  <div className="space-y-3 pt-2 border-t border-white/[0.06]">
                    <div className="text-xs font-mono-tabular uppercase tracking-wider text-[#10B981]">
                      3. Trailing Stop Dynamique (ATR) & DCA (/settrailing • /setdca)
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
                      {/* Trailing Stop */}
                      <div className="p-3.5 rounded-lg bg-[#090D16] border border-white/[0.06] space-y-2.5">
                        <div className="flex items-center justify-between">
                          <label className="flex items-center gap-2 cursor-pointer font-semibold text-[#F1F5F9]">
                            <input
                              type="checkbox"
                              checked={tradingCfg.trailing_stop}
                              onChange={(e) => handleUpdateTradingConfig({ trailing_stop: e.target.checked })}
                            />
                            <span>Trailing Stop ATR (/settrailing)</span>
                          </label>
                          <span className="font-mono-tabular text-[#10B981]">
                            {tradingCfg.trailing_stop ? 'ON' : 'OFF'} ({tradingCfg.trailing_stop_pct ?? 1.0}%)
                          </span>
                        </div>
                        <div className="flex flex-wrap gap-1.5">
                          {[1, 1.5, 2, 3, 5].map((pct) => (
                            <button
                              key={pct}
                              type="button"
                              onClick={() =>
                                handleUpdateTradingConfig({ trailing_stop: true, trailing_stop_pct: pct })
                              }
                              className={`px-2 py-1 rounded font-mono-tabular text-[11px] border ${
                                tradingCfg.trailing_stop_pct === pct
                                  ? 'bg-[#10B981] text-[#090D16] border-[#10B981] font-bold'
                                  : 'bg-[#111827] text-[#94A3B8] border-white/10 hover:text-[#F1F5F9]'
                              }`}
                            >
                              {pct}%
                            </button>
                          ))}
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-[#94A3B8] text-[11px]">Facteur / Distance (0.1–20%) :</span>
                          <input
                            type="number"
                            step="0.1"
                            min="0.1"
                            max="20"
                            value={tradingCfg.trailing_stop_pct ?? 1.0}
                            onChange={(e) =>
                              handleUpdateTradingConfig({
                                trailing_stop_pct: Math.min(20, Math.max(0.1, Number(e.target.value) || 1.0)),
                              })
                            }
                            className="w-24 px-2 py-1 bg-[#111827] border border-white/10 rounded font-mono-tabular text-[#F1F5F9]"
                          />
                        </div>
                      </div>

                      {/* DCA */}
                      <div className="p-3.5 rounded-lg bg-[#090D16] border border-white/[0.06] space-y-2.5">
                        <div className="flex items-center justify-between">
                          <label className="flex items-center gap-2 cursor-pointer font-semibold text-[#F1F5F9]">
                            <input
                              type="checkbox"
                              checked={tradingCfg.dca_enabled}
                              onChange={(e) => handleUpdateTradingConfig({ dca_enabled: e.target.checked })}
                            />
                            <span>Configuration DCA (/setdca)</span>
                          </label>
                          <span className="font-mono-tabular text-[#F59E0B]">
                            {tradingCfg.dca_enabled ? 'ON' : 'OFF'} ({tradingCfg.dca_steps ?? 3} ét.,{' '}
                            {tradingCfg.dca_step_pct ?? 2.0}%)
                          </span>
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                          <div>
                            <label className="block text-[11px] text-[#94A3B8] mb-1">Étapes (1–10)</label>
                            <input
                              type="number"
                              min="1"
                              max="10"
                              value={tradingCfg.dca_steps ?? 3}
                              onChange={(e) =>
                                handleUpdateTradingConfig({
                                  dca_steps: Math.min(10, Math.max(1, Number(e.target.value) || 3)),
                                })
                              }
                              className="w-full px-2 py-1 bg-[#111827] border border-white/10 rounded font-mono-tabular text-[#F1F5F9]"
                            />
                          </div>
                          <div>
                            <label className="block text-[11px] text-[#94A3B8] mb-1">Écart % (0.1–20%)</label>
                            <input
                              type="number"
                              step="0.5"
                              min="0.1"
                              max="20"
                              value={tradingCfg.dca_step_pct ?? 2.0}
                              onChange={(e) =>
                                handleUpdateTradingConfig({
                                  dca_step_pct: Math.min(20, Math.max(0.1, Number(e.target.value) || 2.0)),
                                })
                              }
                              className="w-full px-2 py-1 bg-[#111827] border border-white/10 rounded font-mono-tabular text-[#F1F5F9]"
                            />
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Section 4: Whitelist & Blacklist (/whitelist, /blacklist) */}
                  <div className="space-y-3 pt-2 border-t border-white/[0.06]">
                    <div className="text-xs font-mono-tabular uppercase tracking-wider text-[#10B981]">
                      4. Filtrage des Symboles Documentés (/whitelist • /blacklist)
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
                      {/* Whitelist */}
                      <div className="p-3.5 rounded-lg bg-[#090D16] border border-white/[0.06] space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-[#F1F5F9]">✅ Whitelist AutoTrade</span>
                          {(tradingCfg.symbol_whitelist || []).length > 0 && (
                            <button
                              type="button"
                              onClick={() => handleUpdateTradingConfig({ symbol_whitelist: [] })}
                              className="text-[11px] text-[#F43F5E] hover:underline"
                            >
                              Vider (clear)
                            </button>
                          )}
                        </div>
                        <div className="flex flex-wrap gap-1.5">
                          {SYMBOLS.map((s) => {
                            const active = (tradingCfg.symbol_whitelist || []).includes(s.id);
                            return (
                              <button
                                key={s.id}
                                type="button"
                                onClick={() => {
                                  const cur = tradingCfg.symbol_whitelist || [];
                                  const next = active ? cur.filter((x) => x !== s.id) : [...cur, s.id];
                                  handleUpdateTradingConfig({ symbol_whitelist: next });
                                }}
                                className={`px-2.5 py-1 rounded font-mono-tabular text-[11px] border transition-colors ${
                                  active
                                    ? 'bg-[#10B981]/20 border-[#10B981] text-[#10B981] font-semibold'
                                    : 'bg-[#111827] border-white/10 text-[#94A3B8] hover:text-[#F1F5F9]'
                                }`}
                              >
                                {active ? '✓ ' : '+ '}
                                {s.id}
                              </button>
                            );
                          })}
                        </div>
                        <div className="text-[11px] text-[#64748B]">
                          {(tradingCfg.symbol_whitelist || []).length === 0
                            ? 'Aucune restriction (tous les symboles documentés sont autorisés).'
                            : `Actifs autorisés : ${(tradingCfg.symbol_whitelist || []).join(', ')}`}
                        </div>
                      </div>

                      {/* Blacklist */}
                      <div className="p-3.5 rounded-lg bg-[#090D16] border border-white/[0.06] space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-[#F1F5F9]">🚫 Blacklist AutoTrade</span>
                          {(tradingCfg.symbol_blacklist || []).length > 0 && (
                            <button
                              type="button"
                              onClick={() => handleUpdateTradingConfig({ symbol_blacklist: [] })}
                              className="text-[11px] text-[#F43F5E] hover:underline"
                            >
                              Vider (clear)
                            </button>
                          )}
                        </div>
                        <div className="flex flex-wrap gap-1.5">
                          {SYMBOLS.map((s) => {
                            const active = (tradingCfg.symbol_blacklist || []).includes(s.id);
                            return (
                              <button
                                key={s.id}
                                type="button"
                                onClick={() => {
                                  const cur = tradingCfg.symbol_blacklist || [];
                                  const next = active ? cur.filter((x) => x !== s.id) : [...cur, s.id];
                                  handleUpdateTradingConfig({ symbol_blacklist: next });
                                }}
                                className={`px-2.5 py-1 rounded font-mono-tabular text-[11px] border transition-colors ${
                                  active
                                    ? 'bg-[#F43F5E]/20 border-[#F43F5E] text-[#FB7185] font-semibold'
                                    : 'bg-[#111827] border-white/10 text-[#94A3B8] hover:text-[#F1F5F9]'
                                }`}
                              >
                                {active ? '✕ ' : '+ '}
                                {s.id}
                              </button>
                            );
                          })}
                        </div>
                        <div className="text-[11px] text-[#64748B]">
                          {(tradingCfg.symbol_blacklist || []).length === 0
                            ? 'Aucun actif bloqué.'
                            : `Actifs exclus : ${(tradingCfg.symbol_blacklist || []).join(', ')}`}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Right (5 cols): API Credentials (/setapikeys) + Real-Time Account (/account) */}
                <div className="lg:col-span-5 space-y-6">
                  {/* Binance API Credentials Card */}
                  <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-5 space-y-4">
                    <div className="flex items-center justify-between border-b border-white/[0.07] pb-3">
                      <div className="flex items-center gap-2">
                        <Key className="w-4 h-4 text-[#10B981]" />
                        <h3 className="font-display font-semibold text-base text-[#F1F5F9]">
                          Clés API Binance (/setapikeys)
                        </h3>
                      </div>
                      <span
                        className={`px-2 py-0.5 rounded text-[11px] font-mono-tabular font-semibold border ${
                          tradingCfg.credentials_valid
                            ? 'bg-[#10B981]/15 text-[#10B981] border-[#10B981]/40'
                            : 'bg-[#F43F5E]/15 text-[#FB7185] border-[#F43F5E]/40'
                        }`}
                      >
                        {tradingCfg.credentials_valid
                          ? `● OPÉRATIONNEL (${tradingCfg.api_key_masked || 'Testnet'})`
                          : '○ NON CONNECTÉ'}
                      </span>
                    </div>

                    <div className="flex items-center justify-between p-3 rounded-lg bg-[#090D16] border border-white/[0.06] text-xs">
                      <div>
                        <div className="text-[#94A3B8]">Clé active :</div>
                        <div className="font-mono-tabular font-semibold text-[#F1F5F9]">
                          {tradingCfg.api_key_masked || 'Aucune clé chargée'} •{' '}
                          {tradingCfg.testnet ? 'TESTNET' : 'LIVE'} ({tradingCfg.market_type.toUpperCase()})
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={handleTestBinanceConnection}
                        disabled={testingApiConn}
                        className="px-3 py-1.5 bg-[#1E293B] hover:bg-[#334155] border border-white/10 rounded-lg text-xs text-[#F1F5F9] flex items-center gap-1.5"
                      >
                        <RefreshCw className={`w-3.5 h-3.5 ${testingApiConn ? 'animate-spin text-[#10B981]' : ''}`} />
                        <span>Tester Connexion</span>
                      </button>
                    </div>

                    <form onSubmit={handleSaveBinanceKeys} className="space-y-3 text-xs">
                      <div>
                        <label className="block text-[#94A3B8] mb-1">Binance API Key</label>
                        <input
                          type="text"
                          value={binanceKey}
                          onChange={(e) => setBinanceKey(e.target.value)}
                          placeholder="Entrez votre clé API Binance..."
                          className="w-full px-3 py-2 bg-[#090D16] border border-white/10 rounded-lg font-mono-tabular text-[#F1F5F9]"
                          required
                        />
                      </div>
                      <div>
                        <label className="block text-[#94A3B8] mb-1">Binance API Secret</label>
                        <input
                          type="password"
                          value={binanceSecret}
                          onChange={(e) => setBinanceSecret(e.target.value)}
                          placeholder="••••••••••••••••••••••••••••••••"
                          className="w-full px-3 py-2 bg-[#090D16] border border-white/10 rounded-lg font-mono-tabular text-[#F1F5F9]"
                          required
                        />
                      </div>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={binanceTestnet}
                          onChange={(e) => setBinanceTestnet(e.target.checked)}
                        />
                        <span>Environnement Binance Testnet (/settestnet on|off)</span>
                      </label>
                      <button
                        type="submit"
                        className="w-full py-2.5 bg-[#10B981] hover:bg-[#059669] text-[#090D16] font-semibold rounded-lg transition-colors"
                      >
                        Enregistrer & Vérifier les Clés API
                      </button>
                    </form>
                  </div>

                  {/* Real-Time Binance Account Balance & Margin Card (/account, /balance) */}
                  <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-5 space-y-4">
                    <div className="flex items-center justify-between border-b border-white/[0.07] pb-3">
                      <div className="flex items-center gap-2">
                        <Wallet className="w-4 h-4 text-[#10B981]" />
                        <h3 className="font-display font-semibold text-base text-[#F1F5F9]">
                          Solde & Marge Compte Binance (/account)
                        </h3>
                      </div>
                      <button
                        type="button"
                        onClick={loadLiveAccountAndOrders}
                        disabled={loadingLiveAccount}
                        className="text-xs text-[#10B981] hover:underline flex items-center gap-1"
                      >
                        <RefreshCw className={`w-3.5 h-3.5 ${loadingLiveAccount ? 'animate-spin' : ''}`} />
                        <span>Rafraîchir</span>
                      </button>
                    </div>

                    {liveAccount ? (
                      <div className="space-y-3 text-xs">
                        <div className="grid grid-cols-2 gap-3 font-mono-tabular">
                          <div className="p-3 rounded-lg bg-[#090D16] border border-white/[0.06]">
                            <div className="text-[10px] text-[#64748B] uppercase">Solde Total Wallet</div>
                            <div className="text-base font-bold text-[#F1F5F9] mt-0.5">
                              {Number(liveAccount.total_wallet_balance || 0).toLocaleString('en-US', {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2,
                              })}{' '}
                              USDT
                            </div>
                          </div>
                          <div className="p-3 rounded-lg bg-[#090D16] border border-white/[0.06]">
                            <div className="text-[10px] text-[#64748B] uppercase">Disponible</div>
                            <div className="text-base font-bold text-[#10B981] mt-0.5">
                              {Number(liveAccount.available_balance || 0).toLocaleString('en-US', {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2,
                              })}{' '}
                              USDT
                            </div>
                          </div>
                          <div className="p-3 rounded-lg bg-[#090D16] border border-white/[0.06]">
                            <div className="text-[10px] text-[#64748B] uppercase">PnL Non Réalisé</div>
                            <div
                              className={`text-base font-bold mt-0.5 ${
                                Number(liveAccount.unrealized_pnl || 0) >= 0 ? 'text-[#10B981]' : 'text-[#F43F5E]'
                              }`}
                            >
                              {Number(liveAccount.unrealized_pnl || 0) >= 0 ? '+' : ''}
                              {Number(liveAccount.unrealized_pnl || 0).toFixed(2)} USDT
                            </div>
                          </div>
                          <div className="p-3 rounded-lg bg-[#090D16] border border-white/[0.06]">
                            <div className="text-[10px] text-[#64748B] uppercase">Marge Utilisée</div>
                            <div className="text-base font-bold text-[#F59E0B] mt-0.5">
                              {liveAccount.market_type === 'futures' ? `${liveAccount.margin_used_pct || 0}%` : 'SPOT'}
                            </div>
                          </div>
                        </div>

                        {Array.isArray(liveAccount.assets) && liveAccount.assets.length > 0 && (
                          <div className="space-y-1.5 pt-1">
                            <div className="text-[11px] text-[#94A3B8] font-semibold">Actifs détectés :</div>
                            <div className="max-h-32 overflow-y-auto divide-y divide-white/[0.05] font-mono-tabular">
                              {liveAccount.assets.slice(0, 6).map((a: any) => (
                                <div key={a.asset} className="py-1.5 flex items-center justify-between text-[11px]">
                                  <span className="font-bold text-[#F1F5F9]">{a.asset}</span>
                                  <span className="text-[#94A3B8]">
                                    {liveAccount.market_type === 'futures'
                                      ? `${Number(a.wallet || 0).toFixed(4)} (Dispo: ${Number(a.available || 0).toFixed(2)})`
                                      : `${Number(a.total || 0).toFixed(4)} (~${Number(a.usdt_value || 0).toFixed(2)} USDT)`}
                                  </span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="p-4 rounded-lg bg-[#090D16] border border-white/[0.06] text-xs text-[#94A3B8]">
                        Connectez des clés API Binance valides pour afficher le solde temps réel, la marge disponible et les positions sur le serveur Binance.
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Row 2: Manual Live Order Ticket (/live, /live_long, /live_short) + Open Positions & Orders (/positions, /close) */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                {/* Manual Live Order Ticket (5 cols) */}
                <div className="lg:col-span-5 bg-[#111827] border border-white/[0.07] rounded-xl p-5 space-y-4">
                  <div className="flex items-center justify-between border-b border-white/[0.07] pb-3">
                    <div>
                      <h3 className="font-display font-semibold text-base text-[#F1F5F9]">
                        Ticket d'Ordre Live Manuel (/live_long • /live_short)
                      </h3>
                      <p className="text-xs text-[#64748B]">
                        Validation de pré-ordre + confirmation explicite avant envoi sur Binance ({tradingCfg.market_type.toUpperCase()}).
                      </p>
                    </div>
                  </div>

                  <div className="space-y-3 text-xs">
                    <div className="grid grid-cols-2 gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          setLiveOrderSide('BUY');
                          setLiveOrderDraftCheck(null);
                        }}
                        className={`py-2 rounded-lg font-semibold border transition-colors ${
                          liveOrderSide === 'BUY'
                            ? 'bg-[#10B981] text-[#090D16] border-[#10B981]'
                            : 'bg-[#090D16] text-[#94A3B8] border-white/10'
                        }`}
                      >
                        🟢 OUVRIR LONG (BUY)
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setLiveOrderSide('SELL');
                          setLiveOrderDraftCheck(null);
                        }}
                        className={`py-2 rounded-lg font-semibold border transition-colors ${
                          liveOrderSide === 'SELL'
                            ? 'bg-[#F43F5E] text-white border-[#F43F5E]'
                            : 'bg-[#090D16] text-[#94A3B8] border-white/10'
                        }`}
                      >
                        🔴 OUVRIR SHORT (SELL)
                      </button>
                    </div>

                    <div className="grid grid-cols-2 gap-2.5">
                      <div>
                        <label className="block text-[11px] text-[#94A3B8] mb-1">Symbole</label>
                        <select
                          value={liveOrderSymbol}
                          onChange={(e) => {
                            setLiveOrderSymbol(e.target.value);
                            setLiveOrderDraftCheck(null);
                          }}
                          className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/10 rounded font-mono-tabular text-[#F1F5F9]"
                        >
                          {SYMBOLS.map((s) => (
                            <option key={s.id} value={s.id}>
                              {s.id}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="block text-[11px] text-[#94A3B8] mb-1">Type d'Ordre</label>
                        <select
                          value={liveOrderType}
                          onChange={(e) => {
                            setLiveOrderType(e.target.value as 'MARKET' | 'LIMIT');
                            setLiveOrderDraftCheck(null);
                          }}
                          className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/10 rounded font-mono-tabular text-[#F1F5F9]"
                        >
                          <option value="MARKET">MARKET</option>
                          <option value="LIMIT">LIMIT</option>
                        </select>
                      </div>
                    </div>

                    <div className="grid grid-cols-3 gap-2.5">
                      <div>
                        <label className="block text-[11px] text-[#94A3B8] mb-1">Montant</label>
                        <input
                          type="number"
                          step="any"
                          value={liveOrderAmount}
                          onChange={(e) => {
                            setLiveOrderAmount(e.target.value);
                            setLiveOrderDraftCheck(null);
                          }}
                          className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/10 rounded font-mono-tabular text-[#F1F5F9]"
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] text-[#94A3B8] mb-1">Mode Montant</label>
                        <select
                          value={liveOrderAmountMode}
                          onChange={(e) => {
                            setLiveOrderAmountMode(e.target.value as 'fixed' | 'percentage');
                            setLiveOrderDraftCheck(null);
                          }}
                          className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/10 rounded text-[#F1F5F9]"
                        >
                          <option value="fixed">USDT Fixe</option>
                          <option value="percentage">% Solde</option>
                        </select>
                      </div>
                      <div>
                        <label className="block text-[11px] text-[#94A3B8] mb-1">Levier (1–125)</label>
                        <input
                          type="number"
                          min="1"
                          max="125"
                          value={liveOrderLeverage}
                          onChange={(e) => {
                            setLiveOrderLeverage(e.target.value);
                            setLiveOrderDraftCheck(null);
                          }}
                          className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/10 rounded font-mono-tabular text-[#F1F5F9]"
                        />
                      </div>
                    </div>

                    {liveOrderType === 'LIMIT' && (
                      <div>
                        <label className="block text-[11px] text-[#94A3B8] mb-1">Prix Limite d'Entrée</label>
                        <input
                          type="number"
                          step="any"
                          value={liveOrderEntryPrice}
                          onChange={(e) => {
                            setLiveOrderEntryPrice(e.target.value);
                            setLiveOrderDraftCheck(null);
                          }}
                          placeholder="Ex: 82500"
                          className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/10 rounded font-mono-tabular text-[#F1F5F9]"
                        />
                      </div>
                    )}

                    <div className="grid grid-cols-2 gap-2.5">
                      <div>
                        <label className="block text-[11px] text-[#94A3B8] mb-1">Stop Loss (SL)</label>
                        <input
                          type="number"
                          step="any"
                          value={liveOrderSL}
                          onChange={(e) => {
                            setLiveOrderSL(e.target.value);
                            setLiveOrderDraftCheck(null);
                          }}
                          placeholder="Prix SL..."
                          className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/10 rounded font-mono-tabular text-[#F43F5E]"
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] text-[#94A3B8] mb-1">Take Profit (TP)</label>
                        <input
                          type="number"
                          step="any"
                          value={liveOrderTP}
                          onChange={(e) => {
                            setLiveOrderTP(e.target.value);
                            setLiveOrderDraftCheck(null);
                          }}
                          placeholder="Prix TP..."
                          className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/10 rounded font-mono-tabular text-[#10B981]"
                        />
                      </div>
                    </div>

                    <div className="flex items-center justify-between gap-2 pt-1">
                      <div className="flex items-center gap-2">
                        <span className="text-[#94A3B8]">Marge :</span>
                        {(['ISOLATED', 'CROSS'] as const).map((mt) => (
                          <button
                            key={mt}
                            type="button"
                            onClick={() => setLiveOrderMarginType(mt)}
                            className={`px-2 py-1 rounded text-[11px] font-mono-tabular border ${
                              liveOrderMarginType === mt
                                ? 'bg-[#10B981]/20 border-[#10B981] text-[#10B981]'
                                : 'bg-[#090D16] border-white/10 text-[#94A3B8]'
                            }`}
                          >
                            {mt}
                          </button>
                        ))}
                      </div>
                      <label className="flex items-center gap-1.5 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={liveOrderReduceOnly}
                          onChange={(e) => setLiveOrderReduceOnly(e.target.checked)}
                        />
                        <span>Reduce-Only</span>
                      </label>
                    </div>

                    {liveOrderDraftCheck && (
                      <div className="p-3 rounded-lg bg-[#090D16] border border-[#10B981]/40 space-y-1 font-mono-tabular text-[11px]">
                        <div className="text-[#10B981] font-bold">✅ Pré-validation Binance réussie :</div>
                        <div>
                          Prix réf: {Number(liveOrderDraftCheck.price).toFixed(2)} • Quantité:{' '}
                          <strong>{liveOrderDraftCheck.quantity}</strong>
                        </div>
                        <div>
                          Marge engagée: {Number(liveOrderDraftCheck.margin_amount).toFixed(2)} USDT • Notional:{' '}
                          {Number(liveOrderDraftCheck.notional).toFixed(2)} USDT
                        </div>
                        <div>
                          SL: {liveOrderDraftCheck.sl_price || '—'} | TP: {liveOrderDraftCheck.tp_price || '—'}
                        </div>
                      </div>
                    )}

                    <div className="flex gap-2 pt-1">
                      <button
                        type="button"
                        onClick={() => handleLiveOrderAction('validate')}
                        className="flex-1 py-2.5 bg-[#1E293B] hover:bg-[#334155] border border-white/10 text-[#F1F5F9] font-semibold rounded-lg transition-colors"
                      >
                        1. Valider l'Ordre
                      </button>
                      <button
                        type="button"
                        disabled={!liveOrderDraftCheck}
                        onClick={() => handleLiveOrderAction('execute')}
                        className={`flex-1 py-2.5 font-semibold rounded-lg transition-colors ${
                          liveOrderDraftCheck
                            ? 'bg-[#10B981] hover:bg-[#059669] text-[#090D16]'
                            : 'bg-[#090D16] text-[#64748B] border border-white/5 cursor-not-allowed'
                        }`}
                      >
                        2. Confirmer Envoi Réel
                      </button>
                    </div>
                  </div>
                </div>

                {/* Open Positions, Open Orders & Trade History (7 cols) */}
                <div className="lg:col-span-7 space-y-6">
                  {/* Open Positions (/positions, /close) */}
                  <div className="bg-[#111827] border border-white/[0.07] rounded-xl overflow-hidden">
                    <div className="px-5 py-4 border-b border-white/[0.07] flex items-center justify-between">
                      <h3 className="font-display font-semibold text-sm text-[#F1F5F9]">
                        Positions AutoTrade & Live Ouvertes ({liveTrades.open.length}) — /positions
                      </h3>
                      <button
                        type="button"
                        onClick={loadLiveAccountAndOrders}
                        className="text-xs text-[#10B981] hover:underline"
                      >
                        Actualiser
                      </button>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-left border-collapse text-xs">
                        <thead>
                          <tr className="border-b border-white/[0.07] text-[#64748B] font-mono-tabular uppercase">
                            <th className="py-2.5 px-4">ID / Actif</th>
                            <th className="py-2.5 px-4">Sens & Marché</th>
                            <th className="py-2.5 px-4 text-right">Quantité</th>
                            <th className="py-2.5 px-4 text-right">Entrée</th>
                            <th className="py-2.5 px-4 text-right">SL / TP</th>
                            <th className="py-2.5 px-4 text-right">Action (/close)</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-white/[0.05] font-mono-tabular">
                          {liveTrades.open.length === 0 ? (
                            <tr>
                              <td colSpan={6} className="py-6 text-center text-[#64748B] font-sans">
                                Aucune position ouverte enregistrée localement.
                              </td>
                            </tr>
                          ) : (
                            liveTrades.open.map((t: any) => (
                              <tr key={t.id} className="hover:bg-white/[0.02]">
                                <td className="py-3 px-4 font-semibold text-[#F1F5F9]">
                                  #{t.id} {t.symbol}
                                </td>
                                <td className="py-3 px-4">
                                  <span className={t.direction === 'BUY' ? 'text-[#10B981]' : 'text-[#F43F5E]'}>
                                    {t.direction} x{t.leverage || 1}
                                  </span>{' '}
                                  <span className="text-[10px] text-[#64748B] uppercase">({t.market_type})</span>
                                </td>
                                <td className="py-3 px-4 text-right">{t.quantity}</td>
                                <td className="py-3 px-4 text-right">{Number(t.entry_price || 0).toLocaleString()}</td>
                                <td className="py-3 px-4 text-right">
                                  <span className="text-[#F43F5E]">{t.sl_price ?? '—'}</span> /{' '}
                                  <span className="text-[#10B981]">{t.tp_price ?? '—'}</span>
                                </td>
                                <td className="py-3 px-4 text-right">
                                  <button
                                    type="button"
                                    onClick={() => handleCloseLivePosition(t.id)}
                                    className="px-2.5 py-1 bg-[#F43F5E]/15 hover:bg-[#F43F5E]/25 border border-[#F43F5E]/40 text-[#FB7185] rounded text-[11px]"
                                  >
                                    Fermer (#{t.id})
                                  </button>
                                </td>
                              </tr>
                            ))
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* Open Binance Orders (live_orders / live_cancel_menu) */}
                  <div className="bg-[#111827] border border-white/[0.07] rounded-xl overflow-hidden">
                    <div className="px-5 py-4 border-b border-white/[0.07] flex items-center justify-between">
                      <h3 className="font-display font-semibold text-sm text-[#F1F5F9]">
                        Ordres Protecteurs & Limites Ouverts sur Binance ({liveOpenOrders.length})
                      </h3>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-left border-collapse text-xs">
                        <thead>
                          <tr className="border-b border-white/[0.07] text-[#64748B] font-mono-tabular uppercase">
                            <th className="py-2.5 px-4">Symbole</th>
                            <th className="py-2.5 px-4">Type & Sens</th>
                            <th className="py-2.5 px-4 text-right">Prix / Stop</th>
                            <th className="py-2.5 px-4 text-right">Quantité</th>
                            <th className="py-2.5 px-4 text-right">Action</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-white/[0.05] font-mono-tabular">
                          {liveOpenOrders.length === 0 ? (
                            <tr>
                              <td colSpan={5} className="py-5 text-center text-[#64748B] font-sans">
                                Aucun ordre ouvert sur Binance actuellement.
                              </td>
                            </tr>
                          ) : (
                            liveOpenOrders.map((ord: any) => (
                              <tr key={ord.orderId} className="hover:bg-white/[0.02]">
                                <td className="py-2.5 px-4 font-semibold text-[#F1F5F9]">{ord.symbol}</td>
                                <td className="py-2.5 px-4">
                                  <span className={ord.side === 'BUY' ? 'text-[#10B981]' : 'text-[#F43F5E]'}>
                                    {ord.side}
                                  </span>{' '}
                                  • {ord.type}
                                </td>
                                <td className="py-2.5 px-4 text-right">
                                  {Number(ord.stopPrice || ord.price || 0).toLocaleString()}
                                </td>
                                <td className="py-2.5 px-4 text-right">
                                  {ord.closePosition ? 'ClosePosition' : ord.origQty}
                                </td>
                                <td className="py-2.5 px-4 text-right">
                                  <button
                                    type="button"
                                    onClick={() => handleCancelLiveOrder(ord.symbol, String(ord.orderId))}
                                    className="px-2 py-1 bg-[#1E293B] hover:bg-[#F43F5E]/20 text-[#94A3B8] hover:text-[#FB7185] rounded text-[11px]"
                                  >
                                    Annuler
                                  </button>
                                </td>
                              </tr>
                            ))
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* =========================================================
              TAB 5: SIGNALS HISTORY & DECISION JOURNAL
             ========================================================= */}
          {activeTab === 'history' && (
            <div className="space-y-6">
              <div className="bg-[#111827] border border-white/[0.07] rounded-xl overflow-hidden">
                <div className="px-5 py-4 border-b border-white/[0.07] flex items-center justify-between">
                  <div>
                    <h3 className="font-display font-semibold text-base text-[#F1F5F9]">
                      Historique des Signaux Validés ({signalHistory.length})
                    </h3>
                    <p className="text-xs text-[#64748B]">
                      Registre persistant des signaux générés par SignalEngine avec suivi de performance.
                    </p>
                  </div>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="border-b border-white/[0.07] text-[#64748B] font-mono-tabular uppercase">
                        <th className="py-3 px-4">ID</th>
                        <th className="py-3 px-4">Actif & TF</th>
                        <th className="py-3 px-4">Signal</th>
                        <th className="py-3 px-4 text-right">Score</th>
                        <th className="py-3 px-4 text-right">Prix Entrée</th>
                        <th className="py-3 px-4 text-right">SL / TP</th>
                        <th className="py-3 px-4 text-right">R:R</th>
                        <th className="py-3 px-4">Statut</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/[0.05] font-mono-tabular">
                      {signalHistory.map((sig) => (
                        <tr key={sig.id} className="hover:bg-white/[0.02]">
                          <td className="py-3 px-4 text-[#64748B]">#{sig.id.slice(0, 8)}</td>
                          <td className="py-3 px-4 font-semibold text-[#F1F5F9]">
                            {sig.symbol} • {sig.timeframe.toUpperCase()}
                          </td>
                          <td className="py-3 px-4">
                            <span className={sig.direction === 'BUY' ? 'text-[#10B981] font-bold' : 'text-[#F43F5E] font-bold'}>
                              {sig.direction}
                            </span>
                          </td>
                          <td className="py-3 px-4 text-right">{sig.score}/100</td>
                          <td className="py-3 px-4 text-right">{sig.entry_price?.toLocaleString()}</td>
                          <td className="py-3 px-4 text-right">
                            <span className="text-[#F43F5E]">{sig.sl?.toLocaleString() || '—'}</span> /{' '}
                            <span className="text-[#10B981]">{sig.tp?.toLocaleString() || '—'}</span>
                          </td>
                          <td className="py-3 px-4 text-right text-[#F59E0B]">
                            {sig.rr_ratio ? `1:${sig.rr_ratio.toFixed(2)}` : '—'}
                          </td>
                          <td className="py-3 px-4">
                            <span
                              className={`px-2 py-0.5 rounded text-[11px] uppercase ${
                                sig.status === 'win'
                                  ? 'bg-[#10B981]/15 text-[#10B981]'
                                  : sig.status === 'loss'
                                  ? 'bg-[#F43F5E]/15 text-[#F43F5E]'
                                  : 'bg-white/[0.06] text-[#94A3B8]'
                              }`}
                            >
                              {sig.status} {sig.result_pct ? `(${sig.result_pct > 0 ? '+' : ''}${sig.result_pct}%)` : ''}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* =========================================================
              TAB 6: ACCOUNT, SUBSCRIPTION PLANS, PIN & SUPPORT
             ========================================================= */}
          {activeTab === 'account' && user && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              {/* Left: Plans, Promo Code & Binance Pay */}
              <div className="lg:col-span-6 space-y-6">
                <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-5 space-y-4">
                  <h3 className="font-display font-semibold text-base text-[#F1F5F9]">
                    Abonnement PRO / VIP & Codes Promotionnels
                  </h3>
                  <form onSubmit={handleRedeemPromo} className="flex gap-2 text-xs">
                    <input
                      type="text"
                      value={promoCodeInput}
                      onChange={(e) => setPromoCodeInput(e.target.value)}
                      placeholder="Code Promo (ex: TEDDYPRO ou TEDDYVIP)"
                      className="flex-1 px-3 py-2 bg-[#090D16] border border-white/10 rounded-lg font-mono-tabular uppercase text-[#F1F5F9]"
                      required
                    />
                    <button
                      type="submit"
                      className="px-4 py-2 bg-[#10B981] text-[#090D16] font-semibold rounded-lg"
                    >
                      Activer Code
                    </button>
                  </form>

                  <div className="grid grid-cols-2 gap-3 pt-2 text-xs">
                    <button
                      onClick={() => handleGenerateBinancePay('pro')}
                      className="p-3.5 rounded-lg bg-[#090D16] border border-[#10B981]/40 hover:bg-[#10B981]/10 text-left space-y-1 transition-colors"
                    >
                      <div className="font-semibold text-[#10B981]">Générer Mémo Binance Pay PRO</div>
                      <div className="font-mono-tabular text-[#F1F5F9]">19 USDT / mois</div>
                    </button>
                    <button
                      onClick={() => handleGenerateBinancePay('vip')}
                      className="p-3.5 rounded-lg bg-[#090D16] border border-[#F59E0B]/40 hover:bg-[#F59E0B]/10 text-left space-y-1 transition-colors"
                    >
                      <div className="font-semibold text-[#F59E0B]">Générer Mémo Binance Pay VIP</div>
                      <div className="font-mono-tabular text-[#F1F5F9]">49 USDT / mois</div>
                    </button>
                  </div>

                  {paymentInfo && (
                    <div className="p-4 rounded-lg bg-[#090D16] border border-[#10B981]/40 space-y-1.5 text-xs font-mono-tabular">
                      <div className="text-[#10B981] font-semibold">Instructions Binance Pay :</div>
                      <div>Binance ID destinataire : <strong className="text-[#F1F5F9]">{paymentInfo.binance_id || 'Non configuré'}</strong></div>
                      <div>Montant à envoyer : <strong className="text-[#F1F5F9]">{paymentInfo.amount_usdt} USDT</strong></div>
                      <div>Mémo obligatoire : <strong className="text-[#F59E0B]">{paymentInfo.memo}</strong></div>
                    </div>
                  )}
                </div>

                {/* Security PIN Configuration */}
                <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-5 space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="font-display font-semibold text-base text-[#F1F5F9]">
                      Code PIN de Sécurité (4 chiffres)
                    </h3>
                    <span className="text-xs font-mono-tabular text-[#10B981]">
                      {user.has_pin ? '● PIN Configuré' : '○ Aucun PIN'}
                    </span>
                  </div>
                  <form onSubmit={handleSavePin} className="space-y-3 text-xs">
                    {user.has_pin && (
                      <div>
                        <label className="block text-[#94A3B8] mb-1">Ancien Code PIN</label>
                        <input
                          type="password"
                          maxLength={4}
                          value={oldPin}
                          onChange={(e) => setOldPin(e.target.value)}
                          className="w-full px-3 py-2 bg-[#090D16] border border-white/10 rounded-lg font-mono-tabular text-[#F1F5F9]"
                          required
                        />
                      </div>
                    )}
                    <div>
                      <label className="block text-[#94A3B8] mb-1">Nouveau Code PIN (4 chiffres)</label>
                      <input
                        type="password"
                        maxLength={4}
                        value={newPin}
                        onChange={(e) => setNewPin(e.target.value)}
                        placeholder="1234"
                        className="w-full px-3 py-2 bg-[#090D16] border border-white/10 rounded-lg font-mono-tabular text-[#F1F5F9]"
                        required
                      />
                    </div>
                    <button
                      type="submit"
                      className="px-4 py-2 bg-[#1E293B] hover:bg-[#334155] border border-white/10 rounded-lg text-[#F1F5F9] font-semibold"
                    >
                      Enregistrer le Code PIN
                    </button>
                  </form>
                </div>
              </div>

              {/* Right: Direct Admin Support Messaging */}
              <div className="lg:col-span-6 bg-[#111827] border border-white/[0.07] rounded-xl p-5 space-y-4">
                <h3 className="font-display font-semibold text-base text-[#F1F5F9]">
                  Support Direct Administrateur
                </h3>
                <form onSubmit={handleCreateSupportTicket} className="space-y-3 text-xs">
                  <div>
                    <label className="block text-[#94A3B8] mb-1">Sujet</label>
                    <input
                      type="text"
                      value={ticketSubject}
                      onChange={(e) => setTicketSubject(e.target.value)}
                      placeholder="Validation paiement / Question stratégie..."
                      className="w-full px-3 py-2 bg-[#090D16] border border-white/10 rounded-lg text-[#F1F5F9]"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-[#94A3B8] mb-1">Message</label>
                    <textarea
                      rows={3}
                      value={ticketMessage}
                      onChange={(e) => setTicketMessage(e.target.value)}
                      placeholder="Décrivez votre demande..."
                      className="w-full px-3 py-2 bg-[#090D16] border border-white/10 rounded-lg text-[#F1F5F9]"
                      required
                    />
                  </div>
                  <button
                    type="submit"
                    className="px-4 py-2 bg-[#10B981] text-[#090D16] font-semibold rounded-lg"
                  >
                    Envoyer à l'Administrateur
                  </button>
                </form>

                <div className="space-y-2.5 pt-3 border-t border-white/[0.07]">
                  <div className="text-xs font-semibold text-[#94A3B8]">Vos échanges récents :</div>
                  {tickets.map((t) => (
                    <div key={t.id} className="p-3 rounded-lg bg-[#090D16] border border-white/[0.06] space-y-1.5 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-[#F1F5F9]">{t.subject}</span>
                        <span className="font-mono-tabular text-[11px] text-[#10B981] uppercase">{t.status}</span>
                      </div>
                      <p className="text-[#94A3B8]">{t.message}</p>
                      {t.admin_reply && (
                        <div className="p-2 rounded bg-[#10B981]/10 border border-[#10B981]/30 text-[#34D399]">
                          <strong>Réponse Admin :</strong> {t.admin_reply}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* =========================================================
              TAB 7: ADMIN CONSOLE & LOG DOCTOR DIAGNOSTICS
             ========================================================= */}
          {activeTab === 'admin' && (
            <div className="space-y-6">
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                {/* User Management Table */}
                <div className="lg:col-span-7 bg-[#111827] border border-white/[0.07] rounded-xl p-5 space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="font-display font-semibold text-base text-[#F1F5F9]">
                      Gestion des Utilisateurs & Validation Binance Pay
                    </h3>
                    <button
                      onClick={loadAdminOverview}
                      className="text-xs text-[#10B981] hover:underline flex items-center gap-1"
                    >
                      <RefreshCw className="w-3.5 h-3.5" /> Actualiser
                    </button>
                  </div>

                  <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse text-xs">
                      <thead>
                        <tr className="border-b border-white/[0.07] text-[#64748B] font-mono-tabular uppercase">
                          <th className="py-2.5 px-3">ID / Pseudo</th>
                          <th className="py-2.5 px-3">Rôle</th>
                          <th className="py-2.5 px-3">Mémo Pay</th>
                          <th className="py-2.5 px-3 text-right">Actions Admin</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/[0.05] font-mono-tabular">
                        {(adminData?.users || []).map((u: any) => (
                          <tr key={u.user_id} className="hover:bg-white/[0.02]">
                            <td className="py-2.5 px-3">
                              <div className="font-semibold text-[#F1F5F9]">{u.username || `User #${u.user_id}`}</div>
                              <div className="text-[10px] text-[#64748B]">{u.user_id}</div>
                            </td>
                            <td className="py-2.5 px-3 uppercase text-[#10B981]">{u.role}</td>
                            <td className="py-2.5 px-3 text-[#F59E0B]">{u.memo || '—'}</td>
                            <td className="py-2.5 px-3 text-right space-x-1.5">
                              {['tester', 'pro', 'vip'].map((r) => (
                                <button
                                  key={r}
                                  onClick={() =>
                                    apiFetch('/api/admin/user-role', {
                                      method: 'POST',
                                      body: JSON.stringify({ target_user_id: u.user_id, role: r, action: 'set_role' }),
                                    }).then((res) => {
                                      showToast(res.message, 'success');
                                      loadAdminOverview();
                                      loadUserAndCoreData();
                                    })
                                  }
                                  className="px-2 py-1 bg-[#1E293B] hover:bg-[#334155] rounded text-[10px] uppercase text-[#F1F5F9]"
                                >
                                  {r}
                                </button>
                              ))}
                              {u.memo && (
                                <button
                                  onClick={() =>
                                    apiFetch('/api/admin/user-role', {
                                      method: 'POST',
                                      body: JSON.stringify({ target_user_id: u.user_id, action: 'confirm_binance' }),
                                    }).then((res) => {
                                      showToast(res.message, 'success');
                                      loadAdminOverview();
                                    })
                                  }
                                  className="px-2 py-1 bg-[#10B981] text-[#090D16] font-semibold rounded text-[10px]"
                                >
                                  Valider Pay
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Log Doctor Diagnostics & Broadcast */}
                <div className="lg:col-span-5 space-y-6">
                  <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-5 space-y-4">
                    <h3 className="font-display font-semibold text-base text-[#F1F5F9]">
                      Diagnostic Système (Log Doctor)
                    </h3>
                    <div className="flex gap-2 text-xs">
                      <input
                        type="text"
                        value={doctorQuestion}
                        onChange={(e) => setDoctorQuestion(e.target.value)}
                        placeholder="Posez une question diagnostic (ex: erreur Binance, DB, Telegram)..."
                        className="flex-1 px-3 py-2 bg-[#090D16] border border-white/10 rounded-lg text-[#F1F5F9]"
                      />
                      <button
                        onClick={() =>
                          apiFetch('/api/admin/log-doctor', {
                            method: 'POST',
                            body: JSON.stringify({ question: doctorQuestion }),
                          }).then((r) => setDoctorReport(r.report))
                        }
                        className="px-3.5 py-2 bg-[#10B981] text-[#090D16] font-semibold rounded-lg"
                      >
                        Analyser
                      </button>
                    </div>
                    <pre className="p-3.5 rounded-lg bg-[#090D16] border border-white/[0.06] text-[11px] font-mono-tabular text-[#94A3B8] whitespace-pre-wrap max-h-64 overflow-y-auto">
                      {doctorReport || 'Chargement du diagnostic...'}
                    </pre>
                  </div>

                  {/* Admin Broadcast */}
                  <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-5 space-y-3">
                    <h3 className="font-display font-semibold text-base text-[#F1F5F9]">
                      Diffusion Globale (Broadcast)
                    </h3>
                    <input
                      type="text"
                      value={broadcastTitle}
                      onChange={(e) => setBroadcastTitle(e.target.value)}
                      placeholder="Titre de l'annonce..."
                      className="w-full px-3 py-2 bg-[#090D16] border border-white/10 rounded-lg text-xs text-[#F1F5F9]"
                    />
                    <textarea
                      rows={2}
                      value={broadcastBody}
                      onChange={(e) => setBroadcastBody(e.target.value)}
                      placeholder="Message diffusé à tous les utilisateurs..."
                      className="w-full px-3 py-2 bg-[#090D16] border border-white/10 rounded-lg text-xs text-[#F1F5F9]"
                    />
                    <button
                      onClick={() =>
                        apiFetch('/api/admin/broadcast', {
                          method: 'POST',
                          body: JSON.stringify({ title: broadcastTitle, message: broadcastBody }),
                        }).then((res) => {
                          setBroadcastTitle('');
                          setBroadcastBody('');
                          showToast(res.message, 'success');
                        })
                      }
                      className="w-full py-2 bg-[#F59E0B] text-[#090D16] font-semibold text-xs rounded-lg"
                    >
                      Diffuser à tous les comptes
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
export default App;
