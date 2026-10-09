import React, { useState, useEffect, useCallback } from 'react';
import './index.css';
import { apiFetch, setStoredSession, clearStoredSession, ApiError } from './api';
import { AppLang, getInitialLang, setSavedLang, tr } from './i18n';
import {
  UserProfile,
  MarketAnalysis,
  PaperStats,
  PaperPosition,
  PriceAlert,
  HistoricalSignal,
  TradingConfigState,
  SupportTicket,
  WebNotification,
  SecurityEvent,
} from './types';
import { PriceChart } from './components/PriceChart';
import { LandingPage } from './components/LandingPage';
import { StrategyLabView } from './components/StrategyLabView';
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
  Eye,
  EyeOff,
  FlaskConical,
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
  Menu,
  X,
} from 'lucide-react';

type ActiveTab =
  | 'intelligence'
  | 'paper'
  | 'alerts'
  | 'safety'
  | 'history'
  | 'account'
  | 'strategy_lab'
  | 'admin';

const SYMBOLS = [
  { id: 'BTCUSDT', label: 'BTC / USDT', category: 'Crypto Spot/Perp' },
  { id: 'ETHUSDT', label: 'ETH / USDT', category: 'Crypto Spot/Perp' },
  { id: 'XAUUSD', label: 'XAU / USD (Or)', labelEn: 'XAU / USD (Gold)', category: 'Matières Premières' },
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
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [lang, setLang] = useState<AppLang>(getInitialLang);

  // Auth & User State
  const [user, setUser] = useState<UserProfile | null>(null);
  const [authChecking, setAuthChecking] = useState(true);
  const [authSubmitting, setAuthSubmitting] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [authModal, setAuthModal] = useState<'login' | 'register' | null>(null);
  const [authEmail, setAuthEmail] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [authName, setAuthName] = useState('');
  const [authTelegram, setAuthTelegram] = useState('');
  const [googleOAuthEnabled, setGoogleOAuthEnabled] = useState(false);
  const [googlePendingToken, setGooglePendingToken] = useState<string | null>(null);
  const [capsLockOn, setCapsLockOn] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const handleToggleLang = useCallback(() => {
    const nextLang: AppLang = lang === 'fr' ? 'en' : 'fr';
    setLang(nextLang);
    setSavedLang(nextLang);
    if (user) {
      apiFetch('/api/user/preferences', {
        method: 'POST',
        body: JSON.stringify({ lang: nextLang }),
      })
        .then((r) => {
          if (r?.user) setUser(r.user);
        })
        .catch(() => {});
    }
  }, [lang, user]);

  const handleCapsLockEvent = useCallback((e: React.KeyboardEvent<HTMLInputElement> | React.MouseEvent<HTMLInputElement>) => {
    if (typeof e.getModifierState === 'function') {
      setCapsLockOn(Boolean(e.getModifierState('CapsLock')));
    }
  }, []);

  // Admin Quota Editor State
  const [editingQuotasUid, setEditingQuotasUid] = useState<number | null>(null);
  const [quotaForm, setQuotaForm] = useState({
    daily_analyses: 25,
    daily_scans: 15,
    max_alerts: 10,
    max_paper_trades: 30,
  });
  const [adminUserFilter, setAdminUserFilter] = useState<'ALL' | 'PENDING_APPROVAL' | 'APPROVED' | 'SUSPENDED' | 'REJECTED'>('ALL');

  // Market Intelligence State
  const [selectedSymbol, setSelectedSymbol] = useState('BTCUSDT');
  const [selectedTimeframe, setSelectedTimeframe] = useState('1h');
  const [selectedStyle, setSelectedStyle] = useState('day');
  const [analysis, setAnalysis] = useState<MarketAnalysis | null>(null);
  const [multiScans, setMultiScans] = useState<MarketAnalysis[]>([]);
  const [lastScannedAt, setLastScannedAt] = useState<number | null>(null);
  const [loadingAnalysis, setLoadingAnalysis] = useState(false);
  const [loadingScan, setLoadingScan] = useState(false);

  // Real-Time Binance Stream & Live Tickers State
  const [livePrices, setLivePrices] = useState<
    Record<
      string,
      {
        price: number;
        prevPrice: number;
        direction: 'up' | 'down' | 'neutral';
        change24h?: number;
        high24h?: number;
        low24h?: number;
        bid?: number;
        ask?: number;
        updatedAt: number;
      }
    >
  >({});
  const [priceFlash, setPriceFlash] = useState<Record<string, 'up' | 'down' | null>>({});
  const [wsConnected, setWsConnected] = useState(false);

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
      const currentUser: UserProfile = meRes.user;
      if (currentUser?.csrf_token) {
        localStorage.setItem('bitsure_csrf_token', currentUser.csrf_token);
      }
      if (currentUser?.google_oauth_enabled !== undefined) {
        setGoogleOAuthEnabled(Boolean(currentUser.google_oauth_enabled));
      }
      if (currentUser?.lang === 'en' || currentUser?.lang === 'fr') {
        const saved = localStorage.getItem('bitsure_lang');
        if (saved === 'en' || saved === 'fr') {
          currentUser.lang = saved;
          setLang(saved);
        } else {
          setLang(currentUser.lang);
          setSavedLang(currentUser.lang);
        }
      }
      setUser(currentUser);
      setAuthChecking(false);

      // Only load protected terminal data if the account is APPROVED
      if (!currentUser.approved && currentUser.account_status !== 'APPROVED' && !currentUser.is_admin) {
        return;
      }

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
      setAuthChecking(false);
      if (err instanceof ApiError && err.status === 401) {
        setUser(null);
      }
    }
  }, []);

  const updateLiveTick = useCallback(
    (
      sym: string,
      newPrice: number,
      extra?: { change24h?: number; high24h?: number; low24h?: number; bid?: number; ask?: number }
    ) => {
      if (!newPrice || newPrice <= 0) return;
      setLivePrices((prev) => {
        const oldEntry = prev[sym];
        const prevPrice = oldEntry?.price || newPrice;
        const dir: 'up' | 'down' | 'neutral' =
          newPrice > prevPrice ? 'up' : newPrice < prevPrice ? 'down' : oldEntry?.direction || 'neutral';
        if (newPrice !== prevPrice) {
          const flashDir = newPrice > prevPrice ? 'up' : 'down';
          setPriceFlash((pf) => ({ ...pf, [sym]: flashDir }));
          setTimeout(() => {
            setPriceFlash((pf) => (pf[sym] === flashDir ? { ...pf, [sym]: null } : pf));
          }, 450);
        }
        return {
          ...prev,
          [sym]: {
            price: newPrice,
            prevPrice,
            direction: dir,
            change24h: extra?.change24h ?? oldEntry?.change24h,
            high24h: extra?.high24h ?? oldEntry?.high24h,
            low24h: extra?.low24h ?? oldEntry?.low24h,
            bid: extra?.bid ?? oldEntry?.bid,
            ask: extra?.ask ?? oldEntry?.ask,
            updatedAt: Date.now(),
          },
        };
      });
    },
    []
  );

  const runAnalysis = useCallback(
    async (sym = selectedSymbol, tf = selectedTimeframe, st = selectedStyle, silent = false) => {
      if (!silent) setLoadingAnalysis(true);
      try {
        const res = await apiFetch(
          `/api/market/analyze?symbol=${encodeURIComponent(sym)}&timeframe=${encodeURIComponent(tf)}&style=${encodeURIComponent(st)}&lang=${lang}&silent=${silent ? '1' : '0'}`
        );
        const ana: MarketAnalysis = res.analysis;
        setAnalysis(ana);
        if (ana.current_price > 0) {
          updateLiveTick(ana.symbol || sym, ana.current_price);
        }
        if (!silent) {
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
        }
      } catch (err: any) {
        if (!silent) showToast(err.message, 'error');
      } finally {
        if (!silent) setLoadingAnalysis(false);
      }
    },
    [selectedSymbol, selectedTimeframe, selectedStyle, lang, newAlertPrice, showToast, updateLiveTick]
  );

  const runMultiScan = useCallback(
    async (tfOverride?: string, stOverride?: string, showFeedback = true) => {
      const tf = tfOverride || selectedTimeframe;
      const st = stOverride || selectedStyle;
      if (showFeedback) setLoadingScan(true);
      try {
        const res = await apiFetch(
          `/api/market/multi-scan?timeframe=${encodeURIComponent(tf)}&style=${encodeURIComponent(st)}&lang=${lang}&record=${showFeedback ? '1' : '0'}`
        );
        const scans: MarketAnalysis[] = res.scans || [];
        setMultiScans(scans);
        scans.forEach((sc) => {
          if (sc.current_price > 0) {
            updateLiveTick(sc.symbol, sc.current_price);
          }
        });
        setLastScannedAt(res.scanned_at ? Number(res.scanned_at) * 1000 : Date.now());
        if (showFeedback) {
          const validCount = scans.filter((s) => s.signal === 'BUY' || s.signal === 'SELL').length;
          showToast(
            lang === 'en'
              ? `Global scan completed (${tf.toUpperCase()}): ${scans.length} markets analyzed, ${validCount} active signal(s).`
              : `Scan global terminé (${tf.toUpperCase()}) : ${scans.length} marchés analysés, ${validCount} signal(s) actif(s).`,
            validCount > 0 ? 'success' : 'info'
          );
        }
      } catch (err: any) {
        if (showFeedback) showToast(err.message, 'error');
      } finally {
        if (showFeedback) setLoadingScan(false);
      }
    },
    [selectedTimeframe, selectedStyle, lang, showToast, updateLiveTick]
  );

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

  // 1. Direct Binance WebSocket real-time stream (BTCUSDT & ETHUSDT) + auto-reconnect
  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let unmounted = false;

    const endpoints = [
      'wss://data-stream.binance.vision/stream?streams=btcusdt@miniTicker/ethusdt@miniTicker/btcusdt@bookTicker/ethusdt@bookTicker',
      'wss://stream.binance.com:9443/stream?streams=btcusdt@miniTicker/ethusdt@miniTicker/btcusdt@bookTicker/ethusdt@bookTicker',
    ];
    let epIndex = 0;

    const connectWs = () => {
      if (unmounted) return;
      try {
        const url = endpoints[epIndex % endpoints.length];
        ws = new WebSocket(url);

        ws.onopen = () => {
          if (!unmounted) setWsConnected(true);
        };

        ws.onmessage = (evt) => {
          if (unmounted) return;
          try {
            const msg = JSON.parse(evt.data);
            const d = msg?.data || msg;
            if (!d || !d.s) return;
            const sym = String(d.s).toUpperCase();
            if (d.e === '24hrMiniTicker' || d.c) {
              const closeP = parseFloat(d.c);
              const openP = parseFloat(d.o);
              const highP = parseFloat(d.h);
              const lowP = parseFloat(d.l);
              const pct24 = openP > 0 ? ((closeP - openP) / openP) * 100 : undefined;
              if (closeP > 0) {
                updateLiveTick(sym, closeP, {
                  change24h: pct24,
                  high24h: highP > 0 ? highP : undefined,
                  low24h: lowP > 0 ? lowP : undefined,
                });
              }
            } else if (d.b && d.a) {
              const bid = parseFloat(d.b);
              const ask = parseFloat(d.a);
              const mid = bid > 0 && ask > 0 ? (bid + ask) / 2 : bid || ask;
              if (mid > 0) {
                updateLiveTick(sym, mid, { bid, ask });
              }
            }
          } catch {
            // ignore malformed frame
          }
        };

        ws.onerror = () => {
          if (!unmounted) setWsConnected(false);
        };

        ws.onclose = () => {
          if (unmounted) return;
          setWsConnected(false);
          epIndex += 1;
          reconnectTimer = setTimeout(connectWs, 2000);
        };
      } catch {
        setWsConnected(false);
        epIndex += 1;
        reconnectTimer = setTimeout(connectWs, 3000);
      }
    };

    connectWs();

    return () => {
      unmounted = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (ws) {
        try {
          ws.close();
        } catch {
          // ignore
        }
      }
    };
  }, [updateLiveTick]);

  const isApprovedUser = Boolean(user && (user.approved || user.account_status === 'APPROVED' || user.is_admin));

  // Initial session check on mount + Google OAuth postMessage listener
  useEffect(() => {
    loadUserAndCoreData();

    const applyGooglePending = (pending: any) => {
      if (!pending || !pending.google_pending_token) return;
      setGooglePendingToken(String(pending.google_pending_token));
      if (pending.email) setAuthEmail(String(pending.email));
      if (pending.display_name) setAuthName(String(pending.display_name));
      const nextMode = pending.mode === 'register' ? 'register' : 'login';
      setAuthModal(nextMode);
      setAuthError(null);
      try {
        sessionStorage.removeItem('bitsure_google_pending');
        localStorage.removeItem('bitsure_google_pending');
      } catch {
        // ignore
      }
      showToast(
        nextMode === 'login'
          ? `Compte Google (${pending.email}) vérifié. Veuillez saisir votre mot de passe pour finaliser la connexion.`
          : `Compte Google (${pending.email}) vérifié. Veuillez choisir un mot de passe pour finaliser votre inscription.`,
        'info'
      );
    };

    try {
      const rawPending = sessionStorage.getItem('bitsure_google_pending') || localStorage.getItem('bitsure_google_pending');
      if (rawPending) {
        applyGooglePending(JSON.parse(rawPending));
      }
    } catch {
      // ignore
    }

    const handleOAuthMessage = (event: MessageEvent) => {
      const data = event.data;
      if (!data || typeof data !== 'object') return;
      if (data.type === 'OAUTH_PASSWORD_REQUIRED') {
        applyGooglePending(data);
      } else if (data.type === 'OAUTH_AUTH_SUCCESS') {
        if (data.token) {
          setStoredSession(data.token, data.csrf_token || '');
        }
        setAuthModal(null);
        setAuthError(null);
        loadUserAndCoreData();
        showToast('Authentification Google réussie.', 'success');
      } else if (data.type === 'OAUTH_AUTH_ERROR') {
        setAuthError(data.error || 'Échec de la connexion avec Google.');
        showToast(data.error || 'Échec de la connexion avec Google.', 'error');
      }
    };

    window.addEventListener('message', handleOAuthMessage);
    return () => window.removeEventListener('message', handleOAuthMessage);
  }, [loadUserAndCoreData, showToast]);

  // 2. Continuous live synchronization ONLY when user is authenticated & APPROVED
  useEffect(() => {
    if (!isApprovedUser) return;

    runAnalysis(selectedSymbol, selectedTimeframe, selectedStyle, true);
    runMultiScan(selectedTimeframe, selectedStyle, false);

    // Fetch backend tickers (covers XAUUSD + fallback for BTCUSDT/ETHUSDT) every 2.5s
    const fetchBackendTickers = () => {
      apiFetch('/api/market/tickers')
        .then((res) => {
          if (Array.isArray(res.tickers)) {
            res.tickers.forEach((t: any) => {
              const p = Number(t.price || 0);
              if (p > 0) {
                updateLiveTick(t.symbol, p, {
                  bid: t.price_detail?.bid ? Number(t.price_detail.bid) : undefined,
                  ask: t.price_detail?.ask ? Number(t.price_detail.ask) : undefined,
                });
              }
            });
          }
        })
        .catch(() => {});
    };
    fetchBackendTickers();
    const tickerInterval = setInterval(fetchBackendTickers, 2500);

    // Sync Paper & Live positions + config every 5s
    const syncPositionsInterval = setInterval(() => {
      apiFetch('/api/paper/overview')
        .then((paperRes) => {
          setPaperStats(paperRes.stats);
          setOpenPaper(paperRes.open_positions || []);
          setClosedPaper(paperRes.closed_positions || []);
        })
        .catch(() => {});

      apiFetch('/api/trading/config')
        .then((res) => {
          setTradingCfg(res.config);
          setLiveTrades(res.live_trades || { open: [], closed: [] });
        })
        .catch(() => {});
    }, 5000);

    return () => {
      clearInterval(tickerInterval);
      clearInterval(syncPositionsInterval);
    };
  }, [isApprovedUser, updateLiveTick]);

  // 3. Continuous silent refresh of active symbol analysis (every 8s) and global multi-scan (every 15s) when APPROVED
  useEffect(() => {
    if (!isApprovedUser) return;
    const analysisTimer = setInterval(() => {
      runAnalysis(selectedSymbol, selectedTimeframe, selectedStyle, true);
    }, 8000);

    const scanTimer = setInterval(() => {
      runMultiScan(selectedTimeframe, selectedStyle, false);
    }, 15000);

    return () => {
      clearInterval(analysisTimer);
      clearInterval(scanTimer);
    };
  }, [isApprovedUser, selectedSymbol, selectedTimeframe, selectedStyle, runAnalysis, runMultiScan]);

  // 4. Keep Live Binance Account & Open Orders refreshed every 6s when on Safety tab
  useEffect(() => {
    if (!isApprovedUser || activeTab !== 'safety') return;
    const accTimer = setInterval(() => {
      apiFetch('/api/trading/account')
        .then((accRes) => {
          if (accRes.connected && accRes.account) {
            setLiveAccount(accRes.account);
          }
          setLiveOpenOrders(accRes.open_orders || []);
        })
        .catch(() => {});
    }, 6000);
    return () => clearInterval(accTimer);
  }, [isApprovedUser, activeTab]);

  useEffect(() => {
    if (!isApprovedUser) return;
    if (activeTab === 'admin' && user && !user.is_admin && user.role !== 'admin') {
      setActiveTab('intelligence');
      return;
    }
    if (activeTab === 'safety') loadLiveAccountAndOrders();
    if (activeTab === 'history') loadHistoryAndJournal();
    if (activeTab === 'account') loadTickets();
    if (activeTab === 'admin' && (user?.is_admin || user?.role === 'admin')) {
      loadAdminOverview();
      loadTickets();
    }
  }, [isApprovedUser, activeTab, user, loadLiveAccountAndOrders, loadHistoryAndJournal, loadTickets, loadAdminOverview]);

  // Handlers
  const handleAuthSubmit = async (e: React.FormEvent, modeOverride?: 'login' | 'register') => {
    e.preventDefault();
    setAuthError(null);
    setAuthSubmitting(true);
    const activeMode = modeOverride || authModal || 'login';
    try {
      const endpoint = activeMode === 'login' ? '/api/auth/login' : '/api/auth/register';
      const res = await apiFetch(endpoint, {
        method: 'POST',
        body: JSON.stringify({
          email: authEmail.trim(),
          password: authPassword,
          display_name: authName.trim(),
          telegram_handle: authTelegram.trim(),
          google_pending_token: googlePendingToken || undefined,
        }),
      });
      setStoredSession(res.token, res.csrf_token || res.user?.csrf_token || '');
      setUser(res.user);
      setAuthModal(null);
      setAuthPassword('');
      setGooglePendingToken(null);
      setViewMode('workspace');
      await loadUserAndCoreData();
      showToast(
        res.message || `Bienvenue sur Bitsure Teddy, ${res.user.display_name}`,
        res.user.approved ? 'success' : 'info'
      );
    } catch (err: any) {
      setAuthError(err.message || 'Erreur lors de la connexion.');
      showToast(err.message || 'Erreur lors de la connexion.', 'error');
    } finally {
      setAuthSubmitting(false);
    }
  };

  const handleGoogleLogin = async () => {
    setAuthError(null);
    try {
      const origin = window.location.origin;
      const res = await apiFetch(`/api/auth/google/url?origin=${encodeURIComponent(origin)}`);
      if (res.url) {
        window.location.href = res.url;
      }
    } catch (err: any) {
      setAuthError(err.message || 'Connexion Google indisponible.');
      showToast(err.message || 'Connexion Google indisponible.', 'error');
    }
  };

  const handleLogout = async () => {
    try {
      await apiFetch('/api/auth/logout', { method: 'POST' });
    } catch {
      // ignore network error on logout
    }
    clearStoredSession();
    setUser(null);
    setAdminData(null);
    setPaperStats(null);
    setOpenPaper([]);
    setClosedPaper([]);
    setAlerts([]);
    setTradingCfg(null);
    setAuthModal('login');
    showToast('Vous êtes déconnecté.', 'info');
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

  const authFormModal = (mode: 'login' | 'register', isFullPage = false) => (
    <div
      className={
        isFullPage
          ? 'bg-[#111827] border border-white/15 rounded-2xl max-w-md w-full p-6 sm:p-8 space-y-5 shadow-2xl'
          : 'bg-[#111827] border border-white/15 rounded-xl max-w-md w-full p-6 space-y-5'
      }
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-[#10B981]/15 border border-[#10B981]/40 flex items-center justify-center text-[#10B981] font-display font-bold">
            B
          </div>
          <div>
            <h3 className="font-display text-base sm:text-lg font-bold text-[#F1F5F9]">
              {mode === 'login' ? tr(lang, 'Connexion Bitsure Teddy') : tr(lang, 'Créer un compte Bitsure Teddy')}
            </h3>
            <p className="text-[11px] text-[#64748B]">
              {mode === 'login'
                ? tr(lang, 'Accès sécurisé au terminal quantitatif')
                : tr(lang, 'Inscription soumise à validation administrateur')}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleToggleLang}
            className="px-2 py-1 rounded bg-[#090D16] border border-white/10 text-[10px] font-mono-tabular uppercase text-[#94A3B8] hover:text-[#F1F5F9]"
          >
            {lang === 'fr' ? 'FR ▾ EN' : 'EN ▾ FR'}
          </button>
          {!isFullPage && (
            <button
              type="button"
              onClick={() => {
                setAuthModal(null);
                setAuthError(null);
              }}
              className="text-[#64748B] hover:text-[#F1F5F9]"
            >
              <XCircle className="w-5 h-5" />
            </button>
          )}
        </div>
      </div>

      {/* Mode Switch Tabs */}
      <div className="grid grid-cols-2 gap-1 p-1 bg-[#090D16] border border-white/10 rounded-lg text-xs">
        <button
          type="button"
          onClick={() => {
            setAuthModal('login');
            setAuthError(null);
          }}
          className={`py-2 rounded-md font-semibold transition-colors ${
            mode === 'login' ? 'bg-[#10B981] text-[#090D16]' : 'text-[#94A3B8] hover:text-[#F1F5F9]'
          }`}
        >
          {tr(lang, 'Connexion')}
        </button>
        <button
          type="button"
          onClick={() => {
            setAuthModal('register');
            setAuthError(null);
          }}
          className={`py-2 rounded-md font-semibold transition-colors ${
            mode === 'register' ? 'bg-[#10B981] text-[#090D16]' : 'text-[#94A3B8] hover:text-[#F1F5F9]'
          }`}
        >
          {tr(lang, 'Inscription')}
        </button>
      </div>

      {googlePendingToken && (
        <div className="p-3 rounded-lg bg-[#10B981]/15 border border-[#10B981]/40 text-xs text-[#34D399] flex items-start justify-between gap-2">
          <div className="flex items-start gap-2">
            <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5 text-[#10B981]" />
            <div>
              <div className="font-semibold text-[#F1F5F9]">
                {lang === 'en' ? `Google Identity Verified (${authEmail})` : `Identité Google vérifiée (${authEmail})`}
              </div>
              <div className="text-[11px] text-[#94A3B8] mt-0.5">
                {mode === 'login'
                  ? lang === 'en'
                    ? 'Please enter your Bitsure password to confirm and open your session.'
                    : 'Veuillez saisir votre mot de passe Bitsure pour confirmer et ouvrir votre session.'
                  : lang === 'en'
                  ? 'Please set your Bitsure password (min. 8 characters) to complete registration.'
                  : 'Veuillez définir votre mot de passe Bitsure (min. 8 caractères) pour finaliser votre inscription.'}
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={() => {
              setGooglePendingToken(null);
              setAuthEmail('');
            }}
            className="text-[10px] text-[#94A3B8] hover:text-[#F1F5F9] underline shrink-0"
          >
            {tr(lang, 'Changer')}
          </button>
        </div>
      )}

      {authError && (
        <div className="p-3 rounded-lg bg-[#F43F5E]/15 border border-[#F43F5E]/40 text-xs text-[#FB7185] flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>{authError}</span>
        </div>
      )}

      <form onSubmit={(e) => handleAuthSubmit(e, mode)} className="space-y-3.5 text-sm">
        {mode === 'register' && (
          <>
            <div>
              <label className="block text-xs text-[#94A3B8] mb-1">{tr(lang, 'Nom ou Pseudonyme')}</label>
              <input
                type="text"
                value={authName}
                onChange={(e) => setAuthName(e.target.value)}
                placeholder={tr(lang, 'Votre nom ou pseudo')}
                className="w-full px-3 py-2 bg-[#090D16] border border-white/10 rounded-lg text-[#F1F5F9]"
                required
              />
            </div>
            <div>
              <label className="block text-xs text-[#94A3B8] mb-1">{tr(lang, 'Identifiant Telegram (optionnel)')}</label>
              <input
                type="text"
                value={authTelegram}
                onChange={(e) => setAuthTelegram(e.target.value)}
                placeholder={tr(lang, '@votre_pseudo')}
                className="w-full px-3 py-2 bg-[#090D16] border border-white/10 rounded-lg text-[#F1F5F9]"
              />
            </div>
          </>
        )}
        <div>
          <label className="block text-xs text-[#94A3B8] mb-1">{tr(lang, 'Adresse Email')}</label>
          <input
            type="email"
            value={authEmail}
            onChange={(e) => setAuthEmail(e.target.value)}
            readOnly={Boolean(googlePendingToken)}
            placeholder={tr(lang, 'votre@email.com')}
            className={`w-full px-3 py-2 bg-[#090D16] border border-white/10 rounded-lg text-[#F1F5F9] ${
              googlePendingToken ? 'opacity-70 cursor-not-allowed' : ''
            }`}
            required
          />
        </div>
        <div>
          <label className="block text-xs text-[#94A3B8] mb-1">
            {tr(lang, 'Mot de passe')}{' '}
            {mode === 'register' && <span className="text-[#64748B]">{tr(lang, '(min. 8 caractères)')}</span>}{' '}
            <span className="text-[#10B981] font-semibold">*</span>
          </label>
          <div className="relative">
            <input
              type={showPassword ? 'text' : 'password'}
              value={authPassword}
              onChange={(e) => setAuthPassword(e.target.value)}
              onKeyDown={handleCapsLockEvent}
              onKeyUp={handleCapsLockEvent}
              onClick={handleCapsLockEvent}
              onBlur={() => setCapsLockOn(false)}
              placeholder="••••••••"
              minLength={mode === 'register' ? 8 : 1}
              className="w-full px-3 py-2 pr-10 bg-[#090D16] border border-white/10 rounded-lg text-[#F1F5F9]"
              required
            />
            <button
              type="button"
              onClick={() => setShowPassword((prev) => !prev)}
              aria-label={showPassword ? tr(lang, 'Masquer le mot de passe') : tr(lang, 'Afficher le mot de passe')}
              title={showPassword ? tr(lang, 'Masquer le mot de passe') : tr(lang, 'Afficher le mot de passe')}
              className="absolute inset-y-0 right-0 px-3 flex items-center text-[#64748B] hover:text-[#F1F5F9] transition-colors"
            >
              {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
          {capsLockOn && (
            <p className="mt-1 text-[11px] text-[#94A3B8]">
              {tr(lang, 'Le verrouillage majuscule (Caps Lock) est activé.')}
            </p>
          )}
        </div>
        <button
          type="submit"
          disabled={authSubmitting}
          className="w-full py-2.5 bg-[#10B981] hover:bg-[#059669] disabled:opacity-50 text-[#090D16] font-semibold rounded-lg transition-colors"
        >
          {authSubmitting
            ? tr(lang, 'Vérification en cours...')
            : googlePendingToken
            ? mode === 'login'
              ? tr(lang, 'Confirmer le mot de passe et se connecter')
              : tr(lang, 'Confirmer le mot de passe et créer le compte')
            : mode === 'login'
            ? tr(lang, 'Se connecter')
            : tr(lang, "Soumettre ma demande d'accès")}
        </button>
      </form>

      <div className="relative flex py-1 items-center">
        <div className="flex-grow border-t border-white/10" />
        <span className="flex-shrink mx-3 text-[11px] text-[#64748B] uppercase">{tr(lang, 'ou')}</span>
        <div className="flex-grow border-t border-white/10" />
      </div>

      <button
        type="button"
        onClick={handleGoogleLogin}
        className="w-full py-2.5 px-4 bg-[#1E293B] hover:bg-[#334155] border border-white/15 text-[#F1F5F9] text-xs font-semibold rounded-lg transition-colors flex items-center justify-center gap-2"
      >
        <svg className="w-4 h-4" viewBox="0 0 24 24" aria-hidden="true">
          <path
            fill="#4285F4"
            d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.82-2.4 3.68v3.05h3.88c2.27-2.09 3.665-5.17 3.665-9.17z"
          />
          <path
            fill="#34A853"
            d="M12 24c3.3 0 6.08-1.09 8.1-2.96l-3.88-3.05c-1.08.72-2.45 1.16-4.22 1.16-3.24 0-5.99-2.19-6.97-5.14H1.02v3.14C3.03 21.14 7.21 24 12 24z"
          />
          <path
            fill="#FBBC05"
            d="M5.03 14.01c-.25-.72-.39-1.5-.39-2.31s.14-1.59.39-2.31V6.25H1.02C.37 7.54 0 9.01 0 11.7s.37 4.16 1.02 5.45l4.01-3.14z"
          />
          <path
            fill="#EA4335"
            d="M12 4.75c1.8 0 3.41.62 4.68 1.84l3.51-3.51C18.07 1.19 15.3 0 12 0 7.21 0 3.03 2.86 1.02 6.25l4.01 3.14c.98-2.95 3.73-5.14 6.97-5.14z"
          />
        </svg>
        <span>{tr(lang, 'Continuer avec Google')}</span>
      </button>

      {mode === 'register' && (
        <div className="p-3 rounded-lg bg-[#090D16] border border-white/[0.06] text-[11px] text-[#94A3B8] leading-relaxed">
          <strong className="text-[#10B981]">
            {lang === 'en' ? 'Security & Approval:' : 'Sécurité & Validation :'}
          </strong>{' '}
          {lang === 'en' ? (
            <>
              All new registrations are placed in <code className="text-[#F59E0B]">PENDING_APPROVAL</code> status until
              approved by the Bitsure administrator.
            </>
          ) : (
            <>
              Toute nouvelle inscription est placée en statut <code className="text-[#F59E0B]">PENDING_APPROVAL</code>{' '}
              jusqu&apos;à son approbation par l&apos;administrateur Bitsure.
            </>
          )}
        </div>
      )}
    </div>
  );

  if (viewMode === 'landing') {
    return (
      <>
        <LandingPage
          lang={lang}
          onToggleLang={handleToggleLang}
          onEnterWorkspace={() => {
            if (user) {
              setViewMode('workspace');
            } else {
              setAuthModal('login');
            }
          }}
          onOpenAuthModal={(m) => {
            setAuthError(null);
            setAuthModal(m);
          }}
        />
        {authModal && (
          <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
            {authFormModal(authModal, false)}
          </div>
        )}
      </>
    );
  }

  // Loading state while verifying server session
  if (authChecking) {
    return (
      <div className="min-h-screen bg-[#090D16] text-[#F1F5F9] flex items-center justify-center p-6">
        <div className="flex flex-col items-center gap-3">
          <RefreshCw className="w-6 h-6 text-[#10B981] animate-spin" />
          <p className="text-xs font-mono-tabular text-[#94A3B8]">
            {tr(lang, 'Vérification sécurisée de votre session...')}
          </p>
        </div>
      </div>
    );
  }

  // Strict Authentication Gate: Unauthenticated visitors must log in or register
  if (!user) {
    const activeAuthMode = authModal || 'login';
    return (
      <div className="min-h-screen bg-[#090D16] text-[#F1F5F9] flex flex-col justify-between p-4 sm:p-8">
        <header className="max-w-6xl w-full mx-auto flex items-center justify-between">
          <button
            type="button"
            onClick={() => setViewMode('landing')}
            className="flex items-center gap-2.5 text-left"
          >
            <div className="w-8 h-8 rounded-lg bg-[#10B981]/15 border border-[#10B981]/40 flex items-center justify-center text-[#10B981] font-display font-bold">
              B
            </div>
            <div>
              <div className="font-display font-bold text-sm tracking-tight text-[#F1F5F9]">BITSURE TEDDY</div>
              <div className="text-[10px] font-mono-tabular text-[#64748B]">
                {tr(lang, 'TERMINAL QUANTITATIF PROTÉGÉ')}
              </div>
            </div>
          </button>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleToggleLang}
              className="px-3 py-1.5 rounded-lg bg-[#111827] border border-white/10 text-xs font-mono-tabular uppercase text-[#94A3B8] hover:text-[#F1F5F9]"
            >
              {lang === 'fr' ? 'FR ▾ EN' : 'EN ▾ FR'}
            </button>
            <button
              type="button"
              onClick={() => setViewMode('landing')}
              className="px-3 py-1.5 rounded-lg bg-[#111827] border border-white/10 text-xs text-[#94A3B8] hover:text-[#F1F5F9]"
            >
              {tr(lang, 'Présentation & Tarifs')}
            </button>
          </div>
        </header>

        <div className="flex-1 flex items-center justify-center py-8">
          {authFormModal(activeAuthMode, true)}
        </div>

        <footer className="text-center text-[11px] text-[#64748B] font-mono-tabular">
          {lang === 'en'
            ? 'Bitsure Teddy • Mandatory server authentication • Active access protection & quotas'
            : 'Bitsure Teddy • Authentification serveur obligatoire • Protection des accès & quotas actifs'}
        </footer>
      </div>
    );
  }

  // Mandatory Account Approval Gate: PENDING_APPROVAL, REJECTED, or SUSPENDED accounts cannot access the terminal
  if (!isApprovedUser) {
    const status = user.account_status || 'PENDING_APPROVAL';
    const isRejected = status === 'REJECTED';
    const isSuspended = status === 'SUSPENDED';

    return (
      <div className="min-h-screen bg-[#090D16] text-[#F1F5F9] flex flex-col justify-between p-4 sm:p-8">
        <header className="max-w-4xl w-full mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-[#10B981]/15 border border-[#10B981]/40 flex items-center justify-center text-[#10B981] font-display font-bold">
              B
            </div>
            <div>
              <div className="font-display font-bold text-sm tracking-tight text-[#F1F5F9]">BITSURE TEDDY</div>
              <div className="text-[10px] font-mono-tabular text-[#64748B]">{tr(lang, "CONTRÔLE D'ACCÈS")}</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleToggleLang}
              className="px-2.5 py-1.5 rounded-lg bg-[#111827] border border-white/10 text-xs font-mono-tabular uppercase text-[#94A3B8] hover:text-[#F1F5F9]"
            >
              {lang === 'fr' ? 'FR ▾ EN' : 'EN ▾ FR'}
            </button>
            <button
              type="button"
              onClick={() => loadUserAndCoreData()}
              className="px-3 py-1.5 rounded-lg bg-[#1E293B] hover:bg-[#334155] border border-white/10 text-xs text-[#F1F5F9] flex items-center gap-1.5"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>{tr(lang, 'Vérifier mon statut')}</span>
            </button>
            <button
              type="button"
              onClick={handleLogout}
              className="px-3 py-1.5 rounded-lg bg-[#F43F5E]/15 hover:bg-[#F43F5E]/25 border border-[#F43F5E]/40 text-xs text-[#FB7185] flex items-center gap-1.5"
            >
              <LogOut className="w-3.5 h-3.5" />
              <span>{tr(lang, 'Déconnexion')}</span>
            </button>
          </div>
        </header>

        <div className="flex-1 flex items-center justify-center py-8">
          <div className="bg-[#111827] border border-white/15 rounded-2xl max-w-lg w-full p-6 sm:p-8 space-y-5 text-center">
            <div
              className={`w-14 h-14 rounded-2xl mx-auto flex items-center justify-center border ${
                isRejected || isSuspended
                  ? 'bg-[#F43F5E]/15 border-[#F43F5E]/40 text-[#FB7185]'
                  : 'bg-[#F59E0B]/15 border-[#F59E0B]/40 text-[#F59E0B]'
              }`}
            >
              {isRejected || isSuspended ? <ShieldAlert className="w-7 h-7" /> : <Clock className="w-7 h-7" />}
            </div>

            <div className="space-y-2">
              <span
                className={`inline-block px-2.5 py-0.5 rounded text-[11px] font-mono-tabular font-bold uppercase border ${
                  isRejected || isSuspended
                    ? 'bg-[#F43F5E]/15 border-[#F43F5E]/40 text-[#FB7185]'
                    : 'bg-[#F59E0B]/15 border-[#F59E0B]/40 text-[#F59E0B]'
                }`}
              >
                {lang === 'en' ? 'Status:' : 'Statut :'} {status}
              </span>
              <h2 className="font-display text-xl font-bold text-[#F1F5F9]">
                {isRejected
                  ? tr(lang, "Demande d'accès refusée")
                  : isSuspended
                  ? tr(lang, 'Compte suspendu')
                  : tr(lang, "Compte en attente d'approbation")}
              </h2>
              <p className="text-xs sm:text-sm text-[#94A3B8] leading-relaxed">
                {isRejected
                  ? lang === 'en'
                    ? 'Your access request to Bitsure Teddy was declined by the administrator. You cannot access analysis or trading features.'
                    : "Votre demande d'accès à Bitsure Teddy a été refusée par l'administrateur. Vous ne pouvez pas accéder aux fonctionnalités d'analyse ou de trading."
                  : isSuspended
                  ? lang === 'en'
                    ? 'Your account has been temporarily suspended by the administrator. Contact Bitsure support for more information.'
                    : "Votre compte a été temporairement suspendu par l'administrateur. Contactez le support Bitsure pour plus d'informations."
                  : lang === 'en'
                  ? 'Your registration has been recorded. For security reasons, access to market analyses, scans, alerts, and trading tools is locked until the administrator approves your account.'
                  : "Votre inscription a bien été enregistrée. Par mesure de sécurité, l'accès aux analyses, scans, alertes et outils de trading est bloqué tant que l'administrateur n'a pas approuvé votre compte."}
              </p>
            </div>

            <div className="p-4 rounded-xl bg-[#090D16] border border-white/[0.07] text-left text-xs font-mono-tabular space-y-1.5">
              <div className="flex justify-between">
                <span className="text-[#64748B]">{tr(lang, 'Compte :')}</span>
                <span className="text-[#F1F5F9]">{user.email}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#64748B]">{tr(lang, 'Nom :')}</span>
                <span className="text-[#F1F5F9]">{user.display_name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#64748B]">{tr(lang, 'ID Utilisateur :')}</span>
                <span className="text-[#94A3B8]">#{user.user_id}</span>
              </div>
            </div>

            <div className="flex flex-col sm:flex-row gap-2.5 pt-2">
              <button
                type="button"
                onClick={() => loadUserAndCoreData()}
                className="flex-1 py-2.5 bg-[#10B981] hover:bg-[#059669] text-[#090D16] font-semibold text-xs rounded-lg transition-colors flex items-center justify-center gap-1.5"
              >
                <RefreshCw className="w-4 h-4" />
                <span>{tr(lang, 'Actualiser mon statut')}</span>
              </button>
              <button
                type="button"
                onClick={handleLogout}
                className="flex-1 py-2.5 bg-[#1E293B] hover:bg-[#334155] border border-white/10 text-[#F1F5F9] font-semibold text-xs rounded-lg transition-colors flex items-center justify-center gap-1.5"
              >
                <LogOut className="w-4 h-4" />
                <span>{tr(lang, 'Se déconnecter')}</span>
              </button>
            </div>
          </div>
        </div>
        <div />
      </div>
    );
  }

  const ind = analysis?.indicators || {};
  const tfTrends = ind.timeframe_trends || {};
  const tfAlign = ind.tf_alignment || {};

  const isAdminUser = Boolean(user?.is_admin || user?.role === 'admin');
  const navItems = [
    { id: 'intelligence', label: tr(lang, 'Market Intelligence'), icon: Activity },
    { id: 'paper', label: tr(lang, 'Paper Trading'), icon: Layers, count: openPaper.length },
    { id: 'alerts', label: tr(lang, 'Alertes & Watchlist'), icon: Bell, count: alerts.length },
    {
      id: 'safety',
      label: tr(lang, 'Auto-Trade & Safety'),
      icon: ShieldCheck,
      warn: tradingCfg?.safety_lock || tradingCfg?.safety_warn,
      apiConnected: Boolean(tradingCfg?.credentials_valid),
    },
    { id: 'history', label: tr(lang, 'Historique & Journal'), icon: BookOpen },
    { id: 'account', label: tr(lang, 'Compte, Plans & PIN'), icon: CreditCard },
    ...(isAdminUser
      ? [
          { id: 'strategy_lab', label: tr(lang, 'Strategy Lab (Backtest)'), icon: FlaskConical },
          { id: 'admin', label: tr(lang, 'Admin & Log Doctor'), icon: Terminal },
        ]
      : []),
  ];

  // Grouped Mobile Hub structure (4 primary tabs on mobile + sub-switcher strip)
  const mobileHubGroups = [
    {
      hubId: 'markets',
      label: tr(lang, 'Marchés'),
      icon: Activity,
      tabs: [
        { id: 'intelligence' as ActiveTab, label: tr(lang, 'Market Intelligence'), icon: Activity },
        { id: 'alerts' as ActiveTab, label: tr(lang, 'Alertes & Watchlist'), icon: Bell, count: alerts.length },
      ],
    },
    {
      hubId: 'trading',
      label: tr(lang, 'Trading'),
      icon: Layers,
      tabs: [
        { id: 'paper' as ActiveTab, label: tr(lang, 'Paper Trading'), icon: Layers, count: openPaper.length },
        { id: 'safety' as ActiveTab, label: tr(lang, 'Auto-Trade & Safety'), icon: ShieldCheck },
      ],
    },
    {
      hubId: 'tracking',
      label: tr(lang, 'Suivi'),
      icon: BookOpen,
      tabs: [
        { id: 'history' as ActiveTab, label: tr(lang, 'Historique & Journal'), icon: BookOpen },
        { id: 'account' as ActiveTab, label: tr(lang, 'Compte, Plans & PIN'), icon: CreditCard },
      ],
    },
    ...(isAdminUser
      ? [
          {
            hubId: 'admin_hub',
            label: 'Admin & Lab',
            icon: FlaskConical,
            tabs: [
              { id: 'strategy_lab' as ActiveTab, label: tr(lang, 'Strategy Lab (Backtest)'), icon: FlaskConical },
              { id: 'admin' as ActiveTab, label: tr(lang, 'Admin & Log Doctor'), icon: Terminal },
            ],
          },
        ]
      : [
          {
            hubId: 'account_hub',
            label: tr(lang, 'Compte'),
            icon: CreditCard,
            tabs: [{ id: 'account' as ActiveTab, label: tr(lang, 'Compte, Plans & PIN'), icon: CreditCard }],
          },
        ]),
  ];
  const currentMobileHub =
    mobileHubGroups.find((g) => g.tabs.some((t) => t.id === activeTab)) || mobileHubGroups[0];

  return (
    <div className="min-h-screen bg-[#090D16] text-[#F1F5F9] flex flex-col md:flex-row">
      {/* Left Single Navigation Sidebar (Hidden on mobile, fixed sidebar on desktop) */}
      <aside className="hidden md:flex w-64 shrink-0 border-r border-white/[0.07] bg-[#0B101B] flex-col justify-between">
        <div>
          {/* Brand Logo */}
          <div className="h-16 px-5 border-b border-white/[0.07] flex items-center justify-between">
            <button
              onClick={() => {
                setViewMode('landing');
              }}
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
            {navItems.map((item) => {
              const Icon = item.icon;
              const active = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => {
                    setActiveTab(item.id as ActiveTab);
                    setMobileMenuOpen(false);
                  }}
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
            <div className="flex items-center justify-between text-[11px] font-mono-tabular uppercase tracking-wider text-[#64748B] mb-2">
              <span>{tr(lang, 'Marchés Documentés')}</span>
              <span className="inline-flex items-center gap-1 text-[9px] text-[#10B981]">
                <span className="w-1.5 h-1.5 rounded-full bg-[#10B981] animate-ping" />
                LIVE
              </span>
            </div>
            <div className="space-y-1">
              {SYMBOLS.map((s) => {
                const isSelected = selectedSymbol === s.id;
                const tick = livePrices[s.id];
                const flash = priceFlash[s.id];
                return (
                  <button
                    key={s.id}
                    onClick={() => {
                      setSelectedSymbol(s.id);
                      setActiveTab('intelligence');
                      setMobileMenuOpen(false);
                      runAnalysis(s.id, selectedTimeframe, selectedStyle);
                    }}
                    className={`w-full px-2.5 py-1.5 rounded text-xs flex items-center justify-between transition-colors ${
                      isSelected
                        ? 'bg-[#1E293B] text-[#F1F5F9] font-medium'
                        : 'text-[#94A3B8] hover:bg-white/[0.03] hover:text-[#F1F5F9]'
                    }`}
                  >
                    <span className="font-mono-tabular">{s.id}</span>
                    {tick?.price ? (
                      <span
                        className={`font-mono-tabular text-[11px] font-semibold transition-colors ${
                          flash === 'up'
                            ? 'text-[#10B981]'
                            : flash === 'down'
                            ? 'text-[#F43F5E]'
                            : tick.direction === 'up'
                            ? 'text-[#34D399]'
                            : tick.direction === 'down'
                            ? 'text-[#FB7185]'
                            : 'text-[#F1F5F9]'
                        }`}
                      >
                        {tick.price.toLocaleString('en-US', {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 2,
                        })}
                      </span>
                    ) : (
                      <ChevronRight className="w-3.5 h-3.5 text-[#64748B]" />
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Bottom User Profile */}
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
                  Quota:{' '}
                  {user.remaining_requests < 0 || user.remaining_requests >= 999
                    ? tr(lang, 'Illimité')
                    : `${user.remaining_requests}/${user.daily_limit}`}
                </span>
              </div>
            </div>
          )}

          <div className="flex gap-2">
            <button
              onClick={() => {
                setViewMode('landing');
                setMobileMenuOpen(false);
              }}
              className="flex-1 py-1.5 text-xs text-[#94A3B8] hover:text-[#F1F5F9] border border-white/10 rounded hover:bg-white/[0.04] transition-colors"
            >
              {tr(lang, 'Présentation')}
            </button>
            <button
              onClick={handleLogout}
              className="px-3 py-1.5 text-xs text-[#FB7185] hover:bg-[#F43F5E]/15 border border-[#F43F5E]/30 rounded transition-colors flex items-center gap-1"
              title={tr(lang, 'Se déconnecter')}
            >
              <LogOut className="w-3.5 h-3.5" />
              <span>{tr(lang, 'Quitter')}</span>
            </button>
          </div>
        </div>
      </aside>

      {/* Main Workspace Area */}
      <div className="flex-1 flex flex-col min-w-0 pb-20 md:pb-0">
        {/* Top Utility & Market Bar */}
        <header className="min-h-14 py-2 px-3 sm:px-6 border-b border-white/[0.07] bg-[#0B101B]/95 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-1.5 sm:gap-3 flex-wrap">
            {/* Compact Brand Badge on Mobile */}
            <button
              type="button"
              onClick={() => setViewMode('landing')}
              className="md:hidden w-8 h-8 rounded-lg bg-[#10B981]/15 border border-[#10B981]/40 flex items-center justify-center text-[#10B981] font-display font-bold text-xs shrink-0"
              title="Bitsure Teddy"
            >
              B
            </button>

            <select
              value={selectedSymbol}
              onChange={(e) => {
                setSelectedSymbol(e.target.value);
                runAnalysis(e.target.value, selectedTimeframe, selectedStyle);
              }}
              className="px-2 sm:px-3 py-1.5 bg-[#111827] border border-white/15 rounded-lg text-xs font-mono-tabular font-semibold text-[#F1F5F9]"
            >
              {SYMBOLS.map((s) => (
                <option key={s.id} value={s.id}>
                  {lang === 'en' && s.labelEn ? s.labelEn : s.label}
                </option>
              ))}
            </select>

            <div className="flex items-center bg-[#111827] border border-white/10 rounded-lg p-0.5 overflow-x-auto max-w-full">
              {TIMEFRAMES.map((tf) => (
                <button
                  key={tf}
                  onClick={() => {
                    setSelectedTimeframe(tf);
                    runAnalysis(selectedSymbol, tf, selectedStyle);
                    runMultiScan(tf, selectedStyle, false);
                  }}
                  className={`px-2 sm:px-2.5 py-1 rounded-md text-xs font-mono-tabular transition-colors ${
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
                runMultiScan(selectedTimeframe, e.target.value, false);
              }}
              className="hidden sm:block px-2.5 sm:px-3 py-1.5 bg-[#111827] border border-white/10 rounded-lg text-xs text-[#F1F5F9]"
            >
              {STYLES.map((st) => (
                <option key={st.id} value={st.id}>
                  Style : {st.label}
                </option>
              ))}
            </select>

            <button
              onClick={() => {
                runAnalysis(selectedSymbol, selectedTimeframe, selectedStyle);
                runMultiScan(selectedTimeframe, selectedStyle, false);
              }}
              disabled={loadingAnalysis}
              className="px-2 sm:px-3 py-1.5 bg-[#1E293B] hover:bg-[#334155] border border-white/10 rounded-lg text-xs text-[#F1F5F9] flex items-center gap-1.5 transition-colors"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loadingAnalysis ? 'animate-spin text-[#10B981]' : ''}`} />
              <span className="hidden sm:inline">{tr(lang, 'Actualiser')}</span>
            </button>
          </div>

          <div className="flex items-center gap-2 sm:gap-3 text-xs">
            {/* Live Binance Ticker Strip */}
            <div className="hidden xl:flex items-center gap-2 bg-[#111827] border border-white/[0.08] px-3 py-1 rounded-lg font-mono-tabular">
              <span
                className="inline-flex items-center gap-1.5 pr-2 border-r border-white/10 text-[10px] font-bold text-[#10B981]"
                title={
                  wsConnected
                    ? lang === 'en'
                      ? 'Real-time Binance WebSocket connected'
                      : 'Flux WebSocket Binance temps réel connecté'
                    : lang === 'en'
                    ? 'Real-time synchronization active'
                    : 'Synchronisation temps réel active'
                }
              >
                <span className="w-2 h-2 rounded-full bg-[#10B981] animate-pulse" />
                {lang === 'en' ? 'LIVE' : 'DIRECT'}
              </span>
              {SYMBOLS.map((symObj) => {
                const t = livePrices[symObj.id];
                const fl = priceFlash[symObj.id];
                return (
                  <button
                    key={symObj.id}
                    type="button"
                    onClick={() => {
                      setSelectedSymbol(symObj.id);
                      runAnalysis(symObj.id, selectedTimeframe, selectedStyle);
                    }}
                    className={`px-2 py-0.5 rounded flex items-center gap-1.5 transition-colors ${
                      fl === 'up'
                        ? 'bg-[#10B981]/20 text-[#10B981]'
                        : fl === 'down'
                        ? 'bg-[#F43F5E]/20 text-[#F43F5E]'
                        : 'hover:bg-white/[0.04]'
                    }`}
                  >
                    <span className="text-[#94A3B8] font-semibold">{symObj.id}</span>
                    <span
                      className={`font-bold ${
                        t?.direction === 'up'
                          ? 'text-[#10B981]'
                          : t?.direction === 'down'
                          ? 'text-[#F43F5E]'
                          : 'text-[#F1F5F9]'
                      }`}
                    >
                      {t?.price
                        ? t.price.toLocaleString('en-US', {
                            minimumFractionDigits: 2,
                            maximumFractionDigits: 2,
                          })
                        : '—'}
                    </span>
                    {t?.change24h !== undefined && (
                      <span
                        className={`text-[10px] ${
                          t.change24h >= 0 ? 'text-[#10B981]' : 'text-[#F43F5E]'
                        }`}
                      >
                        {t.change24h >= 0 ? '+' : ''}
                        {t.change24h.toFixed(2)}%
                      </span>
                    )}
                  </button>
                );
              })}
            </div>

            {paperStats && (
              <div className="hidden lg:flex items-center gap-4 font-mono-tabular bg-[#111827] border border-white/[0.07] px-3.5 py-1.5 rounded-lg">
                <span className="text-[#94A3B8]">
                  {lang === 'en' ? 'Paper Equity:' : 'Équité Paper :'}{' '}
                  <strong className="text-[#F1F5F9]">
                    {Number(paperStats.equity ?? 0).toLocaleString('en-US', {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}{' '}
                    USDT
                  </strong>
                </span>
                <span className={(paperStats.total_pnl ?? 0) >= 0 ? 'text-[#10B981]' : 'text-[#F43F5E]'}>
                  PnL : {(paperStats.total_pnl ?? 0) >= 0 ? '+' : ''}
                  {Number(paperStats.total_pnl ?? 0).toFixed(2)} USDT
                </span>
              </div>
            )}

            <button
              onClick={() => {
                handleToggleLang();
                runAnalysis(selectedSymbol, selectedTimeframe, selectedStyle, true);
                runMultiScan(selectedTimeframe, selectedStyle, false);
              }}
              title={lang === 'en' ? 'Switch language (FR / EN)' : 'Changer de langue (FR / EN)'}
              className="px-2.5 py-1.5 bg-[#111827] border border-white/10 rounded-lg font-mono-tabular uppercase text-[#F1F5F9] hover:border-[#10B981]/50 flex items-center gap-1"
            >
              <span className={lang === 'fr' ? 'text-[#10B981] font-bold' : 'text-[#64748B]'}>FR</span>
              <span className="text-[#64748B]">/</span>
              <span className={lang === 'en' ? 'text-[#10B981] font-bold' : 'text-[#64748B]'}>EN</span>
            </button>

            <button
              onClick={handleLogout}
              className="md:hidden p-1.5 bg-[#F43F5E]/15 border border-[#F43F5E]/30 rounded-lg text-[#FB7185]"
              title={tr(lang, 'Se déconnecter')}
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          </div>
        </header>

        {/* Mobile Consolidated Sub-Tab Pill Bar (Shown on mobile to switch cleanly within the active Hub) */}
        {currentMobileHub && currentMobileHub.tabs.length > 1 && (
          <div className="md:hidden px-3 pt-2.5">
            <div className="flex items-center justify-between mb-1.5 px-1">
              <span className="text-[10px] font-mono-tabular uppercase tracking-wider text-[#64748B]">
                {lang === 'en' ? `Section: ${currentMobileHub.label}` : `Pôle : ${currentMobileHub.label}`}
              </span>
              <span className="text-[10px] font-mono-tabular text-[#10B981]">
                {currentMobileHub.tabs.findIndex((t) => t.id === activeTab) + 1}/{currentMobileHub.tabs.length}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-1.5 p-1 bg-[#111827] border border-white/[0.08] rounded-xl">
              {currentMobileHub.tabs.map((subTab) => {
                const SubIcon = subTab.icon;
                const isSubActive = activeTab === subTab.id;
                return (
                  <button
                    key={subTab.id}
                    type="button"
                    onClick={() => setActiveTab(subTab.id)}
                    className={`py-2 px-2.5 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors ${
                      isSubActive
                        ? 'bg-[#10B981] text-[#090D16] shadow-sm'
                        : 'text-[#94A3B8] hover:text-[#F1F5F9]'
                    }`}
                  >
                    <SubIcon className="w-3.5 h-3.5 shrink-0" />
                    <span className="truncate">{subTab.label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

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
        <main className="p-3 sm:p-6 space-y-6 max-w-[1600px] w-full mx-auto">
          {/* =========================================================
              TAB 1: MARKET INTELLIGENCE & TEDDY SCORE WORKSPACE
             ========================================================= */}
          {activeTab === 'intelligence' && (
            <>
              {/* Top 4 KPI Cards (Max 3 data points per card, 24px gap) */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
                {/* KPI 1: Live Price & Market Status */}
                {(() => {
                  const symKey = analysis?.symbol || selectedSymbol;
                  const liveTick = livePrices[symKey];
                  const flash = priceFlash[symKey];
                  const displayPrice = liveTick?.price || analysis?.current_price || 0;
                  return (
                    <div
                      className={`bg-[#111827] border rounded-xl p-5 space-y-2 transition-colors duration-300 ${
                        flash === 'up'
                          ? 'border-[#10B981]/60 bg-[#10B981]/[0.05]'
                          : flash === 'down'
                          ? 'border-[#F43F5E]/60 bg-[#F43F5E]/[0.05]'
                          : 'border-white/[0.07]'
                      }`}
                    >
                      <div className="flex items-center justify-between text-xs text-[#94A3B8]">
                        <span className="flex items-center gap-1.5">
                          <span>{lang === 'en' ? `Live Price (${symKey})` : `Cours Temps Réel (${symKey})`}</span>
                          <span
                            className="w-2 h-2 rounded-full bg-[#10B981] animate-ping"
                            title={lang === 'en' ? 'Live feed' : 'Flux en direct'}
                          />
                        </span>
                        <span className="font-mono-tabular text-[#10B981]">
                          {analysis?.market_status?.is_open ? tr(lang, '● LIVE 24/7') : tr(lang, '○ FERMÉ')}
                        </span>
                      </div>
                      <div className="flex items-baseline justify-between gap-2">
                        <div
                          className={`font-mono-tabular text-2xl font-bold transition-colors ${
                            flash === 'up'
                              ? 'text-[#10B981]'
                              : flash === 'down'
                              ? 'text-[#F43F5E]'
                              : liveTick?.direction === 'up'
                              ? 'text-[#34D399]'
                              : liveTick?.direction === 'down'
                              ? 'text-[#FB7185]'
                              : 'text-[#F1F5F9]'
                          }`}
                        >
                          {displayPrice
                            ? displayPrice.toLocaleString('en-US', {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2,
                              })
                            : '—'}{' '}
                          <span className="text-xs font-normal text-[#64748B]">USD</span>
                        </div>
                        {liveTick?.change24h !== undefined && (
                          <span
                            className={`font-mono-tabular text-xs font-semibold px-1.5 py-0.5 rounded ${
                              liveTick.change24h >= 0
                                ? 'bg-[#10B981]/15 text-[#10B981]'
                                : 'bg-[#F43F5E]/15 text-[#F43F5E]'
                            }`}
                          >
                            {liveTick.change24h >= 0 ? '+' : ''}
                            {liveTick.change24h.toFixed(2)}%
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-[#64748B] font-mono-tabular flex items-center justify-between">
                        <span>
                          ATR(14) : {ind.atr ? ind.atr.toFixed(2) : '—'} • {(analysis?.asset_class || 'crypto').toUpperCase()}
                        </span>
                        {liveTick?.bid && liveTick?.ask && (
                          <span className="text-[10px] text-[#94A3B8]">
                            B:{liveTick.bid.toFixed(1)} / A:{liveTick.ask.toFixed(1)}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })()}

                {/* KPI 2: Signal & Teddy Score */}
                <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-5 space-y-2">
                  <div className="flex items-center justify-between text-xs text-[#94A3B8]">
                    <span>{tr(lang, 'Signal & Teddy Score')}</span>
                    <span className="font-mono-tabular text-[#94A3B8]">
                      {lang === 'en' ? 'Confidence:' : 'Confiance :'} {analysis?.confidence || '—'}
                    </span>
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
                    <span>{tr(lang, 'Alignement Multi-Timeframes')}</span>
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
                              val === 'HAUSSIER' || val === 'BULLISH'
                                ? 'text-[#10B981]'
                                : val === 'BAISSIER' || val === 'BEARISH'
                                ? 'text-[#F43F5E]'
                                : 'text-[#94A3B8]'
                            }`}
                          >
                            {tr(lang, val)}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* KPI 4: Risk Sizing Recommendation */}
                <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-5 space-y-2">
                  <div className="flex items-center justify-between text-xs text-[#94A3B8]">
                    <span>{tr(lang, 'Taille Position Recommandée')}</span>
                    <span className="font-mono-tabular text-[#10B981]">
                      {lang === 'en' ? 'Risk' : 'Risque'} {analysis?.sizing_recommendation?.risk_pct || 1}%
                    </span>
                  </div>
                  <div className="font-mono-tabular text-2xl font-bold text-[#F1F5F9]">
                    {analysis?.sizing_recommendation?.position_size ?? 0}{' '}
                    <span className="text-xs font-normal text-[#64748B]">{tr(lang, 'unités')}</span>
                  </div>
                  <div className="text-xs text-[#64748B] font-mono-tabular">
                    {lang === 'en' ? 'Max risk:' : 'Risque max :'} {analysis?.sizing_recommendation?.risk_amount_usd ?? 100}{' '}
                    USDT • {lang === 'en' ? 'Margin:' : 'Marge :'}{' '}
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
                    livePrice={livePrices[analysis?.symbol || selectedSymbol]?.price || analysis?.current_price}
                    sl={analysis?.sl}
                    tp1={analysis?.tp1}
                    tp2={analysis?.tp2}
                    support={ind.support}
                    resistance={ind.resistance}
                    lang={lang}
                  />

                  {/* Technical Indicators Breakdown Strip */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                    <div className="bg-[#111827] border border-white/[0.07] rounded-lg p-3.5">
                      <div className="text-xs text-[#64748B]">{tr(lang, 'RSI (14) & Stochastique')}</div>
                      <div className="font-mono-tabular text-base font-semibold text-[#F1F5F9] mt-1">
                        {ind.rsi ? ind.rsi.toFixed(2) : '—'}
                      </div>
                      <div className="text-[11px] text-[#94A3B8] mt-0.5">
                        {ind.rsi > 70
                          ? tr(lang, 'Zone de surachat (>70)')
                          : ind.rsi < 30
                          ? tr(lang, 'Zone de survente (<30)')
                          : tr(lang, 'Zone neutre équilibrée')}
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
                      <div className="text-xs text-[#64748B]">{tr(lang, 'ADX (14) • Force Tendance')}</div>
                      <div className="font-mono-tabular text-base font-semibold text-[#F1F5F9] mt-1">
                        {ind.adx ? ind.adx.toFixed(2) : '—'}{' '}
                        <span className="text-xs text-[#10B981]">
                          {ind.adx_rising ? tr(lang, '↑ En hausse') : tr(lang, '↓ En repli')}
                        </span>
                      </div>
                      <div className="text-[11px] text-[#94A3B8] mt-0.5 font-mono-tabular">
                        +DI: {ind.plus_di ? ind.plus_di.toFixed(1) : '—'} / -DI: {ind.minus_di ? ind.minus_di.toFixed(1) : '—'}
                      </div>
                    </div>

                    <div className="bg-[#111827] border border-white/[0.07] rounded-lg p-3.5">
                      <div className="text-xs text-[#64748B]">{tr(lang, 'Support / Résistance (50p)')}</div>
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
                        {tr(lang, 'Diagnostic du Moteur Teddy')}
                      </h3>
                      <span className="font-mono-tabular text-xs text-[#94A3B8]">
                        {lang === 'en' ? 'Status:' : 'Statut :'} {analysis?.validation_status || '—'}
                      </span>
                    </div>

                    <div className="p-3.5 rounded-lg bg-[#090D16] border border-white/[0.06] text-xs text-[#F1F5F9] leading-relaxed">
                      {analysis?.reason || tr(lang, 'Analyse en cours...')}
                    </div>

                    {/* Levels SL / TP1 / TP2 / RR */}
                    <div className="grid grid-cols-2 gap-2.5 text-xs font-mono-tabular">
                      <div className="p-2.5 rounded bg-[#090D16] border border-white/[0.05]">
                        <div className="text-[#64748B] text-[10px]">STOP LOSS (ATR)</div>
                        <div className="text-[#F43F5E] font-semibold mt-0.5">
                          {analysis?.sl ? analysis.sl.toLocaleString('en-US', { maximumFractionDigits: 2 }) : tr(lang, 'Non actif (WAIT)')}
                        </div>
                      </div>
                      <div className="p-2.5 rounded bg-[#090D16] border border-white/[0.05]">
                        <div className="text-[#64748B] text-[10px]">TAKE PROFIT 1</div>
                        <div className="text-[#10B981] font-semibold mt-0.5">
                          {analysis?.tp1 ? analysis.tp1.toLocaleString('en-US', { maximumFractionDigits: 2 }) : tr(lang, 'Non actif (WAIT)')}
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
                        {tr(lang, 'Exécution Rapide Paper Trading')}
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
                          <label className="block text-[11px] text-[#94A3B8] mb-1">
                            {lang === 'en' ? 'Quantity' : 'Quantité'} ({selectedSymbol})
                          </label>
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
                          <label className="block text-[11px] text-[#94A3B8] mb-1">{tr(lang, 'Levier (1x–20x)')}</label>
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
                        {lang === 'en' ? `Open Paper Position (${selectedSymbol})` : `Ouvrir Position Paper (${selectedSymbol})`}
                      </button>
                    </form>
                  </div>
                </div>
              </div>

              {/* Multi-Symbol Scanner Section */}
              <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-4 sm:p-5 space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2.5">
                      <h3 className="font-display font-semibold text-base text-[#F1F5F9]">
                        {tr(lang, 'Scanner Multi-Marchés (BTCUSDT • ETHUSDT • XAUUSD)')}
                      </h3>
                      {lastScannedAt && (
                        <span className="text-[11px] font-mono-tabular text-[#10B981] bg-[#10B981]/10 border border-[#10B981]/30 px-2 py-0.5 rounded">
                          {lang === 'en' ? 'Updated at' : 'Mis à jour à'} {new Date(lastScannedAt).toLocaleTimeString()}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-[#64748B] mt-0.5">
                      {lang === 'en'
                        ? `Simultaneous real-time analysis on closed candles (${selectedTimeframe.toUpperCase()} • Style ${selectedStyle}). Click a card to load its detailed chart.`
                        : `Analyse simultanée en temps réel sur bougies clôturées (${selectedTimeframe.toUpperCase()} • Style ${selectedStyle}). Cliquez sur une carte pour charger son graphique détaillé.`}
                    </p>
                  </div>
                  <button
                    onClick={() => runMultiScan(selectedTimeframe, selectedStyle, true)}
                    disabled={loadingScan}
                    className="w-full sm:w-auto justify-center px-4 py-2 bg-[#10B981] hover:bg-[#059669] text-[#090D16] rounded-lg text-xs font-semibold flex items-center gap-2 transition-colors shadow-lg shadow-[#10B981]/15"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${loadingScan ? 'animate-spin' : ''}`} />
                    <span>
                      {loadingScan
                        ? tr(lang, 'Scan en cours...')
                        : lang === 'en'
                        ? `Run Global Scan (${selectedTimeframe.toUpperCase()})`
                        : `Lancer le Scan Global (${selectedTimeframe.toUpperCase()})`}
                    </span>
                  </button>
                </div>

                {loadingScan && multiScans.length === 0 ? (
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
                    {[1, 2, 3].map((n) => (
                      <div key={n} className="p-4 rounded-lg bg-[#090D16] border border-white/[0.07] animate-pulse space-y-3">
                        <div className="h-4 bg-white/10 rounded w-1/2" />
                        <div className="h-6 bg-white/10 rounded w-2/3" />
                        <div className="h-3 bg-white/10 rounded w-full" />
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
                    {multiScans.map((sc) => {
                      const scInd = sc.indicators || {};
                      const scTrends = scInd.timeframe_trends || {};
                      const scTick = livePrices[sc.symbol];
                      const scFlash = priceFlash[sc.symbol];
                      const scLivePrice = scTick?.price || sc.current_price || 0;
                      return (
                        <div
                          key={sc.symbol}
                          onClick={() => {
                            setSelectedSymbol(sc.symbol);
                            setAnalysis(sc);
                            runAnalysis(sc.symbol, selectedTimeframe, selectedStyle);
                          }}
                          className={`p-4 rounded-lg bg-[#090D16] border cursor-pointer transition-all space-y-2.5 ${
                            selectedSymbol === sc.symbol
                              ? 'border-[#10B981]/60 ring-1 ring-[#10B981]/30'
                              : 'border-white/[0.07] hover:border-[#10B981]/40'
                          }`}
                        >
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              <span className="font-mono-tabular font-bold text-sm text-[#F1F5F9]">{sc.symbol}</span>
                              <span className="text-[10px] font-mono-tabular px-1.5 py-0.5 rounded bg-white/[0.05] text-[#94A3B8]">
                                {sc.timeframe.toUpperCase()}
                              </span>
                            </div>
                            <span
                              className={`font-mono-tabular text-xs font-bold px-2 py-0.5 rounded ${
                                sc.signal === 'BUY'
                                  ? 'bg-[#10B981]/15 text-[#10B981] border border-[#10B981]/30'
                                  : sc.signal === 'SELL'
                                  ? 'bg-[#F43F5E]/15 text-[#F43F5E] border border-[#F43F5E]/30'
                                  : 'bg-[#F59E0B]/15 text-[#F59E0B] border border-[#F59E0B]/30'
                              }`}
                            >
                              {sc.signal} • {sc.teddy_score}/100
                            </span>
                          </div>

                          <div className="flex items-baseline justify-between">
                            <div
                              className={`font-mono-tabular text-lg font-bold transition-colors ${
                                scFlash === 'up'
                                  ? 'text-[#10B981]'
                                  : scFlash === 'down'
                                  ? 'text-[#F43F5E]'
                                  : scTick?.direction === 'up'
                                  ? 'text-[#34D399]'
                                  : scTick?.direction === 'down'
                                  ? 'text-[#FB7185]'
                                  : 'text-[#F1F5F9]'
                              }`}
                            >
                              {Number(scLivePrice).toLocaleString('en-US', {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2,
                              })}{' '}
                              <span className="text-xs font-normal text-[#64748B]">USD</span>
                            </div>
                            <div className="text-[11px] font-mono-tabular text-[#64748B]">
                              RSI: {scInd.rsi ? Number(scInd.rsi).toFixed(1) : '—'} • ADX:{' '}
                              {scInd.adx ? Number(scInd.adx).toFixed(1) : '—'}
                            </div>
                          </div>

                          <div className="grid grid-cols-3 gap-1.5 text-[10px] font-mono-tabular">
                            {(['1h', '4h', '1d'] as const).map((tfKey) => {
                              const trVal = scTrends[tfKey] || 'NEUTRE';
                              return (
                                <div key={tfKey} className="bg-[#111827] px-2 py-1 rounded text-center">
                                  <span className="text-[#64748B] uppercase mr-1">{tfKey}:</span>
                                  <span
                                    className={
                                      trVal === 'HAUSSIER' || trVal === 'BULLISH'
                                        ? 'text-[#10B981] font-semibold'
                                        : trVal === 'BAISSIER' || trVal === 'BEARISH'
                                        ? 'text-[#F43F5E] font-semibold'
                                        : 'text-[#94A3B8]'
                                    }
                                  >
                                    {tr(lang, trVal)}
                                  </span>
                                </div>
                              );
                            })}
                          </div>

                          {(sc.sl || sc.tp1) && (
                            <div className="flex items-center justify-between text-[11px] font-mono-tabular pt-1 border-t border-white/[0.05]">
                              <span className="text-[#F43F5E]">SL: {sc.sl ? Number(sc.sl).toLocaleString() : '—'}</span>
                              <span className="text-[#10B981]">TP1: {sc.tp1 ? Number(sc.tp1).toLocaleString() : '—'}</span>
                              <span className="text-[#F59E0B]">R:R {sc.rr_ratio ? `1:${Number(sc.rr_ratio).toFixed(2)}` : '—'}</span>
                            </div>
                          )}

                          <div className="text-xs text-[#94A3B8] line-clamp-2">{sc.reason}</div>
                        </div>
                      );
                    })}
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
                    {tr(lang, 'Portefeuille Paper Trading Réaliste')}
                  </h2>
                  <p className="text-xs text-[#94A3B8]">
                    {tr(
                      lang,
                      "Simulation fidèle avec frais d'ouverture/clôture (0.04%), slippage (0.02%) et surveillance automatique des seuils SL/TP."
                    )}
                  </p>
                </div>
                <button
                  onClick={handleResetPaperAccount}
                  className="px-3.5 py-2 bg-[#1E293B] hover:bg-[#334155] border border-white/10 rounded-lg text-xs text-[#F1F5F9] transition-colors"
                >
                  {tr(lang, 'Réinitialiser le capital (10 000 USDT)')}
                </button>
              </div>

              {paperStats && (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
                  <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-5">
                    <div className="text-xs text-[#94A3B8]">{tr(lang, 'Capital Disponible')}</div>
                    <div className="font-mono-tabular text-2xl font-bold text-[#F1F5F9] mt-1">
                      {Number(paperStats.capital ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USDT
                    </div>
                  </div>
                  <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-5">
                    <div className="text-xs text-[#94A3B8]">{tr(lang, 'Équité Totale (Marge + Latent)')}</div>
                    <div className="font-mono-tabular text-2xl font-bold text-[#10B981] mt-1">
                      {Number(paperStats.equity ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USDT
                    </div>
                  </div>
                  <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-5">
                    <div className="text-xs text-[#94A3B8]">{tr(lang, 'PnL Réalisé Cumulé')}</div>
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
                    <div className="text-xs text-[#94A3B8]">{tr(lang, 'Taux de Réussite (Win Rate)')}</div>
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
                    {lang === 'en' ? 'Open Positions' : 'Positions Ouvertes'} ({openPaper.length})
                  </h3>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="border-b border-white/[0.07] text-[#64748B] font-mono-tabular uppercase">
                        <th className="py-3 px-4">{tr(lang, 'Actif')}</th>
                        <th className="py-3 px-4">{tr(lang, 'Sens & Levier')}</th>
                        <th className="py-3 px-4 text-right">{tr(lang, 'Entrée')}</th>
                        <th className="py-3 px-4 text-right">{tr(lang, 'Cours Actuel')}</th>
                        <th className="py-3 px-4 text-right">SL / TP</th>
                        <th className="py-3 px-4 text-right">{tr(lang, 'Marge')}</th>
                        <th className="py-3 px-4 text-right">{tr(lang, 'PnL Latent')}</th>
                        <th className="py-3 px-4 text-right">{tr(lang, 'Action')}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/[0.05] font-mono-tabular">
                      {openPaper.length === 0 ? (
                        <tr>
                          <td colSpan={8} className="py-8 text-center text-[#64748B] font-sans">
                            {tr(
                              lang,
                              "Aucune position Paper ouverte. Utilisez le ticket d'ordre depuis l'onglet Market Intelligence."
                            )}
                          </td>
                        </tr>
                      ) : (
                        openPaper.map((pos) => {
                          const entryVal = Number(pos.entry ?? pos.entry_price ?? 0);
                          const liveSymPrice = livePrices[pos.symbol]?.price;
                          const currVal = Number(liveSymPrice ?? pos.current_price ?? entryVal);
                          const slVal = Number(pos.sl ?? 0);
                          const tpVal = Number(pos.tp ?? 0);
                          const qtyVal = Number(pos.qty ?? 0);
                          const levVal = Math.max(1, Number(pos.leverage ?? 1));
                          const marginVal = Number(pos.margin_used ?? (entryVal * qtyVal) / levVal);
                          const rawDiff = pos.side === 'BUY' ? currVal - entryVal : entryVal - currVal;
                          const computedUpnl =
                            liveSymPrice && entryVal > 0 && qtyVal > 0
                              ? rawDiff * qtyVal
                              : Number(pos.unrealized_pnl ?? pos.pnl_usdt ?? 0);
                          const computedUpnlPct =
                            marginVal > 0
                              ? (computedUpnl / marginVal) * 100
                              : Number(pos.unrealized_pnl_pct ?? pos.pnl_pct ?? 0);
                          return (
                            <tr key={pos.id} className="hover:bg-white/[0.02]">
                              <td className="py-3.5 px-4 font-semibold text-[#F1F5F9]">{pos.symbol}</td>
                              <td className="py-3.5 px-4">
                                <span className={pos.side === 'BUY' ? 'text-[#10B981]' : 'text-[#F43F5E]'}>
                                  {pos.side} {pos.leverage}x
                                </span>
                              </td>
                              <td className="py-3.5 px-4 text-right">{entryVal.toLocaleString()}</td>
                              <td className="py-3.5 px-4 text-right font-semibold text-[#F1F5F9]">
                                {currVal.toLocaleString('en-US', {
                                  minimumFractionDigits: 2,
                                  maximumFractionDigits: 2,
                                })}
                              </td>
                              <td className="py-3.5 px-4 text-right">
                                <span className="text-[#F43F5E]">{slVal ? slVal.toLocaleString() : '—'}</span> /{' '}
                                <span className="text-[#10B981]">{tpVal ? tpVal.toLocaleString() : '—'}</span>
                              </td>
                              <td className="py-3.5 px-4 text-right">{marginVal.toFixed(2)} USDT</td>
                              <td
                                className={`py-3.5 px-4 text-right font-semibold ${
                                  computedUpnl >= 0 ? 'text-[#10B981]' : 'text-[#F43F5E]'
                                }`}
                              >
                                {computedUpnl >= 0 ? '+' : ''}
                                {computedUpnl.toFixed(2)} USDT ({computedUpnlPct.toFixed(2)}%)
                              </td>
                              <td className="py-3.5 px-4 text-right">
                                <button
                                  onClick={() => handleClosePaperPosition(pos.id)}
                                  className="px-2.5 py-1 bg-[#F43F5E]/15 hover:bg-[#F43F5E]/25 border border-[#F43F5E]/40 text-[#FB7185] rounded text-[11px]"
                                >
                                  {tr(lang, 'Clôturer')}
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
                    {lang === 'en' ? 'Closed Positions History' : 'Historique des Positions Clôturées'} ({closedPaper.length})
                  </h3>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="border-b border-white/[0.07] text-[#64748B] font-mono-tabular uppercase">
                        <th className="py-3 px-4">{tr(lang, 'Actif')}</th>
                        <th className="py-3 px-4">{tr(lang, 'Sens')}</th>
                        <th className="py-3 px-4 text-right">{tr(lang, 'Entrée')}</th>
                        <th className="py-3 px-4 text-right">{tr(lang, 'Sortie')}</th>
                        <th className="py-3 px-4">{tr(lang, 'Raison')}</th>
                        <th className="py-3 px-4 text-right">{tr(lang, 'PnL Réalisé')}</th>
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
                            <td className="py-3.5 px-4 text-right">{entryVal.toLocaleString()}</td>
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
                  {tr(lang, 'Créer une Alerte de Prix')}
                </h3>
                <p className="text-xs text-[#94A3B8]">
                  {lang === 'en'
                    ? `Current quota: ${alerts.length} / ${alertLimit} active alerts (${user?.role.toUpperCase()}).`
                    : `Quota actuel : ${alerts.length} / ${alertLimit} alertes actives (${user?.role.toUpperCase()}).`}
                </p>
                <form onSubmit={handleAddAlert} className="space-y-3.5 text-xs">
                  <div>
                    <label className="block text-[#94A3B8] mb-1">{tr(lang, 'Symbole')}</label>
                    <select
                      value={newAlertSymbol}
                      onChange={(e) => setNewAlertSymbol(e.target.value)}
                      className="w-full px-3 py-2 bg-[#090D16] border border-white/10 rounded-lg font-mono-tabular text-[#F1F5F9]"
                    >
                      {SYMBOLS.map((s) => (
                        <option key={s.id} value={s.id}>
                          {lang === 'en' && s.labelEn ? s.labelEn : s.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-[#94A3B8] mb-1">{tr(lang, 'Condition de franchissement')}</label>
                    <select
                      value={newAlertCond}
                      onChange={(e) => setNewAlertCond(e.target.value as 'above' | 'below')}
                      className="w-full px-3 py-2 bg-[#090D16] border border-white/10 rounded-lg text-[#F1F5F9]"
                    >
                      <option value="above">
                        {lang === 'en' ? 'Crosses Above (ABOVE ≥)' : 'Franchissement à la hausse (ABOVE ≥)'}
                      </option>
                      <option value="below">
                        {lang === 'en' ? 'Crosses Below (BELOW ≤)' : 'Franchissement à la baisse (BELOW ≤)'}
                      </option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-[#94A3B8] mb-1">{tr(lang, 'Prix Cible (USD / USDT)')}</label>
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
                    {tr(lang, "Activer l'Alerte Prix")}
                  </button>
                </form>
              </div>

              <div className="lg:col-span-7 bg-[#111827] border border-white/[0.07] rounded-xl p-5 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="font-display font-semibold text-base text-[#F1F5F9]">
                    {lang === 'en' ? 'Active Alerts' : 'Alertes Actives'} ({alerts.length})
                  </h3>
                  {alerts.length > 0 && (
                    <button
                      onClick={() =>
                        apiFetch('/api/alerts/clear', { method: 'POST' }).then((r) => {
                          setAlerts(r.alerts || []);
                          showToast(tr(lang, 'Toutes les alertes ont été supprimées.'), 'info');
                        })
                      }
                      className="text-xs text-[#F43F5E] hover:underline"
                    >
                      {tr(lang, 'Tout effacer')}
                    </button>
                  )}
                </div>

                <div className="divide-y divide-white/[0.06]">
                  {alerts.length === 0 ? (
                    <div className="py-10 text-center text-xs text-[#64748B]">
                      {tr(lang, 'Aucune alerte active pour le moment.')}
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
                            {a.condition === 'above' ? tr(lang, '≥ HAUSSE') : tr(lang, '≤ BAISSE')}
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
                        <span className="text-[#FB7185]">{tr(lang, 'SAFETY LOCK ACTIF (Auto-Trade Suspendu)')}</span>
                      </>
                    ) : tradingCfg.safety_warn ? (
                      <>
                        <AlertTriangle className="w-5 h-5 text-[#F59E0B]" />
                        <span className="text-[#FBBF24]">{tr(lang, 'SAFETY WARN (Avertissement Temporaire Actif)')}</span>
                      </>
                    ) : (
                      <>
                        <ShieldCheck className="w-5 h-5 text-[#10B981]" />
                        <span className="text-[#34D399]">{tr(lang, 'SAFETY CENTER OPÉRATIONNEL')}</span>
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
                        ? lang === 'en'
                          ? `BINANCE API CONNECTED (${tradingCfg.market_type.toUpperCase()} • ${
                              tradingCfg.testnet ? 'TESTNET' : 'LIVE REAL'
                            })`
                          : `API BINANCE CONNECTÉE (${tradingCfg.market_type.toUpperCase()} • ${
                              tradingCfg.testnet ? 'TESTNET' : 'LIVE RÉEL'
                            })`
                        : tr(lang, 'API BINANCE DÉCONNECTÉE / CLÉS REQUISES')}
                    </span>
                  </div>

                  <div className="text-xs text-[#94A3B8]">
                    {tradingCfg.safety_lock_reason ||
                      tradingCfg.safety_warn_reason ||
                      tradingCfg.api_status_message ||
                      tr(
                        lang,
                        'Tous les garde-fous de risque (exposition max 20%, fraîcheur de signal 180s, TTL 3600s) sont actifs.'
                      )}
                  </div>
                  {(tradingCfg.safety_lock_at || tradingCfg.safety_warn_at) && (
                    <div className="text-[11px] font-mono-tabular text-[#64748B]">
                      {tradingCfg.safety_lock_at && (
                        <span>
                          {lang === 'en'
                            ? `Lock activated ${Math.round(tradingCfg.safety_lock_age_seconds || 0)}s ago (TTL: ${tradingCfg.safety_lock_ttl_seconds}s) `
                            : `Lock activé il y a ${Math.round(tradingCfg.safety_lock_age_seconds || 0)}s (TTL: ${tradingCfg.safety_lock_ttl_seconds}s) `}
                        </span>
                      )}
                      {tradingCfg.safety_warn_at && (
                        <span>
                          • {lang === 'en' ? 'Warn timestamp:' : 'Warn horodaté :'}{' '}
                          {new Date(tradingCfg.safety_warn_at * 1000).toLocaleTimeString()}
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
                      placeholder={tr(lang, 'PIN (6 chiffres)')}
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
                      {tr(lang, 'Acquitter / Déverrouiller (/clearsafe)')}
                    </button>
                  )}
                  {!tradingCfg.safety_lock && (
                    <button
                      onClick={() =>
                        handleSafetyAction(
                          'engage_lock',
                          lang === 'en'
                            ? 'Manual emergency lock by operator'
                            : 'Verrouillage d’urgence manuel par l’opérateur'
                        )
                      }
                      className="px-3.5 py-2 bg-[#F43F5E]/20 hover:bg-[#F43F5E]/30 border border-[#F43F5E]/40 text-[#FB7185] font-semibold rounded-lg transition-colors"
                    >
                      {tr(lang, 'Verrouiller Safe Mode')}
                    </button>
                  )}
                  <button
                    onClick={() => handleSafetyAction('emergency_stop')}
                    className="px-3.5 py-2 bg-[#F43F5E] hover:bg-[#E11D48] text-white font-semibold rounded-lg transition-colors"
                    title={
                      lang === 'en'
                        ? 'Close all open positions and disable AutoTrade (/emergency)'
                        : 'Ferme toutes les positions ouvertes et désactive AutoTrade (/emergency)'
                    }
                  >
                    🛑 Emergency Stop All (/emergency)
                  </button>
                  <button
                    onClick={() =>
                      apiFetch('/api/trading/reconcile', { method: 'POST' }).then(() => {
                        loadLiveAccountAndOrders();
                        showToast(tr(lang, 'Réconciliation DB ↔ Binance exécutée.'), 'success');
                      })
                    }
                    className="px-3.5 py-2 bg-[#111827] hover:bg-[#1E293B] border border-white/15 text-[#F1F5F9] rounded-lg transition-colors"
                  >
                    {tr(lang, 'Réconcilier DB ↔ Binance')}
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
                        {tr(lang, 'Configuration Complète Auto-Trade & Stratégie (Miroir Bot Telegram)')}
                      </h3>
                      <p className="text-xs text-[#64748B]">
                        {tr(
                          lang,
                          'Synchronisé en temps réel avec `/config`, `/autotrade` et `/periodic_analysis`. Toute modification critique suspend Auto-Trade par sécurité.'
                        )}
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
                        {tradingCfg.testnet
                          ? 'MODE: TESTNET'
                          : lang === 'en'
                          ? 'MODE: LIVE REAL'
                          : 'MODE: LIVE RÉEL'}
                      </button>
                    </div>
                  </div>

                  {/* Section 1: Market, Style & Periodic Analysis (/setmarket, /settradingstyle, /setanalysistf, /setanalysisinterval) */}
                  <div className="space-y-3">
                    <div className="text-xs font-mono-tabular uppercase tracking-wider text-[#10B981]">
                      {tr(lang, '1. Marché, Style & Analyse Périodique')}
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
                      <div>
                        <label className="block text-[#94A3B8] mb-1">{tr(lang, 'Marché (/setmarket)')}</label>
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
                        <label className="block text-[#94A3B8] mb-1">{tr(lang, 'Style (/settradingstyle)')}</label>
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
                        <label className="block text-[#94A3B8] mb-1">{tr(lang, 'Intervalle Scan (/setanalysisinterval)')}</label>
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
                          {lang === 'en'
                            ? `Automatic Periodic Analysis (/periodic_analysis) — every ${tradingCfg.analysis_interval_minutes} min on ${tradingCfg.analysis_timeframe.toUpperCase()}`
                            : `Analyse Périodique Automatique (/periodic_analysis) — toutes les ${tradingCfg.analysis_interval_minutes} min en ${tradingCfg.analysis_timeframe.toUpperCase()}`}
                        </span>
                      </label>
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedTimeframe(tradingCfg.analysis_timeframe);
                          setSelectedStyle(tradingCfg.trading_style);
                          runMultiScan(tradingCfg.analysis_timeframe, tradingCfg.trading_style, true);
                          setActiveTab('intelligence');
                        }}
                        className="px-3 py-1.5 bg-[#10B981]/15 hover:bg-[#10B981]/25 border border-[#10B981]/40 text-[#10B981] rounded-md font-semibold flex items-center gap-1.5"
                      >
                        <Play className="w-3.5 h-3.5" />
                        <span>{tr(lang, 'Scanner Maintenant (/periodic_analysis now)')}</span>
                      </button>
                    </div>
                  </div>

                  {/* Section 2: Leverage, Risk, Max Positions, Min Score, Daily Max Loss, Cooldown */}
                  <div className="space-y-3 pt-2 border-t border-white/[0.06]">
                    <div className="text-xs font-mono-tabular uppercase tracking-wider text-[#10B981]">
                      {tr(lang, "2. Paramètres de Risque, Levier & Filtres d'Exécution")}
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 text-xs">
                      {/* Leverage */}
                      <div className="p-3 rounded-lg bg-[#090D16] border border-white/[0.06] space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-[#94A3B8]">{tr(lang, 'Levier (/setleverage 1–125)')}</span>
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
                          <span className="text-[#94A3B8]">{tr(lang, 'Risque / Trade (/setrisk)')}</span>
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
                          <span className="text-[#94A3B8]">{tr(lang, 'Score Min (/setminscore)')}</span>
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
                          <span className="text-[#94A3B8]">{tr(lang, 'Perte Max/Jour (/setdailymaxloss)')}</span>
                          <span className="font-mono-tabular font-bold text-[#F43F5E]">
                            {tradingCfg.max_daily_loss}%
                          </span>
                        </div>
                        <div className="text-[11px] font-mono-tabular text-[#64748B]">
                          {lang === 'en' ? 'Daily total:' : 'Cumul jour :'} {(tradingCfg.daily_loss_tracked || 0).toFixed(2)} USDT
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
                      {tr(lang, '3. Trailing Stop Dynamique (ATR) & DCA (/settrailing • /setdca)')}
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
                          <span className="text-[#94A3B8] text-[11px]">{tr(lang, 'Facteur / Distance (0.1–20%) :')}</span>
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
                            <span>{tr(lang, 'Configuration DCA (/setdca)')}</span>
                          </label>
                          <span className="font-mono-tabular text-[#F59E0B]">
                            {tradingCfg.dca_enabled ? 'ON' : 'OFF'} ({tradingCfg.dca_steps ?? 3}{' '}
                            {lang === 'en' ? 'st.' : 'ét.'}, {tradingCfg.dca_step_pct ?? 2.0}%)
                          </span>
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                          <div>
                            <label className="block text-[11px] text-[#94A3B8] mb-1">{tr(lang, 'Étapes (1–10)')}</label>
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
                            <label className="block text-[11px] text-[#94A3B8] mb-1">{tr(lang, 'Écart % (0.1–20%)')}</label>
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
                      {tr(lang, '4. Filtrage des Symboles Documentés (/whitelist • /blacklist)')}
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
                              {tr(lang, 'Vider (clear)')}
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
                            ? tr(lang, 'Aucune restriction (tous les symboles documentés sont autorisés).')
                            : `${lang === 'en' ? 'Allowed assets:' : 'Actifs autorisés :'} ${(tradingCfg.symbol_whitelist || []).join(', ')}`}
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
                              {tr(lang, 'Vider (clear)')}
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
                            ? tr(lang, 'Aucun actif bloqué.')
                            : `${lang === 'en' ? 'Excluded assets:' : 'Actifs exclus :'} ${(tradingCfg.symbol_blacklist || []).join(', ')}`}
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
                          {tr(lang, 'Clés API Binance (/setapikeys)')}
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
                          ? `● ${lang === 'en' ? 'OPERATIONAL' : 'OPÉRATIONNEL'} (${tradingCfg.api_key_masked || 'Testnet'})`
                          : tr(lang, '○ NON CONNECTÉ')}
                      </span>
                    </div>

                    <div className="flex items-center justify-between p-3 rounded-lg bg-[#090D16] border border-white/[0.06] text-xs">
                      <div>
                        <div className="text-[#94A3B8]">{tr(lang, 'Clé active :')}</div>
                        <div className="font-mono-tabular font-semibold text-[#F1F5F9]">
                          {tradingCfg.api_key_masked || tr(lang, 'Aucune clé chargée')} •{' '}
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
                        <span>{tr(lang, 'Tester Connexion')}</span>
                      </button>
                    </div>

                    <form onSubmit={handleSaveBinanceKeys} className="space-y-3 text-xs">
                      <div>
                        <label className="block text-[#94A3B8] mb-1">Binance API Key</label>
                        <input
                          type="text"
                          value={binanceKey}
                          onChange={(e) => setBinanceKey(e.target.value)}
                          placeholder={tr(lang, 'Entrez votre clé API Binance...')}
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
                        <span>{tr(lang, 'Environnement Binance Testnet (/settestnet on|off)')}</span>
                      </label>
                      <button
                        type="submit"
                        className="w-full py-2.5 bg-[#10B981] hover:bg-[#059669] text-[#090D16] font-semibold rounded-lg transition-colors"
                      >
                        {tr(lang, 'Enregistrer & Vérifier les Clés API')}
                      </button>
                    </form>
                  </div>

                  {/* Real-Time Binance Account Balance & Margin Card (/account, /balance) */}
                  <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-5 space-y-4">
                    <div className="flex items-center justify-between border-b border-white/[0.07] pb-3">
                      <div className="flex items-center gap-2">
                        <Wallet className="w-4 h-4 text-[#10B981]" />
                        <h3 className="font-display font-semibold text-base text-[#F1F5F9]">
                          {tr(lang, 'Solde & Marge Compte Binance (/account)')}
                        </h3>
                      </div>
                      <button
                        type="button"
                        onClick={loadLiveAccountAndOrders}
                        disabled={loadingLiveAccount}
                        className="text-xs text-[#10B981] hover:underline flex items-center gap-1"
                      >
                        <RefreshCw className={`w-3.5 h-3.5 ${loadingLiveAccount ? 'animate-spin' : ''}`} />
                        <span>{tr(lang, 'Rafraîchir')}</span>
                      </button>
                    </div>

                    {liveAccount ? (
                      <div className="space-y-3 text-xs">
                        <div className="grid grid-cols-2 gap-3 font-mono-tabular">
                          <div className="p-3 rounded-lg bg-[#090D16] border border-white/[0.06]">
                            <div className="text-[10px] text-[#64748B] uppercase">{tr(lang, 'Solde Total Wallet')}</div>
                            <div className="text-base font-bold text-[#F1F5F9] mt-0.5">
                              {Number(liveAccount.total_wallet_balance || 0).toLocaleString('en-US', {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2,
                              })}{' '}
                              USDT
                            </div>
                          </div>
                          <div className="p-3 rounded-lg bg-[#090D16] border border-white/[0.06]">
                            <div className="text-[10px] text-[#64748B] uppercase">{tr(lang, 'Disponible')}</div>
                            <div className="text-base font-bold text-[#10B981] mt-0.5">
                              {Number(liveAccount.available_balance || 0).toLocaleString('en-US', {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2,
                              })}{' '}
                              USDT
                            </div>
                          </div>
                          <div className="p-3 rounded-lg bg-[#090D16] border border-white/[0.06]">
                            <div className="text-[10px] text-[#64748B] uppercase">{tr(lang, 'PnL Non Réalisé')}</div>
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
                            <div className="text-[10px] text-[#64748B] uppercase">{tr(lang, 'Marge Utilisée')}</div>
                            <div className="text-base font-bold text-[#F59E0B] mt-0.5">
                              {liveAccount.market_type === 'futures' ? `${liveAccount.margin_used_pct || 0}%` : 'SPOT'}
                            </div>
                          </div>
                        </div>

                        {Array.isArray(liveAccount.assets) && liveAccount.assets.length > 0 && (
                          <div className="space-y-1.5 pt-1">
                            <div className="text-[11px] text-[#94A3B8] font-semibold">{tr(lang, 'Actifs détectés :')}</div>
                            <div className="max-h-32 overflow-y-auto divide-y divide-white/[0.05] font-mono-tabular">
                              {liveAccount.assets.slice(0, 6).map((a: any) => (
                                <div key={a.asset} className="py-1.5 flex items-center justify-between text-[11px]">
                                  <span className="font-bold text-[#F1F5F9]">{a.asset}</span>
                                  <span className="text-[#94A3B8]">
                                    {liveAccount.market_type === 'futures'
                                      ? `${Number(a.wallet || 0).toFixed(4)} (${lang === 'en' ? 'Avail' : 'Dispo'}: ${Number(a.available || 0).toFixed(2)})`
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
                        {tr(
                          lang,
                          'Connectez des clés API Binance valides pour afficher le solde temps réel, la marge disponible et les positions sur le serveur Binance.'
                        )}
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
                        {tr(lang, "Ticket d'Ordre Live Manuel (/live_long • /live_short)")}
                      </h3>
                      <p className="text-xs text-[#64748B]">
                        {lang === 'en'
                          ? `Pre-order validation + explicit confirmation before sending to Binance (${tradingCfg.market_type.toUpperCase()}).`
                          : `Validation de pré-ordre + confirmation explicite avant envoi sur Binance (${tradingCfg.market_type.toUpperCase()}).`}
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
                        {tr(lang, '🟢 OUVRIR LONG (BUY)')}
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
                        {tr(lang, '🔴 OUVRIR SHORT (SELL)')}
                      </button>
                    </div>

                    <div className="grid grid-cols-2 gap-2.5">
                      <div>
                        <label className="block text-[11px] text-[#94A3B8] mb-1">{tr(lang, 'Symbole')}</label>
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
                        <label className="block text-[11px] text-[#94A3B8] mb-1">{tr(lang, "Type d'Ordre")}</label>
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
                        <label className="block text-[11px] text-[#94A3B8] mb-1">{tr(lang, 'Montant')}</label>
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
                        <label className="block text-[11px] text-[#94A3B8] mb-1">{tr(lang, 'Mode Montant')}</label>
                        <select
                          value={liveOrderAmountMode}
                          onChange={(e) => {
                            setLiveOrderAmountMode(e.target.value as 'fixed' | 'percentage');
                            setLiveOrderDraftCheck(null);
                          }}
                          className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/10 rounded text-[#F1F5F9]"
                        >
                          <option value="fixed">{tr(lang, 'USDT Fixe')}</option>
                          <option value="percentage">{tr(lang, '% Solde')}</option>
                        </select>
                      </div>
                      <div>
                        <label className="block text-[11px] text-[#94A3B8] mb-1">{tr(lang, 'Levier (1–125)')}</label>
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
                        <label className="block text-[11px] text-[#94A3B8] mb-1">{tr(lang, "Prix Limite d'Entrée")}</label>
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
                          placeholder={tr(lang, 'Prix SL...')}
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
                          placeholder={tr(lang, 'Prix TP...')}
                          className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/10 rounded font-mono-tabular text-[#10B981]"
                        />
                      </div>
                    </div>

                    <div className="flex items-center justify-between gap-2 pt-1">
                      <div className="flex items-center gap-2">
                        <span className="text-[#94A3B8]">{lang === 'en' ? 'Margin:' : 'Marge :'}</span>
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
                        <div className="text-[#10B981] font-bold">{tr(lang, '✅ Pré-validation Binance réussie :')}</div>
                        <div>
                          {lang === 'en' ? 'Ref price:' : 'Prix réf:'} {Number(liveOrderDraftCheck.price).toFixed(2)} •{' '}
                          {tr(lang, 'Quantité')}: <strong>{liveOrderDraftCheck.quantity}</strong>
                        </div>
                        <div>
                          {lang === 'en' ? 'Committed margin:' : 'Marge engagée:'}{' '}
                          {Number(liveOrderDraftCheck.margin_amount).toFixed(2)} USDT • Notional:{' '}
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
                        {tr(lang, "1. Valider l'Ordre")}
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
                        {tr(lang, '2. Confirmer Envoi Réel')}
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
                        {lang === 'en'
                          ? `Open AutoTrade & Live Positions (${liveTrades.open.length}) — /positions`
                          : `Positions AutoTrade & Live Ouvertes (${liveTrades.open.length}) — /positions`}
                      </h3>
                      <button
                        type="button"
                        onClick={loadLiveAccountAndOrders}
                        className="text-xs text-[#10B981] hover:underline"
                      >
                        {tr(lang, 'Actualiser')}
                      </button>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-left border-collapse text-xs">
                        <thead>
                          <tr className="border-b border-white/[0.07] text-[#64748B] font-mono-tabular uppercase">
                            <th className="py-2.5 px-4">{tr(lang, 'ID / Actif')}</th>
                            <th className="py-2.5 px-4">{tr(lang, 'Sens & Marché')}</th>
                            <th className="py-2.5 px-4 text-right">{tr(lang, 'Quantité')}</th>
                            <th className="py-2.5 px-4 text-right">{tr(lang, 'Entrée')}</th>
                            <th className="py-2.5 px-4 text-right">SL / TP</th>
                            <th className="py-2.5 px-4 text-right">{tr(lang, 'Action (/close)')}</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-white/[0.05] font-mono-tabular">
                          {liveTrades.open.length === 0 ? (
                            <tr>
                              <td colSpan={6} className="py-6 text-center text-[#64748B] font-sans">
                                {tr(lang, 'Aucune position ouverte enregistrée localement.')}
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
                                    {tr(lang, 'Fermer')} (#{t.id})
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
                        {lang === 'en'
                          ? `Protective & Limit Orders Open on Binance (${liveOpenOrders.length})`
                          : `Ordres Protecteurs & Limites Ouverts sur Binance (${liveOpenOrders.length})`}
                      </h3>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-left border-collapse text-xs">
                        <thead>
                          <tr className="border-b border-white/[0.07] text-[#64748B] font-mono-tabular uppercase">
                            <th className="py-2.5 px-4">{tr(lang, 'Symbole')}</th>
                            <th className="py-2.5 px-4">{tr(lang, 'Type & Sens')}</th>
                            <th className="py-2.5 px-4 text-right">{tr(lang, 'Prix / Stop')}</th>
                            <th className="py-2.5 px-4 text-right">{tr(lang, 'Quantité')}</th>
                            <th className="py-2.5 px-4 text-right">{tr(lang, 'Action')}</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-white/[0.05] font-mono-tabular">
                          {liveOpenOrders.length === 0 ? (
                            <tr>
                              <td colSpan={5} className="py-5 text-center text-[#64748B] font-sans">
                                {tr(lang, 'Aucun ordre ouvert sur Binance actuellement.')}
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
                                    {tr(lang, 'Annuler')}
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
                      {lang === 'en' ? 'Validated Signals History' : 'Historique des Signaux Validés'} ({signalHistory.length})
                    </h3>
                    <p className="text-xs text-[#64748B]">
                      {tr(lang, 'Registre persistant des signaux générés par SignalEngine avec suivi de performance.')}
                    </p>
                  </div>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="border-b border-white/[0.07] text-[#64748B] font-mono-tabular uppercase">
                        <th className="py-3 px-4">ID</th>
                        <th className="py-3 px-4">{tr(lang, 'Actif & TF')}</th>
                        <th className="py-3 px-4">Signal</th>
                        <th className="py-3 px-4 text-right">Score</th>
                        <th className="py-3 px-4 text-right">{tr(lang, 'Prix Entrée')}</th>
                        <th className="py-3 px-4 text-right">SL / TP</th>
                        <th className="py-3 px-4 text-right">R:R</th>
                        <th className="py-3 px-4">{tr(lang, 'Statut')}</th>
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
                    {tr(lang, 'Abonnement PRO / VIP & Codes Promotionnels')}
                  </h3>
                  <form onSubmit={handleRedeemPromo} className="flex gap-2 text-xs">
                    <input
                      type="text"
                      value={promoCodeInput}
                      onChange={(e) => setPromoCodeInput(e.target.value)}
                      placeholder={tr(lang, 'Code Promo (ex: TEDDYPRO ou TEDDYVIP)')}
                      className="flex-1 px-3 py-2 bg-[#090D16] border border-white/10 rounded-lg font-mono-tabular uppercase text-[#F1F5F9]"
                      required
                    />
                    <button
                      type="submit"
                      className="px-4 py-2 bg-[#10B981] text-[#090D16] font-semibold rounded-lg"
                    >
                      {tr(lang, 'Activer Code')}
                    </button>
                  </form>

                  <div className="grid grid-cols-2 gap-3 pt-2 text-xs">
                    <button
                      onClick={() => handleGenerateBinancePay('pro')}
                      className="p-3.5 rounded-lg bg-[#090D16] border border-[#10B981]/40 hover:bg-[#10B981]/10 text-left space-y-1 transition-colors"
                    >
                      <div className="font-semibold text-[#10B981]">{tr(lang, 'Générer Mémo Binance Pay PRO')}</div>
                      <div className="font-mono-tabular text-[#F1F5F9]">{tr(lang, '19 USDT / mois')}</div>
                    </button>
                    <button
                      onClick={() => handleGenerateBinancePay('vip')}
                      className="p-3.5 rounded-lg bg-[#090D16] border border-[#F59E0B]/40 hover:bg-[#F59E0B]/10 text-left space-y-1 transition-colors"
                    >
                      <div className="font-semibold text-[#F59E0B]">{tr(lang, 'Générer Mémo Binance Pay VIP')}</div>
                      <div className="font-mono-tabular text-[#F1F5F9]">{tr(lang, '49 USDT / mois')}</div>
                    </button>
                  </div>

                  {paymentInfo && (
                    <div className="p-4 rounded-lg bg-[#090D16] border border-[#10B981]/40 space-y-1.5 text-xs font-mono-tabular">
                      <div className="text-[#10B981] font-semibold">{tr(lang, 'Instructions Binance Pay :')}</div>
                      <div>
                        {tr(lang, 'Binance ID destinataire :')}{' '}
                        <strong className="text-[#F1F5F9]">{paymentInfo.binance_id || tr(lang, 'Non configuré')}</strong>
                      </div>
                      <div>
                        {tr(lang, 'Montant à envoyer :')} <strong className="text-[#F1F5F9]">{paymentInfo.amount_usdt} USDT</strong>
                      </div>
                      <div>
                        {tr(lang, 'Mémo obligatoire :')} <strong className="text-[#F59E0B]">{paymentInfo.memo}</strong>
                      </div>
                    </div>
                  )}
                </div>

                {/* Security PIN Configuration */}
                <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-5 space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="font-display font-semibold text-base text-[#F1F5F9]">
                      {tr(lang, 'Code PIN de Sécurité (4 chiffres)')}
                    </h3>
                    <span className="text-xs font-mono-tabular text-[#10B981]">
                      {user.has_pin ? tr(lang, '● PIN Configuré') : tr(lang, '○ Aucun PIN')}
                    </span>
                  </div>
                  <form onSubmit={handleSavePin} className="space-y-3 text-xs">
                    {user.has_pin && (
                      <div>
                        <label className="block text-[#94A3B8] mb-1">{tr(lang, 'Ancien Code PIN')}</label>
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
                      <label className="block text-[#94A3B8] mb-1">{tr(lang, 'Nouveau Code PIN (4 chiffres)')}</label>
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
                      {tr(lang, 'Enregistrer le Code PIN')}
                    </button>
                  </form>
                </div>
              </div>

              {/* Right: Direct Admin Support Messaging */}
              <div className="lg:col-span-6 bg-[#111827] border border-white/[0.07] rounded-xl p-5 space-y-4">
                <h3 className="font-display font-semibold text-base text-[#F1F5F9]">
                  {tr(lang, 'Support Direct Administrateur')}
                </h3>
                <form onSubmit={handleCreateSupportTicket} className="space-y-3 text-xs">
                  <div>
                    <label className="block text-[#94A3B8] mb-1">{tr(lang, 'Sujet')}</label>
                    <input
                      type="text"
                      value={ticketSubject}
                      onChange={(e) => setTicketSubject(e.target.value)}
                      placeholder={tr(lang, 'Validation paiement / Question stratégie...')}
                      className="w-full px-3 py-2 bg-[#090D16] border border-white/10 rounded-lg text-[#F1F5F9]"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-[#94A3B8] mb-1">{tr(lang, 'Message')}</label>
                    <textarea
                      rows={3}
                      value={ticketMessage}
                      onChange={(e) => setTicketMessage(e.target.value)}
                      placeholder={tr(lang, 'Décrivez votre demande...')}
                      className="w-full px-3 py-2 bg-[#090D16] border border-white/10 rounded-lg text-[#F1F5F9]"
                      required
                    />
                  </div>
                  <button
                    type="submit"
                    className="px-4 py-2 bg-[#10B981] text-[#090D16] font-semibold rounded-lg"
                  >
                    {tr(lang, "Envoyer à l'Administrateur")}
                  </button>
                </form>

                <div className="space-y-2.5 pt-3 border-t border-white/[0.07]">
                  <div className="text-xs font-semibold text-[#94A3B8]">{tr(lang, 'Vos échanges récents :')}</div>
                  {tickets.map((t) => (
                    <div key={t.id} className="p-3 rounded-lg bg-[#090D16] border border-white/[0.06] space-y-1.5 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-[#F1F5F9]">{t.subject}</span>
                        <span className="font-mono-tabular text-[11px] text-[#10B981] uppercase">{t.status}</span>
                      </div>
                      <p className="text-[#94A3B8]">{t.message}</p>
                      {t.admin_reply && (
                        <div className="p-2 rounded bg-[#10B981]/10 border border-[#10B981]/30 text-[#34D399]">
                          <strong>{tr(lang, 'Réponse Admin :')}</strong> {t.admin_reply}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* =========================================================
              TAB 7: ADMIN CONSOLE & LOG DOCTOR DIAGNOSTICS (ADMIN ONLY)
             ========================================================= */}
          {activeTab === 'admin' && isAdminUser && (
            <div className="space-y-6">
              {/* Top Summary Metrics for Admin */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-4">
                  <div className="text-[11px] text-[#64748B] uppercase font-mono-tabular">{tr(lang, 'Total Comptes')}</div>
                  <div className="text-xl font-bold font-mono-tabular text-[#F1F5F9] mt-1">
                    {(adminData?.users || []).length}
                  </div>
                </div>
                <div className="bg-[#111827] border border-[#F59E0B]/30 rounded-xl p-4">
                  <div className="text-[11px] text-[#F59E0B] uppercase font-mono-tabular">
                    {tr(lang, "En Attente d'Approbation")}
                  </div>
                  <div className="text-xl font-bold font-mono-tabular text-[#F59E0B] mt-1">
                    {(adminData?.users || []).filter((u: any) => u.account_status === 'PENDING_APPROVAL').length}
                  </div>
                </div>
                <div className="bg-[#111827] border border-[#10B981]/30 rounded-xl p-4">
                  <div className="text-[11px] text-[#10B981] uppercase font-mono-tabular">
                    {tr(lang, 'Comptes Approuvés')}
                  </div>
                  <div className="text-xl font-bold font-mono-tabular text-[#10B981] mt-1">
                    {(adminData?.users || []).filter((u: any) => u.account_status === 'APPROVED').length}
                  </div>
                </div>
                <div className="bg-[#111827] border border-[#F43F5E]/30 rounded-xl p-4">
                  <div className="text-[11px] text-[#FB7185] uppercase font-mono-tabular">
                    {tr(lang, 'Suspendus / Refusés')}
                  </div>
                  <div className="text-xl font-bold font-mono-tabular text-[#FB7185] mt-1">
                    {
                      (adminData?.users || []).filter(
                        (u: any) => u.account_status === 'SUSPENDED' || u.account_status === 'REJECTED'
                      ).length
                    }
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                {/* User Management, Approval & Quotas Table */}
                <div className="lg:col-span-8 bg-[#111827] border border-white/[0.07] rounded-xl p-5 space-y-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <h3 className="font-display font-semibold text-base text-[#F1F5F9]">
                        {tr(lang, 'Contrôle des Accès, Approbation des Comptes & Quotas Utilisateurs')}
                      </h3>
                      <p className="text-xs text-[#64748B]">
                        {tr(
                          lang,
                          'Approuvez, refusez, suspendez ou ajustez les quotas individuels de chaque utilisateur.'
                        )}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 flex-wrap">
                      {(
                        [
                          { id: 'ALL', label: tr(lang, 'Tous') },
                          { id: 'PENDING_APPROVAL', label: tr(lang, 'En attente') },
                          { id: 'APPROVED', label: tr(lang, 'Approuvés') },
                          { id: 'SUSPENDED', label: tr(lang, 'Suspendus') },
                          { id: 'REJECTED', label: tr(lang, 'Refusés') },
                        ] as const
                      ).map((f) => (
                        <button
                          key={f.id}
                          type="button"
                          onClick={() => setAdminUserFilter(f.id)}
                          className={`px-2.5 py-1 rounded text-[11px] font-mono-tabular border transition-colors ${
                            adminUserFilter === f.id
                              ? 'bg-[#10B981]/20 border-[#10B981] text-[#10B981]'
                              : 'bg-[#090D16] border-white/10 text-[#94A3B8] hover:text-[#F1F5F9]'
                          }`}
                        >
                          {f.label}
                        </button>
                      ))}
                      <button
                        onClick={loadAdminOverview}
                        className="px-2.5 py-1 bg-[#1E293B] hover:bg-[#334155] rounded text-xs text-[#10B981] flex items-center gap-1"
                      >
                        <RefreshCw className="w-3.5 h-3.5" /> {tr(lang, 'Actualiser')}
                      </button>
                    </div>
                  </div>

                  {/* Per-User Quota Editor Modal/Drawer Inline */}
                  {editingQuotasUid !== null && (
                    <div className="p-4 rounded-xl bg-[#090D16] border border-[#10B981]/40 space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="text-xs font-semibold text-[#10B981]">
                          {lang === 'en'
                            ? `Quota Configuration — User #${editingQuotasUid}`
                            : `Configuration des quotas — Utilisateur #${editingQuotasUid}`}
                        </div>
                        <button
                          type="button"
                          onClick={() => setEditingQuotasUid(null)}
                          className="text-xs text-[#94A3B8] hover:text-[#F1F5F9]"
                        >
                          {tr(lang, 'Fermer')}
                        </button>
                      </div>
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                        <div>
                          <label className="block text-[11px] text-[#94A3B8] mb-1">{tr(lang, 'Analyses / jour')}</label>
                          <input
                            type="number"
                            min={1}
                            value={quotaForm.daily_analyses}
                            onChange={(e) =>
                              setQuotaForm((prev) => ({ ...prev, daily_analyses: parseInt(e.target.value, 10) || 1 }))
                            }
                            className="w-full px-2.5 py-1.5 bg-[#111827] border border-white/10 rounded font-mono-tabular text-[#F1F5F9]"
                          />
                        </div>
                        <div>
                          <label className="block text-[11px] text-[#94A3B8] mb-1">{tr(lang, 'Scans / jour')}</label>
                          <input
                            type="number"
                            min={1}
                            value={quotaForm.daily_scans}
                            onChange={(e) =>
                              setQuotaForm((prev) => ({ ...prev, daily_scans: parseInt(e.target.value, 10) || 1 }))
                            }
                            className="w-full px-2.5 py-1.5 bg-[#111827] border border-white/10 rounded font-mono-tabular text-[#F1F5F9]"
                          />
                        </div>
                        <div>
                          <label className="block text-[11px] text-[#94A3B8] mb-1">{tr(lang, 'Alertes actives max')}</label>
                          <input
                            type="number"
                            min={1}
                            value={quotaForm.max_alerts}
                            onChange={(e) =>
                              setQuotaForm((prev) => ({ ...prev, max_alerts: parseInt(e.target.value, 10) || 1 }))
                            }
                            className="w-full px-2.5 py-1.5 bg-[#111827] border border-white/10 rounded font-mono-tabular text-[#F1F5F9]"
                          />
                        </div>
                        <div>
                          <label className="block text-[11px] text-[#94A3B8] mb-1">{tr(lang, 'Paper Trades / jour')}</label>
                          <input
                            type="number"
                            min={1}
                            value={quotaForm.max_paper_trades}
                            onChange={(e) =>
                              setQuotaForm((prev) => ({ ...prev, max_paper_trades: parseInt(e.target.value, 10) || 1 }))
                            }
                            className="w-full px-2.5 py-1.5 bg-[#111827] border border-white/10 rounded font-mono-tabular text-[#F1F5F9]"
                          />
                        </div>
                      </div>
                      <div className="flex justify-end gap-2">
                        <button
                          type="button"
                          onClick={() =>
                            apiFetch('/api/admin/user-quotas', {
                              method: 'POST',
                              body: JSON.stringify({
                                target_user_id: editingQuotasUid,
                                ...quotaForm,
                              }),
                            })
                              .then((res) => {
                                showToast(res.message, 'success');
                                setEditingQuotasUid(null);
                                loadAdminOverview();
                              })
                              .catch((err) => showToast(err.message, 'error'))
                          }
                          className="px-4 py-1.5 bg-[#10B981] hover:bg-[#059669] text-[#090D16] font-semibold text-xs rounded-lg"
                        >
                          {tr(lang, 'Enregistrer les Quotas')}
                        </button>
                      </div>
                    </div>
                  )}

                  <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse text-xs">
                      <thead>
                        <tr className="border-b border-white/[0.07] text-[#64748B] font-mono-tabular uppercase">
                          <th className="py-2.5 px-3">{tr(lang, 'Utilisateur & Email')}</th>
                          <th className="py-2.5 px-3">{tr(lang, 'Statut & Rôle')}</th>
                          <th className="py-2.5 px-3">{tr(lang, 'Quotas (Utilisé / Max)')}</th>
                          <th className="py-2.5 px-3">{tr(lang, 'Inscription / Connexion')}</th>
                          <th className="py-2.5 px-3 text-right">{tr(lang, "Actions d'Approbation & Rôles")}</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/[0.05] font-mono-tabular">
                        {(adminData?.users || [])
                          .filter((u: any) =>
                            adminUserFilter === 'ALL' ? true : u.account_status === adminUserFilter
                          )
                          .map((u: any) => {
                            const status: string = u.account_status || 'PENDING_APPROVAL';
                            const q = u.quotas || {
                              daily_analyses: 25,
                              daily_scans: 15,
                              max_alerts: 10,
                              max_paper_trades: 30,
                            };
                            const qu = u.quota_usage || {
                              analyses_used: 0,
                              scans_used: 0,
                              paper_trades_used: 0,
                            };
                            return (
                              <tr key={u.user_id} className="hover:bg-white/[0.02]">
                                <td className="py-3 px-3">
                                  <div className="font-semibold text-[#F1F5F9]">
                                    {u.display_name || u.username || `Trader #${u.user_id}`}
                                  </div>
                                  <div className="text-[11px] text-[#94A3B8]">{u.email || tr(lang, 'Compte Telegram')}</div>
                                  <div className="text-[10px] text-[#64748B]">
                                    ID: #{u.user_id} {u.auth_provider ? `• ${u.auth_provider.toUpperCase()}` : ''}
                                  </div>
                                </td>
                                <td className="py-3 px-3 space-y-1">
                                  <div>
                                    <span
                                      className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${
                                        status === 'APPROVED'
                                          ? 'bg-[#10B981]/15 border-[#10B981]/40 text-[#10B981]'
                                          : status === 'PENDING_APPROVAL'
                                          ? 'bg-[#F59E0B]/15 border-[#F59E0B]/40 text-[#F59E0B]'
                                          : 'bg-[#F43F5E]/15 border-[#F43F5E]/40 text-[#FB7185]'
                                      }`}
                                    >
                                      {status}
                                    </span>
                                  </div>
                                  <div className="text-[11px] uppercase text-[#10B981] font-bold">
                                    {lang === 'en' ? 'Role:' : 'Rôle :'} {u.role} {u.memo ? `• Memo: ${u.memo}` : ''}
                                  </div>
                                </td>
                                <td className="py-3 px-3 text-[11px] space-y-0.5">
                                  <div>
                                    Analyses: <span className="text-[#F1F5F9]">{qu.analyses_used}</span>/{q.daily_analyses}
                                  </div>
                                  <div>
                                    Scans: <span className="text-[#F1F5F9]">{qu.scans_used}</span>/{q.daily_scans}
                                  </div>
                                  <div>
                                    {lang === 'en' ? 'Max alerts:' : 'Alertes max:'}{' '}
                                    <span className="text-[#F1F5F9]">{q.max_alerts}</span> • Paper:{' '}
                                    <span className="text-[#F1F5F9]">{qu.paper_trades_used}</span>/{q.max_paper_trades}
                                  </div>
                                  <button
                                    type="button"
                                    onClick={() => {
                                      setEditingQuotasUid(u.user_id);
                                      setQuotaForm({
                                        daily_analyses: q.daily_analyses,
                                        daily_scans: q.daily_scans,
                                        max_alerts: q.max_alerts,
                                        max_paper_trades: q.max_paper_trades,
                                      });
                                    }}
                                    className="text-[10px] text-[#10B981] hover:underline"
                                  >
                                    {tr(lang, 'Modifier quotas')}
                                  </button>
                                </td>
                                <td className="py-3 px-3 text-[10px] text-[#94A3B8] space-y-1">
                                  <div>
                                    {lang === 'en' ? 'Created:' : 'Créé:'}{' '}
                                    {u.created_at
                                      ? new Date(Number(u.created_at) * 1000).toLocaleDateString(
                                          lang === 'en' ? 'en-US' : 'fr-FR'
                                        )
                                      : '—'}
                                  </div>
                                  <div>
                                    {lang === 'en' ? 'Last login:' : 'Dernière conn.:'}{' '}
                                    {u.last_login_at && Number(u.last_login_at) > 0
                                      ? new Date(Number(u.last_login_at) * 1000).toLocaleString(
                                          lang === 'en' ? 'en-US' : 'fr-FR'
                                        )
                                      : '—'}
                                  </div>
                                </td>
                                <td className="py-3 px-3 text-right">
                                  <div className="flex flex-wrap justify-end gap-1.5">
                                    {status !== 'APPROVED' && (
                                      <button
                                        onClick={() =>
                                          apiFetch('/api/admin/user-status', {
                                            method: 'POST',
                                            body: JSON.stringify({
                                              target_user_id: u.user_id,
                                              action: 'approve',
                                              role: u.role || 'tester',
                                            }),
                                          }).then((res) => {
                                            showToast(res.message, 'success');
                                            loadAdminOverview();
                                          })
                                        }
                                        className="px-2.5 py-1 bg-[#10B981] hover:bg-[#059669] text-[#090D16] font-bold rounded text-[10px]"
                                      >
                                        {tr(lang, 'Approuver')}
                                      </button>
                                    )}
                                    {status === 'PENDING_APPROVAL' && (
                                      <button
                                        onClick={() =>
                                          apiFetch('/api/admin/user-status', {
                                            method: 'POST',
                                            body: JSON.stringify({ target_user_id: u.user_id, action: 'reject' }),
                                          }).then((res) => {
                                            showToast(res.message, 'info');
                                            loadAdminOverview();
                                          })
                                        }
                                        className="px-2 py-1 bg-[#F43F5E]/20 hover:bg-[#F43F5E]/30 border border-[#F43F5E]/40 text-[#FB7185] rounded text-[10px]"
                                      >
                                        {tr(lang, 'Refuser')}
                                      </button>
                                    )}
                                    {!u.is_admin && status === 'APPROVED' && (
                                      <button
                                        onClick={() =>
                                          apiFetch('/api/admin/user-status', {
                                            method: 'POST',
                                            body: JSON.stringify({ target_user_id: u.user_id, action: 'suspend' }),
                                          }).then((res) => {
                                            showToast(res.message, 'info');
                                            loadAdminOverview();
                                          })
                                        }
                                        className="px-2 py-1 bg-[#F59E0B]/20 hover:bg-[#F59E0B]/30 border border-[#F59E0B]/40 text-[#F59E0B] rounded text-[10px]"
                                      >
                                        {tr(lang, 'Suspendre')}
                                      </button>
                                    )}
                                    {(status === 'SUSPENDED' || status === 'REJECTED') && (
                                      <button
                                        onClick={() =>
                                          apiFetch('/api/admin/user-status', {
                                            method: 'POST',
                                            body: JSON.stringify({ target_user_id: u.user_id, action: 'reactivate' }),
                                          }).then((res) => {
                                            showToast(res.message, 'success');
                                            loadAdminOverview();
                                          })
                                        }
                                        className="px-2 py-1 bg-[#10B981]/20 hover:bg-[#10B981]/30 border border-[#10B981]/40 text-[#10B981] rounded text-[10px]"
                                      >
                                        {tr(lang, 'Réactiver')}
                                      </button>
                                    )}
                                    {['tester', 'pro', 'vip'].map((r) => (
                                      <button
                                        key={r}
                                        onClick={() =>
                                          apiFetch('/api/admin/user-role', {
                                            method: 'POST',
                                            body: JSON.stringify({
                                              target_user_id: u.user_id,
                                              role: r,
                                              action: 'set_role',
                                            }),
                                          }).then((res) => {
                                            showToast(res.message, 'success');
                                            loadAdminOverview();
                                            loadUserAndCoreData();
                                          })
                                        }
                                        className={`px-2 py-1 rounded text-[10px] uppercase ${
                                          u.role === r
                                            ? 'bg-[#10B981]/25 text-[#10B981] border border-[#10B981]/40'
                                            : 'bg-[#1E293B] hover:bg-[#334155] text-[#F1F5F9]'
                                        }`}
                                      >
                                        {r}
                                      </button>
                                    ))}
                                    {u.memo && (
                                      <button
                                        onClick={() =>
                                          apiFetch('/api/admin/user-role', {
                                            method: 'POST',
                                            body: JSON.stringify({
                                              target_user_id: u.user_id,
                                              action: 'confirm_binance',
                                            }),
                                          }).then((res) => {
                                            showToast(res.message, 'success');
                                            loadAdminOverview();
                                          })
                                        }
                                        className="px-2 py-1 bg-[#10B981] text-[#090D16] font-semibold rounded text-[10px]"
                                      >
                                        {tr(lang, 'Valider Pay')}
                                      </button>
                                    )}
                                  </div>
                                </td>
                              </tr>
                            );
                          })}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Log Doctor Diagnostics, Security Audit Log & Broadcast */}
                <div className="lg:col-span-4 space-y-6">
                  {/* Security Events Audit Log */}
                  <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-5 space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="font-display font-semibold text-base text-[#F1F5F9] flex items-center gap-2">
                        <Shield className="w-4 h-4 text-[#10B981]" />
                        <span>{tr(lang, 'Journal de Sécurité & Accès')}</span>
                      </h3>
                      <span className="text-[10px] font-mono-tabular text-[#64748B]">
                        {(adminData?.security_events || []).length} {lang === 'en' ? 'events' : 'événements'}
                      </span>
                    </div>
                    <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                      {(adminData?.security_events || []).length === 0 ? (
                        <div className="text-xs text-[#64748B]">
                          {tr(lang, 'Aucun événement de sécurité enregistré.')}
                        </div>
                      ) : (
                        (adminData?.security_events || []).map((ev: SecurityEvent) => (
                          <div
                            key={ev.id}
                            className="p-2.5 rounded-lg bg-[#090D16] border border-white/[0.06] text-[11px] space-y-1"
                          >
                            <div className="flex items-center justify-between font-mono-tabular">
                              <span
                                className={`font-bold ${
                                  ev.severity === 'critical'
                                    ? 'text-[#FB7185]'
                                    : ev.severity === 'warning'
                                    ? 'text-[#F59E0B]'
                                    : 'text-[#10B981]'
                                }`}
                              >
                                {ev.event_type}
                              </span>
                              <span className="text-[10px] text-[#64748B]">
                                {ev.created_at
                                  ? new Date(Number(ev.created_at) * 1000).toLocaleTimeString(
                                      lang === 'en' ? 'en-US' : 'fr-FR'
                                    )
                                  : ''}
                              </span>
                            </div>
                            <div className="text-[#94A3B8]">{ev.details}</div>
                            <div className="text-[10px] text-[#64748B] font-mono-tabular">
                              {ev.email ? `Email: ${ev.email} • ` : ''}
                              {ev.user_id ? `UID: #${ev.user_id} • ` : ''}
                              IP: {ev.ip_address || '—'}
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>

                  <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-5 space-y-4">
                    <h3 className="font-display font-semibold text-base text-[#F1F5F9]">
                      {tr(lang, 'Diagnostic Système (Log Doctor)')}
                    </h3>
                    <div className="flex gap-2 text-xs">
                      <input
                        type="text"
                        value={doctorQuestion}
                        onChange={(e) => setDoctorQuestion(e.target.value)}
                        placeholder={tr(lang, 'Posez une question diagnostic (ex: erreur Binance, DB, Telegram)...')}
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
                        {tr(lang, 'Analyser')}
                      </button>
                    </div>
                    <pre className="p-3.5 rounded-lg bg-[#090D16] border border-white/[0.06] text-[11px] font-mono-tabular text-[#94A3B8] whitespace-pre-wrap max-h-64 overflow-y-auto">
                      {doctorReport || tr(lang, 'Chargement du diagnostic...')}
                    </pre>
                  </div>

                  {/* Admin Broadcast */}
                  <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-5 space-y-3">
                    <h3 className="font-display font-semibold text-base text-[#F1F5F9]">
                      {tr(lang, 'Diffusion Globale (Broadcast)')}
                    </h3>
                    <input
                      type="text"
                      value={broadcastTitle}
                      onChange={(e) => setBroadcastTitle(e.target.value)}
                      placeholder={tr(lang, "Titre de l'annonce...")}
                      className="w-full px-3 py-2 bg-[#090D16] border border-white/10 rounded-lg text-xs text-[#F1F5F9]"
                    />
                    <textarea
                      rows={2}
                      value={broadcastBody}
                      onChange={(e) => setBroadcastBody(e.target.value)}
                      placeholder={tr(lang, 'Message diffusé à tous les utilisateurs...')}
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
                      {tr(lang, 'Diffuser à tous les comptes')}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* =========================================================
              TAB 8: STRATEGY LAB & BACKTESTING ENGINE (ADMIN ONLY)
             ========================================================= */}
          {activeTab === 'strategy_lab' && Boolean(user?.is_admin || user?.role === 'admin') && (
            <StrategyLabView
              lang={lang}
              onShowToast={(type, text) => showToast(text, type)}
            />
          )}
        </main>

        {/* Mobile Bottom Consolidated Hub Navigation Bar (4 Hubs for standard users, 5 for Admins) */}
        <nav className="md:hidden fixed bottom-0 inset-x-0 z-30 bg-[#0B101B]/95 backdrop-blur-md border-t border-white/[0.08] flex items-center justify-around py-1.5 px-1">
          {mobileHubGroups.map((hub) => {
            const Icon = hub.icon;
            const isHubActive = hub.tabs.some((t) => t.id === activeTab);
            return (
              <button
                key={hub.hubId}
                onClick={() => {
                  if (!isHubActive) {
                    setActiveTab(hub.tabs[0].id);
                  } else if (hub.tabs.length > 1) {
                    const idx = hub.tabs.findIndex((t) => t.id === activeTab);
                    const nextIdx = (idx + 1) % hub.tabs.length;
                    setActiveTab(hub.tabs[nextIdx].id);
                  }
                }}
                className={`flex flex-col items-center justify-center py-1 px-2 rounded-lg text-[10px] font-medium relative transition-colors ${
                  isHubActive ? 'text-[#10B981]' : 'text-[#94A3B8]'
                }`}
              >
                <Icon className="w-4 h-4 mb-0.5" />
                <span className="truncate max-w-[68px]">{hub.label}</span>
                {hub.tabs.length > 1 && (
                  <span
                    className={`w-1 h-1 rounded-full mt-0.5 ${
                      isHubActive ? 'bg-[#10B981]' : 'bg-white/20'
                    }`}
                  />
                )}
                {hub.hasSafetyDot && (
                  <span
                    className={`absolute top-1 right-2 w-2 h-2 rounded-full ${
                      hub.apiConnected ? 'bg-[#10B981]' : 'bg-[#F43F5E]'
                    }`}
                  />
                )}
              </button>
            );
          })}
        </nav>
      </div>
    </div>
  );
}
export default App;
