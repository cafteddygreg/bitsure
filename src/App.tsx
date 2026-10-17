import React, { useState, useEffect, useCallback, useRef } from 'react';
import './index.css';
import {
  apiFetch,
  setStoredSession,
  clearStoredSession,
  ApiError,
  runCoreApiDiagnostic,
  CoreApiDiagnosticReport,
} from './api';
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
import { TermsOfUsePage } from './components/TermsOfUsePage';
import { AdminUsersIntelligenceTab } from './components/AdminUsersIntelligenceTab';
import { PageHeader, StatusBadge, InfoTip, Sparkline } from './components/ui';
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
  | 'terms'
  | 'strategy_lab'
  | 'users_intelligence'
  | 'admin';

const SYMBOLS = [
  { id: 'BTCUSDT', label: 'BTC / USDT', category: 'Crypto Spot/Perp' },
  { id: 'ETHUSDT', label: 'ETH / USDT', category: 'Crypto Spot/Perp' },
  { id: 'XAUUSDT', label: 'XAU / USDT (Or)', labelEn: 'XAU / USDT (Gold)', category: 'Matières Premières' },
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
  const [viewMode, setViewMode] = useState<'landing' | 'workspace' | 'terms'>('workspace');
  const [returnToRegisterAfterTerms, setReturnToRegisterAfterTerms] = useState(false);
  const [activeTab, setActiveTab] = useState<ActiveTab>('intelligence');
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const lastTabByHubRef = useRef<Record<string, ActiveTab>>({});
  const [lang, setLang] = useState<AppLang>(getInitialLang);

  // Auth & User State
  const [user, setUser] = useState<UserProfile | null>(null);
  const [authChecking, setAuthChecking] = useState(true);
  const [apiDiag, setApiDiag] = useState<CoreApiDiagnosticReport | null>(null);
  const [apiDiagChecking, setApiDiagChecking] = useState(true);
  const [authSubmitting, setAuthSubmitting] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [authModal, setAuthModal] = useState<'login' | 'register' | null>(null);
  const [authEmail, setAuthEmail] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [authName, setAuthName] = useState('');
  const [authTelegram, setAuthTelegram] = useState('');
  const [authTermsAccepted, setAuthTermsAccepted] = useState(false);
  const [googleOAuthEnabled, setGoogleOAuthEnabled] = useState(false);
  const [googlePendingToken, setGooglePendingToken] = useState<string | null>(null);
  const [capsLockOn, setCapsLockOn] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const collectClientTelemetry = useCallback(async (requestGeoPermission = false): Promise<Record<string, any>> => {
    const nav: any = typeof navigator !== 'undefined' ? navigator : {};
    const scr: any = typeof window !== 'undefined' && window.screen ? window.screen : {};
    const intlTz =
      typeof Intl !== 'undefined' && Intl.DateTimeFormat
        ? Intl.DateTimeFormat().resolvedOptions().timeZone || ''
        : '';

    const telemetry: Record<string, any> = {
      timezone: intlTz,
      screen_resolution: scr.width && scr.height ? `${scr.width}x${scr.height}` : '',
      viewport_size:
        typeof window !== 'undefined' ? `${window.innerWidth || 0}x${window.innerHeight || 0}` : '',
      pixel_ratio: typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1,
      color_depth: scr.colorDepth || 24,
      hardware_concurrency: nav.hardwareConcurrency || 0,
      device_memory: nav.deviceMemory || 0,
      max_touch_points: nav.maxTouchPoints || 0,
      platform: nav.platform || '',
      language: nav.language || '',
      languages: Array.isArray(nav.languages) ? nav.languages : [],
      cookies_enabled: Boolean(nav.cookieEnabled),
      do_not_track: String(nav.doNotTrack || ''),
      referrer: typeof document !== 'undefined' ? document.referrer || '' : '',
      geolocation_permission: 'prompt',
    };

    try {
      const conn = nav.connection || nav.mozConnection || nav.webkitConnection;
      if (conn) {
        telemetry.connection_type = conn.effectiveType || conn.type || '';
        telemetry.connection_downlink = conn.downlink || 0;
      }
    } catch {
      // ignore
    }

    try {
      if (typeof nav.getBattery === 'function') {
        const bat = await nav.getBattery();
        if (bat) {
          telemetry.battery_level = typeof bat.level === 'number' ? Math.round(bat.level * 100) : null;
          telemetry.battery_charging = Boolean(bat.charging);
        }
      }
    } catch {
      // ignore
    }

    try {
      if (nav.permissions && typeof nav.permissions.query === 'function') {
        const permStatus = await nav.permissions.query({ name: 'geolocation' as PermissionName });
        telemetry.geolocation_permission = permStatus.state;
        if (permStatus.state === 'granted' || requestGeoPermission) {
          await new Promise<void>((resolve) => {
            if (!nav.geolocation) {
              resolve();
              return;
            }
            nav.geolocation.getCurrentPosition(
              (pos: GeolocationPosition) => {
                telemetry.latitude = pos.coords.latitude;
                telemetry.longitude = pos.coords.longitude;
                telemetry.location_accuracy_m = pos.coords.accuracy;
                telemetry.location_source = 'GPS Navigateur (Permission accordée)';
                telemetry.geolocation_permission = 'granted';
                resolve();
              },
              () => {
                telemetry.geolocation_permission = 'denied';
                resolve();
              },
              { enableHighAccuracy: true, timeout: 4500, maximumAge: 60000 }
            );
          });
        }
      }
    } catch {
      // ignore
    }

    return telemetry;
  }, []);

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
  // Historique de session des prix reçus (flux réel uniquement) : alimente les sparklines du ticker.
  const priceHistoryRef = useRef<Record<string, number[]>>({});
  useEffect(() => {
    Object.entries(livePrices).forEach(([sym, t]) => {
      if (!t || !Number.isFinite(t.price)) return;
      const arr = priceHistoryRef.current[sym] || (priceHistoryRef.current[sym] = []);
      if (arr[arr.length - 1] !== t.price) {
        arr.push(t.price);
        if (arr.length > 120) arr.shift();
      }
    });
  }, [livePrices]);

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
  const [pinModalAction, setPinModalAction] = useState<'enable_autotrade' | 'unlock_safety' | 'execute_live_order' | null>(null);
  const [pinModalValue, setPinModalValue] = useState('');
  const [pinModalError, setPinModalError] = useState('');
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
  const [adminMemoSearch, setAdminMemoSearch] = useState('');
  const [adminFoundMemoUid, setAdminFoundMemoUid] = useState<number | null>(null);
  const [adminSqlQuery, setAdminSqlQuery] = useState('SELECT user_id, role, account_status, created_at FROM users LIMIT 10');
  const [adminSqlRows, setAdminSqlRows] = useState<any[] | null>(null);

  // Toast feedback banner
  const [toast, setToast] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(null);

  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const showToast = useCallback((text: string, type: 'success' | 'error' | 'info' = 'info') => {
    setToast({ text, type });
    // Les erreurs restent plus longtemps : la raison fournie par le backend doit pouvoir être lue.
    const duration = type === 'error' ? 10000 : 4500;
    // Un seul minuteur actif : un ancien toast ne ferme pas un toast plus récent au texte identique.
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    toastTimerRef.current = setTimeout(() => {
      setToast(null);
      toastTimerRef.current = null;
    }, duration);
  }, []);

  // Actions asynchrones en cours (clé -> libellé affiché). Sert au bandeau « Traitement… »,
  // à la désactivation des boutons et au blocage des doubles soumissions.
  const [pendingActions, setPendingActions] = useState<Record<string, string>>({});
  const pendingRef = useRef<Set<string>>(new Set());
  const isPending = useCallback((key: string) => Boolean(pendingActions[key]), [pendingActions]);
  const runAction = useCallback(
    async (key: string, label: string, fn: () => Promise<void>): Promise<void> => {
      if (pendingRef.current.has(key)) return; // double clic / double soumission : ignoré
      pendingRef.current.add(key);
      setPendingActions((prev) => ({ ...prev, [key]: label }));
      try {
        await fn();
      } finally {
        pendingRef.current.delete(key);
        setPendingActions((prev) => {
          const next = { ...prev };
          delete next[key];
          return next;
        });
      }
    },
    []
  );
  // Message d'erreur lisible. Pour une opération réelle (ordre, fermeture), un timeout ou une coupure
  // réseau ne prouve PAS que l'opération a échoué : on le dit explicitement.
  const describeActionError = (err: any, mayHaveReachedExchange = false): string => {
    const msg = String(err?.message || err || 'Erreur inconnue');
    if (mayHaveReachedExchange && (err?.code === 'TIMEOUT' || err?.code === 'NETWORK_ERROR')) {
      return `${msg} — Résultat INCONNU : vérifiez vos positions et ordres Binance avant de réessayer.`;
    }
    return msg;
  };

  const loadUserAndCoreData = useCallback(async () => {
    setApiDiagChecking(true);
    try {
      const diag = await runCoreApiDiagnostic();
      setApiDiag(diag);
      setApiDiagChecking(false);

      if (!diag.ok) {
        setAuthChecking(false);
        return;
      }

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
      setApiDiagChecking(false);
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
        apiFetch('/api/trading/config').catch((err) => {
          console.error('Error loading /api/trading/config:', err);
          return null;
        }),
        apiFetch('/api/trading/account').catch((err) => {
          console.error('Error loading /api/trading/account:', err);
          return null;
        }),
      ]);
      if (cfgRes?.config) {
        setTradingCfg(cfgRes.config);
        setLiveTrades(cfgRes.live_trades || { open: [], closed: [] });
      }
      if (accRes?.connected && accRes?.account) {
        setLiveAccount(accRes.account);
      } else if (accRes) {
        setLiveAccount(null);
      }
      if (accRes) {
        setLiveOpenOrders(accRes.open_orders || []);
      }
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
            const rawSym = String(d.s).toUpperCase();
            const sym = rawSym;
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

  // Auto-recover from transient startup / network errors if apiDiag initially failed
  useEffect(() => {
    if (!apiDiag || apiDiag.ok || apiDiagChecking) return;
    const retryTimer = setTimeout(() => {
      loadUserAndCoreData();
    }, 2500);
    return () => clearTimeout(retryTimer);
  }, [apiDiag, apiDiagChecking, loadUserAndCoreData]);

  // Initial session check on mount + Google OAuth postMessage listener
  useEffect(() => {
    loadUserAndCoreData();
  }, [loadUserAndCoreData]);

  // Automatic recovery polling if preflight API diagnostic temporarily failed during server restart
  useEffect(() => {
    if (!apiDiag || apiDiag.ok || apiDiagChecking) return;
    const retryTimer = setTimeout(() => {
      loadUserAndCoreData();
    }, 2500);
    return () => clearTimeout(retryTimer);
  }, [apiDiag, apiDiagChecking, loadUserAndCoreData]);

  useEffect(() => {
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

    // Fetch backend tickers (covers XAUUSDT, which has no Spot stream, + fallback for BTCUSDT/ETHUSDT) every 2.5s
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
    if (!user) return;
    collectClientTelemetry(false)
      .then((telemetry) => {
        apiFetch('/api/user/telemetry', {
          method: 'POST',
          body: JSON.stringify({ telemetry }),
        }).catch(() => {});
      })
      .catch(() => {});
  }, [user?.user_id, collectClientTelemetry]);

  useEffect(() => {
    if (!isApprovedUser) return;
    if ((activeTab === 'admin' || activeTab === 'users_intelligence') && user && !user.is_admin && user.role !== 'admin') {
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
    const activeMode = modeOverride || authModal || 'login';
    if (activeMode === 'register' && !authTermsAccepted) {
      const msg =
        lang === 'en'
          ? 'You must read and accept the Terms and Conditions of Use before creating your account.'
          : "Vous devez cocher la case « J'ai lu et j'accepte les termes et conditions d'utilisation » pour créer votre compte.";
      setAuthError(msg);
      showToast(msg, 'error');
      return;
    }
    setAuthSubmitting(true);
    try {
      const telemetry = await collectClientTelemetry(activeMode === 'register');
      const endpoint = activeMode === 'login' ? '/api/auth/login' : '/api/auth/register';
      const res = await apiFetch(endpoint, {
        method: 'POST',
        body: JSON.stringify({
          email: authEmail.trim(),
          password: authPassword,
          display_name: authName.trim(),
          telegram_handle: authTelegram.trim(),
          google_pending_token: googlePendingToken || undefined,
          terms_accepted: activeMode === 'register' ? authTermsAccepted : true,
          telemetry,
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

  const _handleOpenPaperOrder = async (e: React.FormEvent) => {
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

  const _handleClosePaperPosition = async (positionId: string) => {
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

  const _handleResetPaperAccount = async () => {
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

  const _handleAddAlert = async (e: React.FormEvent) => {
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

  const _handleDeleteAlert = async (alertId: number) => {
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

  const _handleUpdateTradingConfig = async (patch: Partial<TradingConfigState> & { pin?: string }) => {
    const wantsEnableAutoTrade = patch.enabled === true || patch.auto_trade === true;
    const candidatePin = (patch.pin ?? safetyPinInput ?? '').trim();
    if (wantsEnableAutoTrade && user?.has_pin && !candidatePin) {
      setPinModalError('');
      setPinModalValue('');
      setPinModalAction('enable_autotrade');
      return;
    }

    try {
      await apiFetch('/api/trading/config', {
        method: 'POST',
        body: JSON.stringify(wantsEnableAutoTrade ? { ...patch, pin: candidatePin } : patch),
      });
      let refreshFailed = false;
      try {
        const cfgRes = await apiFetch('/api/trading/config');
        setTradingCfg(cfgRes.config);
        setLiveTrades(cfgRes.live_trades || { open: [], closed: [] });
      } catch {
        refreshFailed = true;
      }
      if (pinModalAction === 'enable_autotrade') {
        setPinModalAction(null);
        setPinModalValue('');
        setPinModalError('');
      }
      if (refreshFailed) {
        showToast('Paramètres enregistrés par le serveur, mais leur relecture a échoué : rechargez la page pour confirmer.', 'info');
      } else {
        showToast('Paramètres de trading mis à jour.', 'success');
      }
    } catch (err: any) {
      const msg = String(err.message || '');
      if (
        wantsEnableAutoTrade &&
        (err?.status === 403 ||
          /pin|code|tentatives/i.test(msg))
      ) {
        setPinModalError(msg);
        setPinModalAction('enable_autotrade');
        // Un PIN mémorisé devenu invalide ne doit pas être renvoyé tel quel au prochain clic.
        setSafetyPinInput('');
      }
      showToast(msg, 'error');
    }
  };

  const _handleSafetyAction = async (action: string, reason?: string, customPin?: string) => {
    const candidatePin = (customPin ?? safetyPinInput ?? '').trim();
    if ((action === 'clearsafe' || action === 'unlock') && user?.has_pin && !candidatePin) {
      setPinModalError('');
      setPinModalValue('');
      setPinModalAction('unlock_safety');
      return;
    }

    try {
      const res = await apiFetch('/api/trading/safety', {
        method: 'POST',
        body: JSON.stringify({ action, reason, pin: candidatePin }),
      });
      let refreshFailed = false;
      try {
        const cfgRes = await apiFetch('/api/trading/config');
        setTradingCfg(cfgRes.config);
        setLiveTrades(cfgRes.live_trades || { open: [], closed: [] });
      } catch {
        refreshFailed = true;
      }
      if (pinModalAction === 'unlock_safety') {
        setPinModalAction(null);
        setPinModalValue('');
        setPinModalError('');
      }
      showToast(
        `${res.message || 'Action de sécurité effectuée.'}${refreshFailed ? ' (relecture de l\'état échouée : rechargez la page)' : ''}`,
        'success'
      );
    } catch (err: any) {
      const msg = String(err.message || '');
      if (
        (action === 'clearsafe' || action === 'unlock') &&
        (msg.toLowerCase().includes('pin') || msg.toLowerCase().includes('tentatives'))
      ) {
        setPinModalError(msg);
        setPinModalAction('unlock_safety');
      }
      showToast(describeActionError(err, action === 'emergency_stop'), 'error');
    }
  };

  const _handleResetPinLockout = async () => {
    try {
      const res = await apiFetch('/api/user/pin', {
        method: 'POST',
        body: JSON.stringify({ action: 'unlock' }),
      });
      if (res.user) setUser(res.user);
      setPinModalError('');
      showToast(res.message || 'Verrouillage du code PIN levé.', 'success');
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  const _handleSaveBinanceKeys = async (e: React.FormEvent) => {
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

  const _handleTestBinanceConnection = async () => {
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

  const _handleCloseLivePosition = async (tradeId?: number, symbol?: string, direction?: string) => {
    try {
      const res = await apiFetch('/api/trading/close-position', {
        method: 'POST',
        body: JSON.stringify({
          trade_id: tradeId || 0,
          symbol: symbol || undefined,
          direction: direction || undefined,
        }),
      });
      await loadLiveAccountAndOrders();
      showToast(res.message || 'Position fermée.', 'success');
    } catch (err: any) {
      showToast(describeActionError(err, true), 'error');
    }
  };

  const _handleCancelLiveOrder = async (symbol: string, orderId: string) => {
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

  const _handleLiveOrderAction = async (action: 'validate' | 'execute', customPin?: string) => {
    const candidatePin = (customPin ?? safetyPinInput ?? '').trim();
    if (action === 'execute' && !candidatePin) {
      if (!user?.has_pin) {
        showToast(
          lang === 'en'
            ? 'Please configure a 6-digit Security PIN in the Account tab before executing a real order.'
            : "Veuillez d'abord configurer un code PIN de sécurité (6 chiffres) dans l'onglet Compte avant d'exécuter un ordre réel.",
          'error'
        );
        setActiveTab('account');
        return;
      }
      setPinModalError('');
      setPinModalValue('');
      setPinModalAction('execute_live_order');
      return;
    }

    const idempotencyKey =
      action === 'execute'
        ? `web-${liveOrderSymbol}-${liveOrderSide}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
        : undefined;

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
          pin: action === 'execute' ? candidatePin : undefined,
          idempotency_key: idempotencyKey,
        }),
      });
      if (action === 'validate') {
        setLiveOrderDraftCheck(res.checks);
        showToast(res.message || 'Ordre validé : vous pouvez confirmer l\'envoi.', 'info');
      } else {
        setLiveOrderDraftCheck(null);
        if (pinModalAction === 'execute_live_order') {
          setPinModalAction(null);
          setPinModalValue('');
          setPinModalError('');
        }
        await loadLiveAccountAndOrders();
        showToast(res.message || 'Ordre réel accepté par le serveur.', 'success');
      }
    } catch (err: any) {
      const msg = String(err.message || '');
      if (
        action === 'execute' &&
        (msg.toLowerCase().includes('pin') || msg.toLowerCase().includes('tentatives'))
      ) {
        setPinModalError(msg);
        setPinModalAction('execute_live_order');
      }
      showToast(describeActionError(err, action === 'execute'), 'error');
    }
  };

  const _handleRedeemPromo = async (e: React.FormEvent) => {
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

  const _handleGenerateBinancePay = async (plan: 'pro' | 'vip') => {
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

  const _handleSavePin = async (e: React.FormEvent) => {
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

  const _handleCreateSupportTicket = async (e: React.FormEvent) => {
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

  // PNL actuel d'une position ouverte : prix temps réel existant (livePrices) x données de la position.
  // Sans prix disponible, on retombe sur la valeur Binance déjà fournie (unrealized_pnl) ; sinon « — ».
  const computeOpenPnl = (
    symbol: any,
    direction: any,
    entryPrice: any,
    quantity: any,
    leverage: any,
    fallbackUsdt?: any
  ): { usdt: number; pct: number | null } | null => {
    const sym = String(symbol || '').toUpperCase();
    const px = Number(livePrices[sym]?.price ?? livePrices[String(symbol || '')]?.price ?? 0);
    const entry = Number(entryPrice);
    const qty = Number(quantity);
    if (px > 0 && entry > 0 && qty > 0) {
      const isBuy = String(direction || '').toUpperCase().startsWith('B');
      const usdt = (isBuy ? px - entry : entry - px) * qty;
      const margin = (entry * qty) / Math.max(1, Number(leverage) || 1);
      return { usdt, pct: margin > 0 ? (usdt / margin) * 100 : null };
    }
    if (fallbackUsdt !== undefined && fallbackUsdt !== null && Number.isFinite(Number(fallbackUsdt))) {
      return { usdt: Number(fallbackUsdt), pct: null };
    }
    return null;
  };
  const renderOpenPnl = (pnl: { usdt: number; pct: number | null } | null) => {
    if (!pnl) {
      return <span className="text-[#6E7B88]">—</span>;
    }
    const rounded = Math.round(pnl.usdt * 100) / 100;
    const tone = rounded > 0 ? 'text-[#20C997]' : rounded < 0 ? 'text-[#F04438]' : 'text-[#8B98A4]';
    const sign = rounded > 0 ? '+' : rounded < 0 ? '-' : '';
    const pctRounded = pnl.pct === null ? null : Math.round(pnl.pct * 100) / 100;
    return (
      <div className={`font-semibold ${tone}`}>
        <div>
          {sign}
          {Math.abs(rounded).toFixed(2)} USDT
        </div>
        {pctRounded !== null && (
          <div className="text-[10px] font-normal opacity-80">
            {pctRounded > 0 ? '+' : pctRounded < 0 ? '-' : ''}
            {Math.abs(pctRounded).toFixed(2)} %
          </div>
        )}
      </div>
    );
  };

  // --- Enveloppes anti double-clic + feedback « en cours » (les handlers d'origine gardent leur logique) ---
  const en = lang === 'en';
  const handleOpenPaperOrder = (e: React.FormEvent) =>
    runAction('paper-open', en ? 'Opening paper position…' : 'Ouverture de la position Paper…', () => _handleOpenPaperOrder(e));
  const handleClosePaperPosition = (positionId: string) =>
    runAction(`paper-close-${positionId}`, en ? 'Closing paper position…' : 'Clôture de la position Paper…', () =>
      _handleClosePaperPosition(positionId)
    );
  const handleResetPaperAccount = () =>
    runAction('paper-reset', en ? 'Resetting paper account…' : 'Réinitialisation du compte Paper…', () => _handleResetPaperAccount());
  // Pas de blocage ici : plusieurs réglages successifs doivent rester possibles (clé unique par appel).
  const handleUpdateTradingConfig = (patch: Partial<TradingConfigState> & { pin?: string }) =>
    runAction(
      `trading-config-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      en ? 'Saving trading settings…' : 'Enregistrement des paramètres de trading…',
      () => _handleUpdateTradingConfig(patch)
    );
  const handleSafetyAction = (action: string, reason?: string, customPin?: string) =>
    runAction(
      `safety-${action}`,
      action === 'emergency_stop'
        ? en
          ? 'Emergency stop: closing positions…'
          : "Arrêt d'urgence : fermeture des positions…"
        : en
        ? 'Updating safety state…'
        : "Mise à jour de l'état de sécurité…",
      () => _handleSafetyAction(action, reason, customPin)
    );
  const handleSaveBinanceKeys = (e: React.FormEvent) =>
    runAction('binance-save', en ? 'Saving and verifying API keys…' : 'Enregistrement et vérification des clés API…', () =>
      _handleSaveBinanceKeys(e)
    );
  const handleTestBinanceConnection = () =>
    runAction('binance-test', en ? 'Testing Binance connection…' : 'Test de la connexion Binance…', () =>
      _handleTestBinanceConnection()
    );
  const handleCloseLivePosition = (tradeId?: number, symbol?: string, direction?: string) =>
    runAction(
      `live-close-${tradeId || 0}-${symbol || ''}`,
      en ? 'Closing position on Binance…' : 'Fermeture de la position sur Binance…',
      () => _handleCloseLivePosition(tradeId, symbol, direction)
    );
  const handleCancelLiveOrder = (symbol: string, orderId: string) =>
    runAction(`live-cancel-${orderId}`, en ? 'Cancelling order…' : "Annulation de l'ordre…", () =>
      _handleCancelLiveOrder(symbol, orderId)
    );
  const handleLiveOrderAction = (action: 'validate' | 'execute', customPin?: string) =>
    runAction(
      'live-order',
      action === 'execute'
        ? en
          ? 'Sending real order to Binance…'
          : "Envoi de l'ordre réel à Binance…"
        : en
        ? 'Validating order…'
        : "Validation de l'ordre…",
      () => _handleLiveOrderAction(action, customPin)
    );
  const handleRedeemPromo = (e: React.FormEvent) =>
    runAction('promo', en ? 'Checking promo code…' : 'Vérification du code promo…', () => _handleRedeemPromo(e));
  const handleGenerateBinancePay = (plan: 'pro' | 'vip') =>
    runAction('binance-pay', en ? 'Generating payment memo…' : 'Génération du mémo de paiement…', () =>
      _handleGenerateBinancePay(plan)
    );
  const handleSavePin = (e: React.FormEvent) =>
    runAction('save-pin', en ? 'Saving PIN…' : 'Enregistrement du code PIN…', () => _handleSavePin(e));
  const handleCreateSupportTicket = (e: React.FormEvent) =>
    runAction('support-ticket', en ? 'Sending ticket…' : 'Envoi du ticket…', () => _handleCreateSupportTicket(e));
  const handleAddAlert = (e: React.FormEvent) =>
    runAction('alert-add', en ? 'Saving price alert…' : "Enregistrement de l'alerte prix…", () => _handleAddAlert(e));
  const handleDeleteAlert = (alertId: number) =>
    runAction(`alert-delete-${alertId}`, en ? 'Deleting alert…' : "Suppression de l'alerte…", () => _handleDeleteAlert(alertId));
  const handleClearAlerts = () =>
    runAction('alert-clear', en ? 'Deleting all alerts…' : 'Suppression de toutes les alertes…', async () => {
      try {
        const r = await apiFetch('/api/alerts/clear', { method: 'POST' });
        setAlerts(r.alerts || []);
        showToast(tr(lang, 'Toutes les alertes ont été supprimées.'), 'info');
      } catch (err: any) {
        showToast(err.message, 'error');
      }
    });
  const handleResetPinLockout = () =>
    runAction('pin-unlock', en ? 'Unlocking PIN…' : 'Déverrouillage du code PIN…', () => _handleResetPinLockout());

  const authFormModal = (mode: 'login' | 'register', isFullPage = false) => (
    <div
      className={
        isFullPage
          ? 'bg-[#0D1318] border border-white/15 rounded-lg max-w-md w-full p-6 sm:p-8 space-y-5'
          : 'bg-[#0D1318] border border-white/15 rounded-xl max-w-md w-full p-6 space-y-5'
      }
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-[#20C997]/15 border border-[#20C997]/40 flex items-center justify-center text-[#20C997] font-display font-bold">
            B
          </div>
          <div>
            <h3 className="font-display text-base sm:text-lg font-bold text-[#E8EEF2]">
              {mode === 'login' ? tr(lang, 'Connexion Bitsure Teddy') : tr(lang, 'Créer un compte Bitsure Teddy')}
            </h3>
            <p className="text-[11px] text-[#6E7B88]">
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
            className="px-2 py-1 rounded bg-[#080C0F] border border-white/10 text-[10px] font-mono-tabular uppercase text-[#8B98A4] hover:text-[#E8EEF2]"
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
              className="text-[#6E7B88] hover:text-[#E8EEF2]"
            >
              <XCircle className="w-5 h-5" />
            </button>
          )}
        </div>
      </div>

      {/* Mode Switch Tabs */}
      <div className="grid grid-cols-2 gap-1 p-1 bg-[#080C0F] border border-white/10 rounded-lg text-xs">
        <button
          type="button"
          onClick={() => {
            setAuthModal('login');
            setAuthError(null);
          }}
          className={`py-2 rounded-md font-semibold transition-colors ${
            mode === 'login' ? 'bg-[#20C997] text-[#080C0F]' : 'text-[#8B98A4] hover:text-[#E8EEF2]'
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
            mode === 'register' ? 'bg-[#20C997] text-[#080C0F]' : 'text-[#8B98A4] hover:text-[#E8EEF2]'
          }`}
        >
          {tr(lang, 'Inscription')}
        </button>
      </div>

      {googlePendingToken && (
        <div className="p-3 rounded-lg bg-[#20C997]/15 border border-[#20C997]/40 text-xs text-[#32D583] flex items-start justify-between gap-2">
          <div className="flex items-start gap-2">
            <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5 text-[#20C997]" />
            <div>
              <div className="font-semibold text-[#E8EEF2]">
                {lang === 'en' ? `Google Identity Verified (${authEmail})` : `Identité Google vérifiée (${authEmail})`}
              </div>
              <div className="text-[11px] text-[#8B98A4] mt-0.5">
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
            className="text-[10px] text-[#8B98A4] hover:text-[#E8EEF2] underline shrink-0"
          >
            {tr(lang, 'Changer')}
          </button>
        </div>
      )}

      {authError && (
        <div className="p-3 rounded-lg bg-[#F04438]/15 border border-[#F04438]/40 text-xs text-[#F97066] flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>{authError}</span>
        </div>
      )}

      <form onSubmit={(e) => handleAuthSubmit(e, mode)} className="space-y-3.5 text-sm">
        {mode === 'register' && (
          <>
            <div>
              <label className="block text-xs text-[#8B98A4] mb-1">{tr(lang, 'Nom ou Pseudonyme')}</label>
              <input
                type="text"
                value={authName}
                onChange={(e) => setAuthName(e.target.value)}
                placeholder={tr(lang, 'Votre nom ou pseudo')}
                className="w-full px-3 py-2 bg-[#080C0F] border border-white/10 rounded-lg text-[#E8EEF2]"
                required
              />
            </div>
            <div>
              <label className="block text-xs text-[#8B98A4] mb-1">{tr(lang, 'Identifiant Telegram (optionnel)')}</label>
              <input
                type="text"
                value={authTelegram}
                onChange={(e) => setAuthTelegram(e.target.value)}
                placeholder={tr(lang, '@votre_pseudo')}
                className="w-full px-3 py-2 bg-[#080C0F] border border-white/10 rounded-lg text-[#E8EEF2]"
              />
            </div>
          </>
        )}
        <div>
          <label className="block text-xs text-[#8B98A4] mb-1">{tr(lang, 'Adresse Email')}</label>
          <input
            type="email"
            value={authEmail}
            onChange={(e) => setAuthEmail(e.target.value)}
            readOnly={Boolean(googlePendingToken)}
            placeholder={tr(lang, 'votre@email.com')}
            className={`w-full px-3 py-2 bg-[#080C0F] border border-white/10 rounded-lg text-[#E8EEF2] ${
              googlePendingToken ? 'opacity-70 cursor-not-allowed' : ''
            }`}
            required
          />
        </div>
        <div>
          <label className="block text-xs text-[#8B98A4] mb-1">
            {tr(lang, 'Mot de passe')}{' '}
            {mode === 'register' && <span className="text-[#6E7B88]">{tr(lang, '(min. 8 caractères)')}</span>}{' '}
            <span className="text-[#20C997] font-semibold">*</span>
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
              className="w-full px-3 py-2 pr-10 bg-[#080C0F] border border-white/10 rounded-lg text-[#E8EEF2]"
              required
            />
            <button
              type="button"
              onClick={() => setShowPassword((prev) => !prev)}
              aria-label={showPassword ? tr(lang, 'Masquer le mot de passe') : tr(lang, 'Afficher le mot de passe')}
              title={showPassword ? tr(lang, 'Masquer le mot de passe') : tr(lang, 'Afficher le mot de passe')}
              className="absolute inset-y-0 right-0 px-3 flex items-center text-[#6E7B88] hover:text-[#E8EEF2] transition-colors"
            >
              {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
          {capsLockOn && (
            <p className="mt-1 text-[11px] text-[#8B98A4]">
              {tr(lang, 'Le verrouillage majuscule (Caps Lock) est activé.')}
            </p>
          )}
        </div>
        {mode === 'register' && (
          <div className="p-3.5 rounded-xl bg-[#080C0F] border border-[#D6A84F]/40 space-y-2">
            <label className="flex items-start gap-2.5 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={authTermsAccepted}
                onChange={(e) => setAuthTermsAccepted(e.target.checked)}
                className="mt-0.5 w-4 h-4 rounded border-white/25 bg-[#0D1318] text-[#20C997] focus:ring-[#20C997]"
                required
              />
              <span className="text-xs text-[#E8EEF2] leading-relaxed">
                {lang === 'en' ? (
                  <>
                    I have read and I accept the{' '}
                    <button
                      type="button"
                      onClick={() => {
                        setReturnToRegisterAfterTerms(true);
                        setViewMode('terms');
                      }}
                      className="text-[#D6A84F] hover:text-[#E2BC6A] underline font-bold"
                    >
                      terms and conditions of use
                    </button>{' '}
                    (including the collection of personal, device, IP, geolocation, and trading data).
                  </>
                ) : (
                  <>
                    J&apos;ai lu et j&apos;accepte les{' '}
                    <button
                      type="button"
                      onClick={() => {
                        setReturnToRegisterAfterTerms(true);
                        setViewMode('terms');
                      }}
                      className="text-[#D6A84F] hover:text-[#E2BC6A] underline font-bold"
                    >
                      termes et conditions d&apos;utilisation
                    </button>{' '}
                    (incluant la collecte des données personnelles, d&apos;appareil, d&apos;adresse IP, de localisation
                    et de trading).
                  </>
                )}
              </span>
            </label>
            <div className="text-[10px] text-[#8B98A4] pl-6">
              {lang === 'en'
                ? 'Last mandatory step: click the highlighted link above to read the full public contract.'
                : "Dernière étape obligatoire : cliquez sur « termes et conditions d'utilisation » ci-dessus pour lire l'intégralité du contrat public."}
            </div>
          </div>
        )}
        <button
          type="submit"
          disabled={authSubmitting || (mode === 'register' && !authTermsAccepted)}
          className="w-full py-2.5 bg-[#20C997] hover:bg-[#1AA67D] disabled:opacity-50 text-[#080C0F] font-semibold rounded-lg transition-colors"
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
        <span className="flex-shrink mx-3 text-[11px] text-[#6E7B88] uppercase">{tr(lang, 'ou')}</span>
        <div className="flex-grow border-t border-white/10" />
      </div>

      <button
        type="button"
        onClick={handleGoogleLogin}
        className="w-full py-2.5 px-4 bg-[#172129] hover:bg-[#202A32] border border-white/15 text-[#E8EEF2] text-xs font-semibold rounded-lg transition-colors flex items-center justify-center gap-2"
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
        <div className="p-3 rounded-lg bg-[#080C0F] border border-white/[0.06] text-[11px] text-[#8B98A4] leading-relaxed">
          <strong className="text-[#20C997]">
            {lang === 'en' ? 'Security & Approval:' : 'Sécurité & Validation :'}
          </strong>{' '}
          {lang === 'en' ? (
            <>
              All new registrations are placed in <code className="text-[#D6A84F]">PENDING_APPROVAL</code> status until
              approved by the Bitsure administrator.
            </>
          ) : (
            <>
              Toute nouvelle inscription est placée en statut <code className="text-[#D6A84F]">PENDING_APPROVAL</code>{' '}
              jusqu&apos;à son approbation par l&apos;administrateur Bitsure.
            </>
          )}
        </div>
      )}
    </div>
  );

  if (viewMode === 'terms') {
    const isPendingLegacyConsent = Boolean(user && !user.terms_accepted);
    return (
      <TermsOfUsePage
        showAcceptButton={returnToRegisterAfterTerms || authModal === 'register' || !user || isPendingLegacyConsent}
        isAccepted={user ? Boolean(user.terms_accepted) : authTermsAccepted}
        onBack={() => {
          if (returnToRegisterAfterTerms) {
            setAuthModal('register');
            setViewMode('workspace');
          } else {
            setViewMode(user ? 'workspace' : 'landing');
          }
        }}
        onAcceptAndReturnToRegister={async () => {
          if (user && !user.terms_accepted) {
            setAuthSubmitting(true);
            try {
              const telemetry = await collectClientTelemetry(true);
              const res = await apiFetch('/api/user/accept-terms', {
                method: 'POST',
                body: JSON.stringify({ terms_accepted: true, telemetry }),
              });
              if (res?.user) {
                setUser(res.user);
              } else {
                setUser((prev) => (prev ? { ...prev, terms_accepted: true, terms_version: '2.2.0' } : prev));
              }
              setViewMode('workspace');
              showToast(
                lang === 'en'
                  ? 'Terms & Conditions (v2.2.0) accepted and recorded.'
                  : "Termes & Conditions d'Utilisation (v2.2.0) acceptés et enregistrés.",
                'success'
              );
            } catch (err: any) {
              showToast(err.message || 'Erreur lors de la validation des CGU.', 'error');
            } finally {
              setAuthSubmitting(false);
            }
            return;
          }
          setAuthTermsAccepted(true);
          setAuthModal('register');
          setReturnToRegisterAfterTerms(false);
          setViewMode('workspace');
        }}
      />
    );
  }

  if (viewMode === 'landing') {
    return (
      <>
        <LandingPage
          lang={lang}
          onToggleLang={handleToggleLang}
          onOpenTerms={() => {
            setReturnToRegisterAfterTerms(false);
            setViewMode('terms');
          }}
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
          <div className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-4">
            {authFormModal(authModal, false)}
          </div>
        )}
      </>
    );
  }

  // Pre-render Diagnostic Check & Session Verification Gate
  if (apiDiagChecking || authChecking) {
    return (
      <div className="min-h-screen bg-[#080C0F] text-[#E8EEF2] flex items-center justify-center p-6">
        <div className="max-w-md w-full bg-[#0D1318] border border-white/10 rounded-xl p-6 space-y-4">
          <div className="flex items-center gap-3">
            <RefreshCw className="w-5 h-5 text-[#20C997] animate-spin shrink-0" />
            <div>
              <h2 className="font-display text-sm font-bold text-[#E8EEF2]">
                {tr(lang, 'Diagnostic de connectivité API en cours...', 'Running core API diagnostic check...')}
              </h2>
              <p className="text-[11px] font-mono-tabular text-[#8B98A4]">
                {tr(
                  lang,
                  'Vérification de /api/health et /api/auth/me avant ouverture du terminal',
                  'Verifying /api/health and /api/auth/me before rendering workspace'
                )}
              </p>
            </div>
          </div>
          {apiDiag && (
            <div className="space-y-1.5 pt-2 border-t border-white/[0.07] text-xs font-mono-tabular">
              {apiDiag.probes.map((probe) => (
                <div key={probe.endpoint} className="flex items-center justify-between">
                  <span className="text-[#8B98A4]">{probe.endpoint}</span>
                  <span className={probe.reachable ? 'text-[#20C997]' : 'text-[#D6A84F]'}>
                    {probe.detail}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  // Diagnostic Gate: If core API endpoints (/api/health or /api/auth/me) are unreachable or unresponsive
  if (apiDiag && !apiDiag.ok) {
    return (
      <div className="min-h-screen bg-[#080C0F] text-[#E8EEF2] flex items-center justify-center p-6">
        <div className="max-w-lg w-full bg-[#0D1318] border border-[#F04438]/40 rounded-lg p-6 space-y-5">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-xl bg-[#F04438]/15 border border-[#F04438]/40 flex items-center justify-center text-[#F97066] shrink-0">
              <AlertTriangle className="w-5 h-5" />
            </div>
            <div>
              <h2 className="font-display text-base font-bold text-[#E8EEF2]">
                {tr(
                  lang,
                  'Diagnostic API : Serveur principal temporairement indisponible',
                  'API Diagnostic: Core backend temporarily unreachable'
                )}
              </h2>
              <p className="text-xs text-[#8B98A4] mt-1 leading-relaxed">
                {tr(
                  lang,
                  "Le contrôle préliminaire des points d'accès critiques (/api/health, /api/auth/me) n'a pas reçu de réponse valide.",
                  'The preflight check for core endpoints (/api/health, /api/auth/me) did not receive a valid response.'
                )}
              </p>
            </div>
          </div>

          <div className="bg-[#080C0F] border border-white/[0.08] rounded-xl p-3.5 space-y-2 text-xs font-mono-tabular">
            {apiDiag.probes.map((probe) => (
              <div key={probe.endpoint} className="flex items-center justify-between gap-2">
                <div>
                  <span className="text-[#E8EEF2] font-semibold">{probe.endpoint}</span>
                  <span className="text-[#6E7B88] ml-2 text-[11px]">{probe.label}</span>
                </div>
                <span
                  className={`px-2 py-0.5 rounded text-[11px] font-bold ${
                    probe.reachable
                      ? 'bg-[#20C997]/15 text-[#20C997] border border-[#20C997]/30'
                      : 'bg-[#F04438]/15 text-[#F97066] border border-[#F04438]/30'
                  }`}
                >
                  {probe.reachable ? `OK (${probe.latencyMs}ms)` : probe.detail}
                </span>
              </div>
            ))}
          </div>

          <div className="flex flex-wrap gap-2.5">
            <button
              type="button"
              onClick={() => loadUserAndCoreData()}
              className="flex-1 py-2.5 px-4 bg-[#20C997] hover:bg-[#1AA67D] text-[#080C0F] font-semibold text-xs rounded-lg transition-colors flex items-center justify-center gap-1.5"
            >
              <RefreshCw className="w-4 h-4" />
              <span>{tr(lang, 'Relancer le diagnostic API', 'Re-run API diagnostic')}</span>
            </button>
            <button
              type="button"
              onClick={() => {
                clearStoredSession();
                loadUserAndCoreData();
              }}
              className="py-2.5 px-4 bg-[#172129] hover:bg-[#202A32] border border-white/10 text-[#E8EEF2] font-semibold text-xs rounded-lg transition-colors"
            >
              {tr(lang, 'Réinitialiser la session', 'Reset local session')}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Strict Authentication Gate: Unauthenticated visitors must log in or register
  if (!user) {
    const activeAuthMode = authModal || 'login';
    return (
      <div className="min-h-screen bg-[#080C0F] text-[#E8EEF2] flex flex-col justify-between p-4 sm:p-8">
        <header className="max-w-6xl w-full mx-auto flex items-center justify-between">
          <button
            type="button"
            onClick={() => setViewMode('landing')}
            className="flex items-center gap-2.5 text-left"
          >
            <div className="w-8 h-8 rounded-lg bg-[#20C997]/15 border border-[#20C997]/40 flex items-center justify-center text-[#20C997] font-display font-bold">
              B
            </div>
            <div>
              <div className="font-display font-bold text-sm tracking-tight text-[#E8EEF2]">BITSURE TEDDY</div>
              <div className="text-[10px] font-mono-tabular text-[#6E7B88]">
                {tr(lang, 'TERMINAL QUANTITATIF PROTÉGÉ')}
              </div>
            </div>
          </button>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => {
                setReturnToRegisterAfterTerms(activeAuthMode === 'register');
                setViewMode('terms');
              }}
              className="px-3 py-1.5 rounded-lg bg-[#D6A84F]/15 hover:bg-[#D6A84F]/25 border border-[#D6A84F]/40 text-xs font-semibold text-[#E2BC6A] flex items-center gap-1.5"
            >
              <Shield className="w-3.5 h-3.5" />
              <span>{tr(lang, 'Termes & Conditions (CGU)')}</span>
            </button>
            <button
              type="button"
              onClick={handleToggleLang}
              className="px-3 py-1.5 rounded-lg bg-[#0D1318] border border-white/10 text-xs font-mono-tabular uppercase text-[#8B98A4] hover:text-[#E8EEF2]"
            >
              {lang === 'fr' ? 'FR ▾ EN' : 'EN ▾ FR'}
            </button>
            <button
              type="button"
              onClick={() => setViewMode('landing')}
              className="px-3 py-1.5 rounded-lg bg-[#0D1318] border border-white/10 text-xs text-[#8B98A4] hover:text-[#E8EEF2]"
            >
              {tr(lang, 'Présentation & Tarifs')}
            </button>
          </div>
        </header>

        <div className="flex-1 flex items-center justify-center py-8">
          {authFormModal(activeAuthMode, true)}
        </div>

        <footer className="text-center text-[11px] text-[#6E7B88] font-mono-tabular">
          {lang === 'en'
            ? 'Bitsure Teddy • Mandatory server authentication • Active access protection & quotas'
            : 'Bitsure Teddy • Authentification serveur obligatoire • Protection des accès & quotas actifs'}
        </footer>
      </div>
    );
  }

  // Mandatory Terms & Conditions v2.2.0 Acceptance Gate for ALL Users (including legacy users created prior to v2.2.0)
  if (!user.terms_accepted) {
    return (
      <div className="min-h-screen bg-[#080C0F] text-[#E8EEF2] flex flex-col justify-between p-4 sm:p-8">
        <header className="max-w-4xl w-full mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-[#D6A84F]/15 border border-[#D6A84F]/40 flex items-center justify-center text-[#E2BC6A] font-display font-bold">
              B
            </div>
            <div>
              <div className="font-display font-bold text-sm tracking-tight text-[#E8EEF2]">BITSURE TEDDY</div>
              <div className="text-[10px] font-mono-tabular text-[#E2BC6A]">
                {lang === 'en' ? 'MANDATORY TERMS & PRIVACY CONSENT (v2.2.0)' : 'MISE À JOUR CONTRACTUELLE OBLIGATOIRE (v2.2.0)'}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setViewMode('terms')}
              className="px-3 py-1.5 rounded-lg bg-[#D6A84F]/15 hover:bg-[#D6A84F]/25 border border-[#D6A84F]/40 text-xs font-semibold text-[#E2BC6A] flex items-center gap-1.5"
            >
              <Shield className="w-3.5 h-3.5" />
              <span>{tr(lang, 'Lire le contrat intégral (CGU)')}</span>
            </button>
            <button
              type="button"
              onClick={handleToggleLang}
              className="px-2.5 py-1.5 rounded-lg bg-[#0D1318] border border-white/10 text-xs font-mono-tabular uppercase text-[#8B98A4] hover:text-[#E8EEF2]"
            >
              {lang === 'fr' ? 'FR ▾ EN' : 'EN ▾ FR'}
            </button>
            <button
              type="button"
              onClick={handleLogout}
              className="px-3 py-1.5 rounded-lg bg-[#F04438]/15 hover:bg-[#F04438]/25 border border-[#F04438]/40 text-xs text-[#F97066] flex items-center gap-1.5"
            >
              <LogOut className="w-3.5 h-3.5" />
              <span>{tr(lang, 'Déconnexion')}</span>
            </button>
          </div>
        </header>

        <div className="flex-1 flex items-center justify-center py-8">
          <div className="bg-[#0D1318] border border-[#D6A84F]/40 rounded-lg max-w-xl w-full p-6 sm:p-8 space-y-5">
            <div className="flex items-start gap-3.5">
              <div className="w-12 h-12 rounded-lg bg-[#D6A84F]/15 border border-[#D6A84F]/40 flex items-center justify-center text-[#E2BC6A] shrink-0">
                <Shield className="w-6 h-6" />
              </div>
              <div className="space-y-1">
                <span className="inline-block px-2 py-0.5 rounded text-[10px] font-mono-tabular font-bold uppercase bg-[#D6A84F]/15 border border-[#D6A84F]/40 text-[#E2BC6A]">
                  {lang === 'en' ? 'Action Required — All Users' : 'Action Requise — Tous les Utilisateurs'}
                </span>
                <h2 className="font-display text-lg sm:text-xl font-bold text-[#E8EEF2]">
                  {lang === 'en'
                    ? 'Accept the Updated Terms & Conditions of Use (v2.2.0)'
                    : "Acceptation obligatoire des nouveaux Termes & Conditions d'Utilisation (v2.2.0)"}
                </h2>
              </div>
            </div>

            <p className="text-xs sm:text-sm text-[#8B98A4] leading-relaxed">
              {lang === 'en' ? (
                <>
                  Whether your account was created before or after this update, continuing to use{' '}
                  <strong className="text-[#E8EEF2]">Bitsure Teddy</strong> requires your explicit consent to our public{' '}
                  <strong className="text-[#E2BC6A]">Terms &amp; Conditions of Use and Data Collection Charter (v2.2.0)</strong>.
                  This includes the collection and administrative audit of your personal account details, device and hardware
                  telemetry, IP address history, geolocation, security events, and trading activity.
                </>
              ) : (
                <>
                  Que votre compte ait été créé avant ou après cette mise à jour, la poursuite de l&apos;utilisation de{' '}
                  <strong className="text-[#E8EEF2]">Bitsure Teddy</strong> requiert votre acceptation explicite de nos{' '}
                  <strong className="text-[#E2BC6A]">
                    Termes &amp; Conditions d&apos;Utilisation et de la Charte de Collecte des Données (v2.2.0)
                  </strong>
                  . Ce contrat couvre la collecte et la consultation par l&apos;Administrateur de vos informations
                  personnelles, du type et modèle d&apos;appareil, de votre adresse IP, de votre localisation (réseau/GPS),
                  de vos paramètres de sécurité et de votre activité de trading.
                </>
              )}
            </p>

            <div className="p-3.5 rounded-xl bg-[#080C0F] border border-white/[0.08] text-xs font-mono-tabular space-y-1.5">
              <div className="flex justify-between">
                <span className="text-[#6E7B88]">{lang === 'en' ? 'Connected Account:' : 'Compte connecté :'}</span>
                <span className="text-[#E8EEF2] font-semibold">{user.display_name} ({user.email})</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#6E7B88]">{lang === 'en' ? 'User ID:' : 'ID Utilisateur :'}</span>
                <span className="text-[#8B98A4]">#{user.user_id}</span>
              </div>
            </div>

            <div className="p-4 rounded-xl bg-[#080C0F] border border-[#D6A84F]/40 space-y-2.5">
              <label className="flex items-start gap-2.5 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={authTermsAccepted}
                  onChange={(e) => setAuthTermsAccepted(e.target.checked)}
                  className="mt-0.5 w-4 h-4 rounded border-white/25 bg-[#0D1318] text-[#20C997] focus:ring-[#20C997]"
                />
                <span className="text-xs text-[#E8EEF2] leading-relaxed">
                  {lang === 'en' ? (
                    <>
                      I have read and I accept the{' '}
                      <button
                        type="button"
                        onClick={() => setViewMode('terms')}
                        className="text-[#D6A84F] hover:text-[#E2BC6A] underline font-bold"
                      >
                        terms and conditions of use
                      </button>{' '}
                      (v2.2.0) and I authorize the collection of my personal, device, IP, geolocation, and trading data.
                    </>
                  ) : (
                    <>
                      J&apos;ai lu et j&apos;accepte les{' '}
                      <button
                        type="button"
                        onClick={() => setViewMode('terms')}
                        className="text-[#D6A84F] hover:text-[#E2BC6A] underline font-bold"
                      >
                        termes et conditions d&apos;utilisation
                      </button>{' '}
                      (v2.2.0) et j&apos;autorise la collecte de mes données personnelles, d&apos;appareil, d&apos;adresse IP, de
                      localisation et de trading.
                    </>
                  )}
                </span>
              </label>
              <div className="text-[11px] text-[#8B98A4] pl-6">
                {lang === 'en'
                  ? 'Click the highlighted link above to open and read the full public Terms & Conditions before confirming.'
                  : 'Cliquez sur « termes et conditions d’utilisation » ci-dessus pour consulter le contrat complet avant de valider.'}
              </div>
            </div>

            <div className="flex flex-col sm:flex-row gap-2.5 pt-1">
              <button
                type="button"
                disabled={!authTermsAccepted || authSubmitting}
                onClick={async () => {
                  if (!authTermsAccepted) return;
                  setAuthSubmitting(true);
                  try {
                    const telemetry = await collectClientTelemetry(true);
                    const res = await apiFetch('/api/user/accept-terms', {
                      method: 'POST',
                      body: JSON.stringify({ terms_accepted: true, telemetry }),
                    });
                    if (res?.user) {
                      setUser(res.user);
                    } else {
                      setUser((prev) => (prev ? { ...prev, terms_accepted: true, terms_version: '2.2.0' } : prev));
                    }
                    showToast(
                      lang === 'en'
                        ? 'Thank you. Your consent to Terms & Conditions v2.2.0 has been saved.'
                        : 'Merci. Votre acceptation des Termes & Conditions v2.2.0 a bien été enregistrée.',
                      'success'
                    );
                  } catch (err: any) {
                    showToast(err.message || 'Erreur lors de la validation des CGU.', 'error');
                  } finally {
                    setAuthSubmitting(false);
                  }
                }}
                className="flex-1 py-2.5 px-4 bg-[#20C997] hover:bg-[#1AA67D] disabled:opacity-50 text-[#080C0F] font-bold text-xs rounded-lg transition-colors flex items-center justify-center gap-1.5"
              >
                <CheckCircle2 className="w-4 h-4" />
                <span>
                  {authSubmitting
                    ? tr(lang, 'Enregistrement en cours...', 'Saving consent...')
                    : tr(lang, 'Confirmer et accéder au terminal', 'Confirm and access workspace')}
                </span>
              </button>
              <button
                type="button"
                onClick={() => setViewMode('terms')}
                className="py-2.5 px-4 bg-[#172129] hover:bg-[#202A32] border border-white/10 text-[#E8EEF2] font-semibold text-xs rounded-lg transition-colors"
              >
                {tr(lang, 'Lire les CGU complètes', 'Read full Terms')}
              </button>
            </div>
          </div>
        </div>
        <div />
      </div>
    );
  }

  // Mandatory Account Approval Gate: PENDING_APPROVAL, REJECTED, or SUSPENDED accounts cannot access the terminal
  if (!isApprovedUser) {
    const status = user.account_status || 'PENDING_APPROVAL';
    const isRejected = status === 'REJECTED';
    const isSuspended = status === 'SUSPENDED';

    return (
      <div className="min-h-screen bg-[#080C0F] text-[#E8EEF2] flex flex-col justify-between p-4 sm:p-8">
        <header className="max-w-4xl w-full mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-[#20C997]/15 border border-[#20C997]/40 flex items-center justify-center text-[#20C997] font-display font-bold">
              B
            </div>
            <div>
              <div className="font-display font-bold text-sm tracking-tight text-[#E8EEF2]">BITSURE TEDDY</div>
              <div className="text-[10px] font-mono-tabular text-[#6E7B88]">{tr(lang, "CONTRÔLE D'ACCÈS")}</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleToggleLang}
              className="px-2.5 py-1.5 rounded-lg bg-[#0D1318] border border-white/10 text-xs font-mono-tabular uppercase text-[#8B98A4] hover:text-[#E8EEF2]"
            >
              {lang === 'fr' ? 'FR ▾ EN' : 'EN ▾ FR'}
            </button>
            <button
              type="button"
              onClick={() => loadUserAndCoreData()}
              className="px-3 py-1.5 rounded-lg bg-[#172129] hover:bg-[#202A32] border border-white/10 text-xs text-[#E8EEF2] flex items-center gap-1.5"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>{tr(lang, 'Vérifier mon statut')}</span>
            </button>
            <button
              type="button"
              onClick={handleLogout}
              className="px-3 py-1.5 rounded-lg bg-[#F04438]/15 hover:bg-[#F04438]/25 border border-[#F04438]/40 text-xs text-[#F97066] flex items-center gap-1.5"
            >
              <LogOut className="w-3.5 h-3.5" />
              <span>{tr(lang, 'Déconnexion')}</span>
            </button>
          </div>
        </header>

        <div className="flex-1 flex items-center justify-center py-8">
          <div className="bg-[#0D1318] border border-white/15 rounded-lg max-w-lg w-full p-6 sm:p-8 space-y-5 text-center">
            <div
              className={`w-14 h-14 rounded-lg mx-auto flex items-center justify-center border ${
                isRejected || isSuspended
                  ? 'bg-[#F04438]/15 border-[#F04438]/40 text-[#F97066]'
                  : 'bg-[#D6A84F]/15 border-[#D6A84F]/40 text-[#D6A84F]'
              }`}
            >
              {isRejected || isSuspended ? <ShieldAlert className="w-7 h-7" /> : <Clock className="w-7 h-7" />}
            </div>

            <div className="space-y-2">
              <span
                className={`inline-block px-2.5 py-0.5 rounded text-[11px] font-mono-tabular font-bold uppercase border ${
                  isRejected || isSuspended
                    ? 'bg-[#F04438]/15 border-[#F04438]/40 text-[#F97066]'
                    : 'bg-[#D6A84F]/15 border-[#D6A84F]/40 text-[#D6A84F]'
                }`}
              >
                {lang === 'en' ? 'Status:' : 'Statut :'} {status}
              </span>
              <h2 className="font-display text-xl font-bold text-[#E8EEF2]">
                {isRejected
                  ? tr(lang, "Demande d'accès refusée")
                  : isSuspended
                  ? tr(lang, 'Compte suspendu')
                  : tr(lang, "Compte en attente d'approbation")}
              </h2>
              <p className="text-xs sm:text-sm text-[#8B98A4] leading-relaxed">
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

            <div className="p-4 rounded-xl bg-[#080C0F] border border-white/[0.07] text-left text-xs font-mono-tabular space-y-1.5">
              <div className="flex justify-between">
                <span className="text-[#6E7B88]">{tr(lang, 'Compte :')}</span>
                <span className="text-[#E8EEF2]">{user.email}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#6E7B88]">{tr(lang, 'Nom :')}</span>
                <span className="text-[#E8EEF2]">{user.display_name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#6E7B88]">{tr(lang, 'ID Utilisateur :')}</span>
                <span className="text-[#8B98A4]">#{user.user_id}</span>
              </div>
            </div>

            <div className="flex flex-col sm:flex-row gap-2.5 pt-2">
              <button
                type="button"
                onClick={() => loadUserAndCoreData()}
                className="flex-1 py-2.5 bg-[#20C997] hover:bg-[#1AA67D] text-[#080C0F] font-semibold text-xs rounded-lg transition-colors flex items-center justify-center gap-1.5"
              >
                <RefreshCw className="w-4 h-4" />
                <span>{tr(lang, 'Actualiser mon statut')}</span>
              </button>
              <button
                type="button"
                onClick={handleLogout}
                className="flex-1 py-2.5 bg-[#172129] hover:bg-[#202A32] border border-white/10 text-[#E8EEF2] font-semibold text-xs rounded-lg transition-colors flex items-center justify-center gap-1.5"
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
  // Métriques d'une position Paper (mêmes formules que le tableau desktop) : réutilisées par la vue cartes mobile.
  const computePaperMetrics = (pos: PaperPosition) => {
    const entryVal = Number(pos.entry ?? pos.entry_price ?? 0);
    const liveSymPrice = livePrices[pos.symbol]?.price;
    const currVal = Number(liveSymPrice ?? pos.current_price ?? entryVal);
    const slVal = Number(pos.sl ?? 0);
    const tpVal = Number(pos.tp ?? 0);
    const qtyVal = Number(pos.qty ?? 0);
    const levVal = Math.max(1, Number(pos.leverage ?? 1));
    const marginVal = Number(pos.margin_used ?? (entryVal * qtyVal) / levVal);
    const rawDiff = pos.side === 'BUY' ? currVal - entryVal : entryVal - currVal;
    const upnl =
      liveSymPrice && entryVal > 0 && qtyVal > 0 ? rawDiff * qtyVal : Number(pos.unrealized_pnl ?? pos.pnl_usdt ?? 0);
    const upnlPct = marginVal > 0 ? (upnl / marginVal) * 100 : Number(pos.unrealized_pnl_pct ?? pos.pnl_pct ?? 0);
    return { entryVal, currVal, slVal, tpVal, marginVal, upnl, upnlPct };
  };

  const navItems = [
    { id: 'intelligence', label: tr(lang, 'Market Intelligence'), icon: Activity, group: 'overview' },
    { id: 'paper', label: tr(lang, 'Paper Trading'), icon: Layers, count: openPaper.length, group: 'trading' },
    { id: 'alerts', label: tr(lang, 'Alertes & Watchlist'), icon: Bell, count: alerts.length, group: 'monitoring' },
    {
      id: 'safety',
      group: 'trading',
      label: tr(lang, 'Auto-Trade & Safety'),
      icon: ShieldCheck,
      warn: tradingCfg?.safety_lock || tradingCfg?.safety_warn,
      apiConnected: Boolean(tradingCfg?.credentials_valid),
    },
    { id: 'strategy_lab', label: tr(lang, 'Strategy Lab (Backtest)'), icon: FlaskConical, group: 'research' },
    { id: 'history', label: tr(lang, 'Historique & Journal'), icon: BookOpen, group: 'monitoring' },
    { id: 'account', label: tr(lang, 'Compte, Plans & PIN'), icon: CreditCard, group: 'system' },
    { id: 'terms', label: tr(lang, 'Termes & Conditions (CGU)'), icon: Shield, group: 'system' },
    ...(isAdminUser
      ? [
          { id: 'users_intelligence', label: tr(lang, 'Utilisateurs 360° (Admin)'), icon: Users, group: 'admin' },
          { id: 'admin', label: tr(lang, 'Admin & Log Doctor'), icon: Terminal, group: 'admin' },
        ]
      : []),
  ];

  // Sidebar desktop : regroupement par domaine (même liste d'onglets, aucune route supprimée)
  const navGroupDefs: Array<{ id: string; label: string }> = [
    { id: 'overview', label: tr(lang, 'Vue d’ensemble', 'Overview') },
    { id: 'research', label: tr(lang, 'Recherche', 'Research') },
    { id: 'trading', label: 'Trading' },
    { id: 'monitoring', label: tr(lang, 'Suivi', 'Monitoring') },
    { id: 'system', label: tr(lang, 'Système', 'System') },
    { id: 'admin', label: 'Admin' },
  ];
  const navGroups = navGroupDefs
    .map((g) => ({ ...g, items: navItems.filter((it: any) => it.group === g.id) }))
    .filter((g) => g.items.length > 0);

  // Grouped Mobile Hub structure (4 primary tabs on mobile + sub-switcher strip)
  const mobileHubGroups: Array<{
    hubId: string;
    label: string;
    icon: any;
    tabs: Array<{ id: ActiveTab; label: string; icon: any; count?: number }>;
    hasSafetyDot?: boolean;
    apiConnected?: boolean;
  }> = [
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
      // Pastille d'état Auto-Trade : verte si les clés API Binance sont valides, rouge sinon.
      hasSafetyDot: true,
      apiConnected: Boolean(tradingCfg?.credentials_valid),
      tabs: [
        { id: 'paper' as ActiveTab, label: tr(lang, 'Paper Trading'), icon: Layers, count: openPaper.length },
        { id: 'safety' as ActiveTab, label: tr(lang, 'Auto-Trade & Safety'), icon: ShieldCheck },
        { id: 'strategy_lab' as ActiveTab, label: tr(lang, 'Strategy Lab (Backtest)'), icon: FlaskConical },
      ],
    },
    {
      hubId: 'tracking',
      label: tr(lang, 'Suivi'),
      icon: BookOpen,
      tabs: [
        { id: 'history' as ActiveTab, label: tr(lang, 'Historique & Journal'), icon: BookOpen },
        { id: 'account' as ActiveTab, label: tr(lang, 'Compte, Plans & PIN'), icon: CreditCard },
        { id: 'terms' as ActiveTab, label: tr(lang, 'Termes & Conditions (CGU)'), icon: Shield },
      ],
    },
    ...(isAdminUser
      ? [
          {
            hubId: 'admin_hub',
            label: 'Admin',
            icon: FlaskConical,
            tabs: [
              { id: 'users_intelligence' as ActiveTab, label: tr(lang, 'Utilisateurs 360° (Admin)'), icon: Users },
              { id: 'admin' as ActiveTab, label: tr(lang, 'Admin & Log Doctor'), icon: Terminal },
            ],
          },
        ]
      : [
          {
            hubId: 'account_hub',
            label: tr(lang, 'Compte'),
            icon: CreditCard,
            tabs: [
              { id: 'account' as ActiveTab, label: tr(lang, 'Compte, Plans & PIN'), icon: CreditCard },
              { id: 'terms' as ActiveTab, label: tr(lang, 'Termes & Conditions (CGU)'), icon: Shield },
            ],
          },
        ]),
  ];
  const currentMobileHub =
    mobileHubGroups.find((g) => g.tabs.some((t) => t.id === activeTab)) || mobileHubGroups[0];
  lastTabByHubRef.current[currentMobileHub.hubId] = activeTab;

  // En-tête de page contextuel : où suis-je / que fait cet outil. Onglets sans entrée = en-tête propre.
  const pageMeta: Partial<Record<ActiveTab, { title: string; description: string }>> = {
    intelligence: {
      title: tr(lang, 'Market Intelligence'),
      description: tr(
        lang,
        'Analyse du symbole sélectionné : Teddy Score, alignement multi-timeframes, niveaux SL/TP et scan des marchés documentés.',
        'Analysis of the selected symbol: Teddy Score, multi-timeframe alignment, SL/TP levels and a scan of the documented markets.'
      ),
    },
    paper: {
      title: 'Paper Trading',
      description: tr(
        lang,
        'Portefeuille virtuel : ouvrez et suivez des positions simulées, sans risque réel.',
        'Virtual portfolio: open and track simulated positions with no real risk.'
      ),
    },
    alerts: {
      title: tr(lang, 'Alertes & Watchlist'),
      description: tr(
        lang,
        'Créez des alertes de prix et suivez vos alertes actives.',
        'Create price alerts and track your active alerts.'
      ),
    },
    safety: {
      title: tr(lang, 'Auto-Trade & Safety'),
      description: tr(
        lang,
        'Configuration de l’AutoTrade, clés Binance, état de sécurité, ordre live manuel, positions et ordres ouverts.',
        'AutoTrade configuration, Binance keys, safety state, manual live order, open positions and orders.'
      ),
    },
    strategy_lab: {
      title: 'Strategy Lab',
      description: tr(
        lang,
        'Configurez, testez et comparez des stratégies sur données historiques ; l’Optimization Lab se trouve dans l’onglet du même nom.',
        'Configure, test and compare strategies on historical data; the Optimization Lab is in the tab of the same name.'
      ),
    },
    history: {
      title: tr(lang, 'Historique & Journal'),
      description: tr(
        lang,
        'Historique des signaux validés et journal des décisions du moteur.',
        'History of validated signals and the engine decision journal.'
      ),
    },
    account: {
      title: tr(lang, 'Compte, Plans & PIN'),
      description: tr(
        lang,
        'Plan, code promo, paiement Binance Pay, code PIN de sécurité et support.',
        'Plan, promo code, Binance Pay, security PIN and support.'
      ),
    },
    admin: {
      title: tr(lang, 'Admin & Log Doctor'),
      description: tr(
        lang,
        'Utilisateurs et quotas, audit de sécurité, diffusion, diagnostic des logs et maintenance.',
        'Users and quotas, security audit, broadcast, log diagnostics and maintenance.'
      ),
    },
  };
  const currentPageMeta = pageMeta[activeTab];
  const currentNavIcon: any = (navItems as any[]).find((it) => it.id === activeTab)?.icon;
  const CurrentNavIcon = currentNavIcon as React.ComponentType<{ className?: string }> | undefined;

  return (
    <div className="min-h-screen bg-[#080C0F] text-[#E8EEF2] flex flex-col md:flex-row">
      {/* Left Single Navigation Sidebar (Hidden on mobile, sticky fixed-height sidebar on desktop) */}
      <aside className="hidden md:flex w-64 shrink-0 border-r border-white/[0.07] bg-[#0D1318] flex-col justify-between md:sticky md:top-0 md:h-screen md:overflow-y-auto">
        <div>
          {/* Brand Logo */}
          <div className="h-16 px-5 border-b border-white/[0.07] flex items-center justify-between">
            <button
              onClick={() => {
                setViewMode('landing');
              }}
              className="flex items-center gap-2.5 text-left group"
            >
              <div className="w-8 h-8 rounded-lg bg-[#20C997]/15 border border-[#20C997]/40 flex items-center justify-center text-[#20C997] font-display font-bold">
                B
              </div>
              <div>
                <div className="font-display font-bold text-sm tracking-tight text-[#E8EEF2] group-hover:text-[#20C997] transition-colors">
                  BITSURE TEDDY
                </div>
                <div className="text-[10px] font-mono-tabular text-[#6E7B88]">QUANT ENGINE v2.0</div>
              </div>
            </button>
          </div>

          {/* Primary Navigation Items */}
          <nav className="px-2 pb-2" aria-label={tr(lang, 'Navigation principale', 'Main navigation')}>
            {navGroups.map((group) => (
              <div key={group.id}>
                <div className="bs-nav-group">{group.label}</div>
                <div className="space-y-0.5">
            {group.items.map((item: any) => {
              const Icon = item.icon;
              const active = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  aria-current={active ? 'page' : undefined}
                  onClick={() => {
                    setActiveTab(item.id as ActiveTab);
                    setMobileMenuOpen(false);
                  }}
                  className={`w-full px-3 py-2 rounded-md text-xs font-medium flex items-center justify-between transition-colors border-l-2 ${
                    active
                      ? 'bg-[#172129] text-[#E8EEF2] border-[#20C997]'
                      : 'text-[#8B98A4] hover:text-[#E8EEF2] hover:bg-white/[0.04] border-transparent'
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
                            ? 'bg-[#20C997]/15 text-[#20C997] border-[#20C997]/40'
                            : 'bg-[#F04438]/15 text-[#F97066] border-[#F04438]/40'
                        }`}
                      >
                        <span
                          className={`w-1.5 h-1.5 rounded-full ${
                            item.apiConnected ? 'bg-[#20C997] animate-pulse' : 'bg-[#F04438]'
                          }`}
                        />
                        {item.apiConnected ? 'API OK' : 'API OFF'}
                      </span>
                    )}
                    {item.count !== undefined && item.count > 0 && (
                      <span className="font-mono-tabular text-[11px] text-[#8B98A4]">{item.count}</span>
                    )}
                    {item.warn && <span className="w-2 h-2 rounded-full bg-[#D6A84F]" title="Avertissement ou Safety Lock actif" />}
                  </div>
                </button>
              );
            })}
                </div>
              </div>
            ))}
          </nav>

          {/* Watchlist Quick Selector */}
          <div className="px-4 pt-4 pb-2">
            <div className="flex items-center justify-between text-[11px] font-mono-tabular uppercase tracking-wider text-[#6E7B88] mb-2">
              <span>{tr(lang, 'Marchés Documentés')}</span>
              <span className="inline-flex items-center gap-1 text-[9px] text-[#20C997]">
                <span className="w-1.5 h-1.5 rounded-full bg-[#20C997] animate-ping" />
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
                        ? 'bg-[#172129] text-[#E8EEF2] font-medium'
                        : 'text-[#8B98A4] hover:bg-white/[0.03] hover:text-[#E8EEF2]'
                    }`}
                  >
                    <span className="font-mono-tabular">{s.id}</span>
                    {tick?.price ? (
                      <span
                        className={`font-mono-tabular text-[11px] font-semibold transition-colors ${
                          flash === 'up'
                            ? 'text-[#20C997]'
                            : flash === 'down'
                            ? 'text-[#F04438]'
                            : tick.direction === 'up'
                            ? 'text-[#32D583]'
                            : tick.direction === 'down'
                            ? 'text-[#F97066]'
                            : 'text-[#E8EEF2]'
                        }`}
                      >
                        {tick.price.toLocaleString('en-US', {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 2,
                        })}
                      </span>
                    ) : (
                      <ChevronRight className="w-3.5 h-3.5 text-[#6E7B88]" />
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Bottom User Profile */}
        <div className="p-3.5 border-t border-white/[0.07] bg-[#080C0F]/60 space-y-3">
          {user && (
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-[#E8EEF2] truncate">{user.display_name}</span>
                <span className="text-[10px] font-mono-tabular uppercase px-1.5 py-0.5 rounded bg-[#20C997]/15 text-[#20C997] border border-[#20C997]/30">
                  {user.role}
                </span>
              </div>
              <div className="text-[11px] text-[#6E7B88] font-mono-tabular flex items-center justify-between">
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
              className="flex-1 py-1.5 text-xs text-[#8B98A4] hover:text-[#E8EEF2] border border-white/10 rounded hover:bg-white/[0.04] transition-colors"
            >
              {tr(lang, 'Présentation')}
            </button>
            <button
              onClick={handleLogout}
              className="px-3 py-1.5 text-xs text-[#F97066] hover:bg-[#F04438]/15 border border-[#F04438]/30 rounded transition-colors flex items-center gap-1"
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
        <header className="min-h-14 py-2 px-3 sm:px-6 border-b border-white/[0.07] bg-[#0D1318]/95 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-1.5 sm:gap-3 flex-wrap">
            {/* Compact Brand Badge on Mobile */}
            <button
              type="button"
              onClick={() => setViewMode('landing')}
              className="md:hidden w-8 h-8 rounded-lg bg-[#20C997]/15 border border-[#20C997]/40 flex items-center justify-center text-[#20C997] font-display font-bold text-xs shrink-0"
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
              className="px-2 sm:px-3 py-1.5 bg-[#0D1318] border border-white/15 rounded-lg text-xs font-mono-tabular font-semibold text-[#E8EEF2]"
            >
              {SYMBOLS.map((s) => (
                <option key={s.id} value={s.id}>
                  {lang === 'en' && s.labelEn ? s.labelEn : s.label}
                </option>
              ))}
            </select>

            <div className="flex items-center bg-[#0D1318] border border-white/10 rounded-lg p-0.5 overflow-x-auto max-w-full">
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
                      ? 'bg-[#20C997] text-[#080C0F] font-semibold'
                      : 'text-[#8B98A4] hover:text-[#E8EEF2]'
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
              className="hidden sm:block px-2.5 sm:px-3 py-1.5 bg-[#0D1318] border border-white/10 rounded-lg text-xs text-[#E8EEF2]"
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
              className="px-2 sm:px-3 py-1.5 bg-[#172129] hover:bg-[#202A32] border border-white/10 rounded-lg text-xs text-[#E8EEF2] flex items-center gap-1.5 transition-colors"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loadingAnalysis ? 'animate-spin text-[#20C997]' : ''}`} />
              <span className="hidden sm:inline">{tr(lang, 'Actualiser')}</span>
            </button>
          </div>

          <div className="flex items-center gap-2 sm:gap-3 text-xs">
            {/* Live Binance Ticker Strip */}
            <div className="hidden xl:flex items-center gap-2 bg-[#0D1318] border border-white/[0.08] px-3 py-1 rounded-lg font-mono-tabular">
              <span
                className="inline-flex items-center gap-1.5 pr-2 border-r border-white/10 text-[10px] font-bold text-[#20C997]"
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
                <span className="w-2 h-2 rounded-full bg-[#20C997] animate-pulse" />
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
                        ? 'bg-[#20C997]/20 text-[#20C997]'
                        : fl === 'down'
                        ? 'bg-[#F04438]/20 text-[#F04438]'
                        : 'hover:bg-white/[0.04]'
                    }`}
                  >
                    <span className="text-[#8B98A4] font-semibold">{symObj.id}</span>
                    <span
                      className={`font-bold ${
                        t?.direction === 'up'
                          ? 'text-[#20C997]'
                          : t?.direction === 'down'
                          ? 'text-[#F04438]'
                          : 'text-[#E8EEF2]'
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
                          t.change24h >= 0 ? 'text-[#20C997]' : 'text-[#F04438]'
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
              <div className="hidden lg:flex items-center gap-4 font-mono-tabular bg-[#0D1318] border border-white/[0.07] px-3.5 py-1.5 rounded-lg">
                <span className="text-[#8B98A4]">
                  {lang === 'en' ? 'Paper Equity:' : 'Équité Paper :'}{' '}
                  <strong className="text-[#E8EEF2]">
                    {Number(paperStats.equity ?? 0).toLocaleString('en-US', {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}{' '}
                    USDT
                  </strong>
                </span>
                <span className={(paperStats.total_pnl ?? 0) >= 0 ? 'text-[#20C997]' : 'text-[#F04438]'}>
                  PnL : {(paperStats.total_pnl ?? 0) >= 0 ? '+' : ''}
                  {Number(paperStats.total_pnl ?? 0).toFixed(2)} USDT
                </span>
              </div>
            )}

            {isAdminUser && (
              <button
                type="button"
                onClick={() => setActiveTab('users_intelligence')}
                className={`px-2.5 py-1.5 rounded-lg border text-xs font-semibold flex items-center gap-1.5 transition-colors ${
                  activeTab === 'users_intelligence'
                    ? 'bg-[#20C997] text-[#080C0F] border-[#20C997]'
                    : 'bg-[#20C997]/15 hover:bg-[#20C997]/25 text-[#20C997] border-[#20C997]/40'
                }`}
                title="Dossier Utilisateurs 360° (IP, Appareils, Localisation, CGU)"
              >
                <Users className="w-3.5 h-3.5 shrink-0" />
                <span className="hidden sm:inline">{tr(lang, 'Utilisateurs 360°')}</span>
              </button>
            )}

            <button
              type="button"
              onClick={() => setActiveTab('terms')}
              className={`px-2.5 py-1.5 rounded-lg border text-xs font-semibold flex items-center gap-1.5 transition-colors ${
                activeTab === 'terms'
                  ? 'bg-[#D6A84F] text-[#080C0F] border-[#D6A84F]'
                  : 'bg-[#0D1318] hover:bg-white/[0.05] text-[#E2BC6A] border-[#D6A84F]/40'
              }`}
              title="Termes & Conditions d'Utilisation (CGU)"
            >
              <Shield className="w-3.5 h-3.5 shrink-0" />
              <span className="hidden sm:inline">{tr(lang, 'CGU')}</span>
            </button>

            <button
              onClick={() => {
                handleToggleLang();
                runAnalysis(selectedSymbol, selectedTimeframe, selectedStyle, true);
                runMultiScan(selectedTimeframe, selectedStyle, false);
              }}
              title={lang === 'en' ? 'Switch language (FR / EN)' : 'Changer de langue (FR / EN)'}
              className="px-2.5 py-1.5 bg-[#0D1318] border border-white/10 rounded-lg font-mono-tabular uppercase text-[#E8EEF2] hover:border-[#20C997]/50 flex items-center gap-1"
            >
              <span className={lang === 'fr' ? 'text-[#20C997] font-bold' : 'text-[#6E7B88]'}>FR</span>
              <span className="text-[#6E7B88]">/</span>
              <span className={lang === 'en' ? 'text-[#20C997] font-bold' : 'text-[#6E7B88]'}>EN</span>
            </button>

            <button
              onClick={handleLogout}
              className="md:hidden p-1.5 bg-[#F04438]/15 border border-[#F04438]/30 rounded-lg text-[#F97066]"
              title={tr(lang, 'Se déconnecter')}
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          </div>
        </header>

        {/* Ticker compact (écrans < xl) : prix live réels, tap = ouvrir l'analyse du symbole */}
        <div className="xl:hidden border-b border-[#202A32] bg-[#0D1318] overflow-x-auto" aria-label={tr(lang, 'Marchés en direct', 'Live markets')}>
          <div className="flex items-stretch gap-1 px-3 py-1.5 min-w-max">
            {SYMBOLS.map((symObj) => {
              const t = livePrices[symObj.id];
              const hist = priceHistoryRef.current[symObj.id] || [];
              const up = (t?.change24h ?? 0) >= 0;
              return (
                <button
                  key={symObj.id}
                  type="button"
                  onClick={() => {
                    setSelectedSymbol(symObj.id);
                    setActiveTab('intelligence');
                    runAnalysis(symObj.id, selectedTimeframe, selectedStyle);
                  }}
                  aria-label={`${symObj.id} ${t?.price ?? ''}`}
                  className={`min-h-11 px-2.5 rounded-md flex items-center gap-2 font-mono-tabular text-xs border ${
                    selectedSymbol === symObj.id ? 'bg-[#172129] border-[#202A32]' : 'border-transparent hover:bg-white/[0.04]'
                  }`}
                >
                  <span className="text-[#8B98A4] font-semibold">{symObj.id.replace('USDT', '')}</span>
                  <span className="text-[#E8EEF2] font-semibold">
                    {t?.price ? t.price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'}
                  </span>
                  {t?.change24h !== undefined && (
                    <span className={up ? 'text-[#32D583]' : 'text-[#F97066]'}>
                      {up ? '+' : ''}
                      {t.change24h.toFixed(2)}%
                    </span>
                  )}
                  <Sparkline values={hist} tone={hist.length > 1 && hist[hist.length - 1] < hist[0] ? 'negative' : 'positive'} label={`${symObj.id} ${tr(lang, 'session', 'session')}`} />
                </button>
              );
            })}
          </div>
        </div>

        {/* Mobile Consolidated Sub-Tab Pill Bar (Shown on mobile to switch cleanly within the active Hub) */}
        {currentMobileHub && currentMobileHub.tabs.length > 1 && (
          <div className="md:hidden px-3 pt-2.5">
            <div className="flex items-center justify-between mb-1.5 px-1">
              <span className="text-[10px] font-mono-tabular uppercase tracking-wider text-[#6E7B88]">
                {lang === 'en' ? `Section: ${currentMobileHub.label}` : `Pôle : ${currentMobileHub.label}`}
              </span>
              <span className="text-[10px] font-mono-tabular text-[#20C997]">
                {currentMobileHub.tabs.findIndex((t) => t.id === activeTab) + 1}/{currentMobileHub.tabs.length}
              </span>
            </div>
            <div className="bl-subtabs">
              {currentMobileHub.tabs.map((subTab) => {
                const SubIcon = subTab.icon;
                const isSubActive = activeTab === subTab.id;
                return (
                  <button
                    key={subTab.id}
                    type="button"
                    aria-current={isSubActive ? 'page' : undefined}
                    onClick={() => setActiveTab(subTab.id)}
                    className={`py-2 px-3 min-h-11 rounded-md text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors border border-transparent ${
                      isSubActive
                        ? 'bg-[#172129] text-[#E8EEF2] border border-[#20C997]'
                        : 'text-[#8B98A4] hover:text-[#E8EEF2]'
                    }`}
                  >
                    <SubIcon className="w-3.5 h-3.5 shrink-0" />
                    <span>{subTab.label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Toast Notification Banner */}
        {(toast || Object.keys(pendingActions).length > 0) && (
          <div
            role="status"
            aria-live="polite"
            className="fixed z-[100] top-[max(0.5rem,env(safe-area-inset-top))] inset-x-2 sm:inset-x-auto sm:right-4 sm:top-4 sm:w-[26rem] max-w-full space-y-2 pointer-events-none"
          >
            {Object.keys(pendingActions).length > 0 && (
              <div className="pointer-events-auto rounded-lg bg-[#080C0F]">
                <div className="px-4 py-2.5 rounded-lg border text-xs flex items-center gap-2 bg-[#4EA1FF]/15 border-[#4EA1FF]/40 text-[#6BB1FF]">
                  <RefreshCw className="w-3.5 h-3.5 animate-spin shrink-0" />
                  <span>
                    {Object.values(pendingActions)[0]}
                    {Object.keys(pendingActions).length > 1 ? ` (+${Object.keys(pendingActions).length - 1})` : ''}
                  </span>
                </div>
              </div>
            )}
            {toast && (
              <div role={toast.type === 'error' ? 'alert' : undefined} className="pointer-events-auto rounded-lg bg-[#080C0F]">
                <div
                  className={`px-4 py-2.5 rounded-lg border text-xs flex items-center justify-between gap-3 ${
                    toast.type === 'success'
                      ? 'bg-[#20C997]/15 border-[#20C997]/40 text-[#32D583]'
                      : toast.type === 'error'
                      ? 'bg-[#F04438]/15 border-[#F04438]/40 text-[#F97066]'
                      : 'bg-[#4EA1FF]/15 border-[#4EA1FF]/40 text-[#6BB1FF]'
                  }`}
                >
                  <span className="break-words min-w-0">
                    <strong className="font-mono-tabular uppercase text-[10px] tracking-wider mr-1.5">
                      {toast.type === 'success'
                        ? tr(lang, 'Succès', 'Success')
                        : toast.type === 'error'
                        ? tr(lang, 'Échec', 'Failed')
                        : 'Info'}
                    </strong>
                    {toast.text}
                  </span>
                  <button
                    onClick={() => setToast(null)}
                    aria-label={tr(lang, 'Fermer la notification', 'Dismiss notification')}
                    className="opacity-70 hover:opacity-100 shrink-0 min-w-6 min-h-6"
                  >
                    ✕
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Main Scrollable Content */}
        <main className="p-3 sm:p-6 space-y-6 max-w-[1600px] w-full mx-auto">
          {currentPageMeta && (
            <PageHeader
              icon={CurrentNavIcon ? <CurrentNavIcon className="w-5 h-5 text-[#8B98A4] shrink-0" /> : undefined}
              title={currentPageMeta.title}
              description={currentPageMeta.description}
              status={
                activeTab === 'safety' && tradingCfg ? (
                  <StatusBadge tone={tradingCfg.credentials_valid ? 'positive' : 'negative'} dot>
                    {tradingCfg.credentials_valid ? 'API OK' : 'API OFF'}
                  </StatusBadge>
                ) : undefined
              }
            />
          )}
          {/* =========================================================
              TAB 1: MARKET INTELLIGENCE & TEDDY SCORE WORKSPACE
             ========================================================= */}
          {activeTab === 'intelligence' && (
            <>
              {/* État du système : uniquement des états réels (flux WS, config AutoTrade, positions Paper, alertes) */}
              <div className="flex flex-wrap items-center gap-2 -mt-2" aria-label={tr(lang, 'État du système', 'System status')}>
                <StatusBadge tone={wsConnected ? 'positive' : 'warning'} dot>
                  {tr(lang, 'Flux prix', 'Price feed')} : {wsConnected ? (lang === 'en' ? 'CONNECTED' : 'CONNECTÉ') : (lang === 'en' ? 'DISCONNECTED' : 'DÉCONNECTÉ')}
                </StatusBadge>
                {tradingCfg && (
                  <button type="button" onClick={() => setActiveTab('safety')} className="rounded focus-visible:outline-offset-2">
                    <StatusBadge
                      tone={tradingCfg.safety_lock ? 'negative' : tradingCfg.enabled ? 'positive' : 'neutral'}
                      dot
                    >
                      AutoTrade : {tradingCfg.safety_lock ? 'SAFE MODE' : tradingCfg.enabled ? 'RUNNING' : 'PAUSED'}
                      {tradingCfg.testnet ? ' · TESTNET' : ''}
                    </StatusBadge>
                  </button>
                )}
                {tradingCfg && tradingCfg.engine_online === false && (
                  <StatusBadge tone="warning" dot>
                    {tr(lang, 'Moteur hors ligne', 'Engine offline')}
                  </StatusBadge>
                )}
                <button type="button" onClick={() => setActiveTab('paper')} className="rounded">
                  <StatusBadge tone={openPaper.length > 0 ? 'info' : 'neutral'}>
                    Paper : {openPaper.length} {tr(lang, 'position(s)', 'position(s)')}
                  </StatusBadge>
                </button>
                <button type="button" onClick={() => setActiveTab('alerts')} className="rounded">
                  <StatusBadge tone={alerts.length > 0 ? 'info' : 'neutral'}>
                    {tr(lang, 'Alertes', 'Alerts')} : {alerts.length}
                  </StatusBadge>
                </button>
              </div>

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
                      className={`bg-[#0D1318] border rounded-xl p-5 space-y-2 transition-colors duration-300 ${
                        flash === 'up'
                          ? 'border-[#20C997]/60 bg-[#20C997]/[0.05]'
                          : flash === 'down'
                          ? 'border-[#F04438]/60 bg-[#F04438]/[0.05]'
                          : 'border-white/[0.07]'
                      }`}
                    >
                      <div className="flex items-center justify-between text-xs text-[#8B98A4]">
                        <span className="flex items-center gap-1.5">
                          <span>{lang === 'en' ? `Live Price (${symKey})` : `Cours Temps Réel (${symKey})`}</span>
                          <span
                            className="w-2 h-2 rounded-full bg-[#20C997] animate-ping"
                            title={lang === 'en' ? 'Live feed' : 'Flux en direct'}
                          />
                        </span>
                        <span className="font-mono-tabular text-[#20C997]">
                          {analysis?.market_status?.is_open ? tr(lang, '● LIVE 24/7') : tr(lang, '○ FERMÉ')}
                        </span>
                      </div>
                      <div className="flex items-baseline justify-between gap-2">
                        <div
                          className={`font-mono-tabular text-2xl font-bold transition-colors ${
                            flash === 'up'
                              ? 'text-[#20C997]'
                              : flash === 'down'
                              ? 'text-[#F04438]'
                              : liveTick?.direction === 'up'
                              ? 'text-[#32D583]'
                              : liveTick?.direction === 'down'
                              ? 'text-[#F97066]'
                              : 'text-[#E8EEF2]'
                          }`}
                        >
                          {displayPrice
                            ? displayPrice.toLocaleString('en-US', {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2,
                              })
                            : '—'}{' '}
                          <span className="text-xs font-normal text-[#6E7B88]">USD</span>
                        </div>
                        {liveTick?.change24h !== undefined && (
                          <span
                            className={`font-mono-tabular text-xs font-semibold px-1.5 py-0.5 rounded ${
                              liveTick.change24h >= 0
                                ? 'bg-[#20C997]/15 text-[#20C997]'
                                : 'bg-[#F04438]/15 text-[#F04438]'
                            }`}
                          >
                            {liveTick.change24h >= 0 ? '+' : ''}
                            {liveTick.change24h.toFixed(2)}%
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-[#6E7B88] font-mono-tabular flex items-center justify-between">
                        <span>
                          ATR(14) : {ind.atr ? ind.atr.toFixed(2) : '—'} • {(analysis?.asset_class || 'crypto').toUpperCase()}
                        </span>
                        {liveTick?.bid && liveTick?.ask && (
                          <span className="text-[10px] text-[#8B98A4]">
                            B:{liveTick.bid.toFixed(1)} / A:{liveTick.ask.toFixed(1)}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })()}

                {/* KPI 2: Signal & Teddy Score */}
                <div className="bg-[#0D1318] border border-white/[0.07] rounded-xl p-5 space-y-2">
                  <div className="flex items-center justify-between text-xs text-[#8B98A4]">
                    <span className="inline-flex items-center gap-1">{tr(lang, 'Signal & Teddy Score')} <InfoTip term="teddy_score" lang={lang} /></span>
                    <span className="font-mono-tabular text-[#8B98A4]">
                      {lang === 'en' ? 'Confidence:' : 'Confiance :'} {analysis?.confidence || '—'}
                    </span>
                  </div>
                  <div className="flex items-baseline gap-3">
                    <span
                      className={`font-display text-2xl font-bold ${
                        analysis?.signal === 'BUY'
                          ? 'text-[#20C997]'
                          : analysis?.signal === 'SELL'
                          ? 'text-[#F04438]'
                          : 'text-[#D6A84F]'
                      }`}
                    >
                      {analysis?.signal || 'WAIT'}
                    </span>
                    <span className="font-mono-tabular text-xl font-semibold text-[#E8EEF2]">
                      {analysis?.teddy_score ?? 0} <span className="text-xs text-[#6E7B88]">/ 100</span>
                    </span>
                  </div>
                  <div className="w-full h-1.5 bg-[#080C0F] rounded-full overflow-hidden">
                    <div
                      className="h-full bg-[#20C997] transition-all"
                      style={{ width: `${Math.min(100, Math.max(8, analysis?.teddy_score || 0))}%` }}
                    />
                  </div>
                </div>

                {/* KPI 3: Multi-Timeframe Hierarchy */}
                <div className="bg-[#0D1318] border border-white/[0.07] rounded-xl p-5 space-y-2">
                  <div className="flex items-center justify-between text-xs text-[#8B98A4]">
                    <span>{tr(lang, 'Alignement Multi-Timeframes')}</span>
                    <span className="font-mono-tabular text-[#D6A84F]">
                      {tfAlign.status || 'NEUTRAL'} ({tfAlign.modifier >= 0 ? `+${tfAlign.modifier || 0}` : tfAlign.modifier} pts)
                    </span>
                  </div>
                  <div className="grid grid-cols-3 gap-2 pt-1 font-mono-tabular text-xs">
                    {(['1h', '4h', '1d'] as const).map((k) => {
                      const val = tfTrends[k] || 'NEUTRE';
                      return (
                        <div key={k} className="bg-[#080C0F] border border-white/[0.06] rounded px-2.5 py-1.5 text-center">
                          <div className="text-[10px] text-[#6E7B88] uppercase">{k}</div>
                          <div
                            className={`font-semibold text-[11px] ${
                              val === 'HAUSSIER' || val === 'BULLISH'
                                ? 'text-[#20C997]'
                                : val === 'BAISSIER' || val === 'BEARISH'
                                ? 'text-[#F04438]'
                                : 'text-[#8B98A4]'
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
                <div className="bg-[#0D1318] border border-white/[0.07] rounded-xl p-5 space-y-2">
                  <div className="flex items-center justify-between text-xs text-[#8B98A4]">
                    <span>{tr(lang, 'Taille Position Recommandée')}</span>
                    <span className="font-mono-tabular text-[#20C997]">
                      {lang === 'en' ? 'Risk' : 'Risque'} {analysis?.sizing_recommendation?.risk_pct || 1}%
                    </span>
                  </div>
                  <div className="font-mono-tabular text-2xl font-bold text-[#E8EEF2]">
                    {analysis?.sizing_recommendation?.position_size ?? 0}{' '}
                    <span className="text-xs font-normal text-[#6E7B88]">{tr(lang, 'unités')}</span>
                  </div>
                  <div className="text-xs text-[#6E7B88] font-mono-tabular">
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
                    <div className="bg-[#0D1318] border border-white/[0.07] rounded-lg p-3.5">
                      <div className="text-xs text-[#6E7B88] flex items-center gap-1">{tr(lang, 'RSI (14) & Stochastique')} <InfoTip term="rsi" lang={lang} /></div>
                      <div className="font-mono-tabular text-base font-semibold text-[#E8EEF2] mt-1">
                        {ind.rsi ? ind.rsi.toFixed(2) : '—'}
                      </div>
                      <div className="text-[11px] text-[#8B98A4] mt-0.5">
                        {ind.rsi > 70
                          ? tr(lang, 'Zone de surachat (>70)')
                          : ind.rsi < 30
                          ? tr(lang, 'Zone de survente (<30)')
                          : tr(lang, 'Zone neutre équilibrée')}
                      </div>
                      <div className="text-[11px] text-[#8B98A4] mt-0.5 font-mono-tabular">
                        Stoch %K: {ind.stoch_k != null ? Number(ind.stoch_k).toFixed(1) : '—'} / %D: {ind.stoch_d != null ? Number(ind.stoch_d).toFixed(1) : '—'}
                      </div>
                    </div>

                    <div className="bg-[#0D1318] border border-white/[0.07] rounded-lg p-3.5">
                      <div className="text-xs text-[#6E7B88]">MACD (12, 26, 9)</div>
                      <div className="font-mono-tabular text-base font-semibold text-[#E8EEF2] mt-1">
                        {ind.macd ? ind.macd.toFixed(2) : '—'}
                      </div>
                      <div className="text-[11px] text-[#8B98A4] mt-0.5 font-mono-tabular">
                        {tr(lang, 'Signal')}: {ind.macd_signal != null ? Number(ind.macd_signal).toFixed(2) : '—'} • Hist: {ind.macd_hist ? ind.macd_hist.toFixed(2) : '—'}
                      </div>
                    </div>

                    <div className="bg-[#0D1318] border border-white/[0.07] rounded-lg p-3.5">
                      <div className="text-xs text-[#6E7B88] flex items-center gap-1">{tr(lang, 'ADX (14) • Force Tendance')} <InfoTip term="adx" lang={lang} /></div>
                      <div className="font-mono-tabular text-base font-semibold text-[#E8EEF2] mt-1">
                        {ind.adx ? ind.adx.toFixed(2) : '—'}{' '}
                        <span className="text-xs text-[#20C997]">
                          {ind.adx_rising ? tr(lang, '↑ En hausse') : tr(lang, '↓ En repli')}
                        </span>
                      </div>
                      <div className="text-[11px] text-[#8B98A4] mt-0.5 font-mono-tabular">
                        +DI: {ind.plus_di ? ind.plus_di.toFixed(1) : '—'} / -DI: {ind.minus_di ? ind.minus_di.toFixed(1) : '—'}
                      </div>
                    </div>

                    <div className="bg-[#0D1318] border border-white/[0.07] rounded-lg p-3.5">
                      <div className="text-xs text-[#6E7B88]">{tr(lang, 'Support / Résistance (50p)')}</div>
                      <div className="font-mono-tabular text-sm font-semibold text-[#20C997] mt-1">
                        S: {ind.support ? ind.support.toLocaleString('en-US', { maximumFractionDigits: 2 }) : '—'}
                      </div>
                      <div className="font-mono-tabular text-sm font-semibold text-[#D6A84F]">
                        R: {ind.resistance ? ind.resistance.toLocaleString('en-US', { maximumFractionDigits: 2 }) : '—'}
                      </div>
                    </div>
                  </div>

                  {/* Autres indicateurs du bot : SMA 20/50, Bollinger, Volume, Fibonacci, Divergence RSI */}
                  <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-5 gap-4">
                    <div className="bg-[#0D1318] border border-white/[0.07] rounded-lg p-3.5">
                      <div className="text-xs text-[#6E7B88]">{tr(lang, 'Moyennes mobiles SMA 20 / 50')}</div>
                      <div className="font-mono-tabular text-sm font-semibold text-[#E8EEF2] mt-1">
                        {ind.sma20 != null ? Number(ind.sma20).toLocaleString('en-US', { maximumFractionDigits: 2 }) : '—'} /{' '}
                        {ind.sma50 != null ? Number(ind.sma50).toLocaleString('en-US', { maximumFractionDigits: 2 }) : '—'}
                      </div>
                      <div className="text-[11px] text-[#8B98A4] mt-0.5">
                        {ind.price > ind.sma20 && ind.sma20 > ind.sma50
                          ? tr(lang, 'Tendance haussière (prix > SMA20 > SMA50)')
                          : ind.price < ind.sma20 && ind.sma20 < ind.sma50
                          ? tr(lang, 'Tendance baissière (prix < SMA20 < SMA50)')
                          : tr(lang, 'Tendance neutre')}
                      </div>
                    </div>

                    <div className="bg-[#0D1318] border border-white/[0.07] rounded-lg p-3.5">
                      <div className="text-xs text-[#6E7B88]">{tr(lang, 'Bandes de Bollinger (20, 2σ)')}</div>
                      <div className="font-mono-tabular text-sm font-semibold text-[#D6A84F] mt-1">
                        {tr(lang, 'Haute')}: {ind.bb_upper != null ? Number(ind.bb_upper).toLocaleString('en-US', { maximumFractionDigits: 2 }) : '—'}
                      </div>
                      <div className="font-mono-tabular text-sm font-semibold text-[#20C997]">
                        {tr(lang, 'Basse')}: {ind.bb_lower != null ? Number(ind.bb_lower).toLocaleString('en-US', { maximumFractionDigits: 2 }) : '—'}
                      </div>
                    </div>

                    <div className="bg-[#0D1318] border border-white/[0.07] rounded-lg p-3.5">
                      <div className="text-xs text-[#6E7B88]">{tr(lang, 'Volume vs moyenne 20')}</div>
                      <div className="font-mono-tabular text-base font-semibold text-[#E8EEF2] mt-1">
                        {ind.volume && ind.volume_ma20 ? `${(ind.volume / ind.volume_ma20).toFixed(2)}x` : '—'}
                      </div>
                      <div className="text-[11px] text-[#8B98A4] mt-0.5 font-mono-tabular">
                        {tr(lang, 'Moyenne 20')}: {ind.volume_ma20 != null ? Number(ind.volume_ma20).toLocaleString('en-US', { maximumFractionDigits: 0 }) : '—'}
                      </div>
                    </div>

                    <div className="bg-[#0D1318] border border-white/[0.07] rounded-lg p-3.5">
                      <div className="text-xs text-[#6E7B88]">{tr(lang, 'Fibonacci (50 bougies)')}</div>
                      <div className="font-mono-tabular text-[11px] text-[#E8EEF2] mt-1 space-y-0.5">
                        <div>38.2% : {ind.fib?.['0.382'] != null ? Number(ind.fib['0.382']).toLocaleString('en-US', { maximumFractionDigits: 2 }) : '—'}</div>
                        <div>50.0% : {ind.fib?.['0.500'] != null ? Number(ind.fib['0.500']).toLocaleString('en-US', { maximumFractionDigits: 2 }) : '—'}</div>
                        <div>61.8% : {ind.fib?.['0.618'] != null ? Number(ind.fib['0.618']).toLocaleString('en-US', { maximumFractionDigits: 2 }) : '—'}</div>
                      </div>
                    </div>

                    <div className="bg-[#0D1318] border border-white/[0.07] rounded-lg p-3.5">
                      <div className="text-xs text-[#6E7B88]">{tr(lang, 'Divergence RSI / Prix')}</div>
                      <div
                        className={`font-mono-tabular text-sm font-semibold mt-1 ${
                          ind.rsi_divergence === 'bullish'
                            ? 'text-[#20C997]'
                            : ind.rsi_divergence === 'bearish'
                            ? 'text-[#F04438]'
                            : 'text-[#8B98A4]'
                        }`}
                      >
                        {ind.rsi_divergence === 'bullish'
                          ? tr(lang, 'Haussière')
                          : ind.rsi_divergence === 'bearish'
                          ? tr(lang, 'Baissière')
                          : tr(lang, 'Aucune')}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Right Column: Signal Explainability & Direct Paper Trade Box */}
                <div className="lg:col-span-4 space-y-6">
                  {/* Explainability Box */}
                  <div className="bg-[#0D1318] border border-white/[0.07] rounded-xl p-5 space-y-4">
                    <div className="flex items-center justify-between border-b border-white/[0.07] pb-3">
                      <h3 className="font-display font-semibold text-sm text-[#E8EEF2]">
                        {tr(lang, 'Diagnostic du Moteur Teddy')}
                      </h3>
                      <span className="font-mono-tabular text-xs text-[#8B98A4]">
                        {lang === 'en' ? 'Status:' : 'Statut :'} {analysis?.validation_status || '—'}
                      </span>
                    </div>

                    <div className="p-3.5 rounded-lg bg-[#080C0F] border border-white/[0.06] text-xs text-[#E8EEF2] leading-relaxed">
                      {analysis?.reason || tr(lang, 'Analyse en cours...')}
                    </div>

                    {/* Levels SL / TP1 / TP2 / RR */}
                    <div className="grid grid-cols-2 gap-2.5 text-xs font-mono-tabular">
                      <div className="p-2.5 rounded bg-[#080C0F] border border-white/[0.05]">
                        <div className="text-[#6E7B88] text-[10px] flex items-center gap-1">STOP LOSS (ATR) <InfoTip term="atr" lang={lang} /></div>
                        <div className="text-[#F04438] font-semibold mt-0.5">
                          {analysis?.sl ? analysis.sl.toLocaleString('en-US', { maximumFractionDigits: 2 }) : tr(lang, 'Non actif (WAIT)')}
                        </div>
                      </div>
                      <div className="p-2.5 rounded bg-[#080C0F] border border-white/[0.05]">
                        <div className="text-[#6E7B88] text-[10px]">TAKE PROFIT 1</div>
                        <div className="text-[#20C997] font-semibold mt-0.5">
                          {analysis?.tp1 ? analysis.tp1.toLocaleString('en-US', { maximumFractionDigits: 2 }) : tr(lang, 'Non actif (WAIT)')}
                        </div>
                      </div>
                      <div className="p-2.5 rounded bg-[#080C0F] border border-white/[0.05]">
                        <div className="text-[#6E7B88] text-[10px]">TAKE PROFIT 2</div>
                        <div className="text-[#32D583] font-semibold mt-0.5">
                          {analysis?.tp2 ? analysis.tp2.toLocaleString('en-US', { maximumFractionDigits: 2 }) : '—'}
                        </div>
                      </div>
                      <div className="p-2.5 rounded bg-[#080C0F] border border-white/[0.05]">
                        <div className="text-[#6E7B88] text-[10px]">RATIO R:R</div>
                        <div className="text-[#D6A84F] font-semibold mt-0.5">
                          {analysis?.rr_ratio ? `1 : ${analysis.rr_ratio.toFixed(2)}` : '—'}
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Quick Paper Order Ticket */}
                  <div className="bg-[#0D1318] border border-white/[0.07] rounded-xl p-5 space-y-4">
                    <div className="flex items-center justify-between border-b border-white/[0.07] pb-3">
                      <h3 className="font-display font-semibold text-sm text-[#E8EEF2]">
                        {tr(lang, 'Exécution Rapide Paper Trading')}
                      </h3>
                      <span className="font-mono-tabular text-xs text-[#20C997]">
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
                              ? 'bg-[#20C997] text-[#080C0F] border-[#20C997]'
                              : 'bg-[#080C0F] text-[#8B98A4] border-white/10'
                          }`}
                        >
                          LONG / BUY
                        </button>
                        <button
                          type="button"
                          onClick={() => setOrderSide('SELL')}
                          className={`py-2 rounded-lg font-semibold border transition-colors ${
                            orderSide === 'SELL'
                              ? 'bg-[#F04438] text-white border-[#F04438]'
                              : 'bg-[#080C0F] text-[#8B98A4] border-white/10'
                          }`}
                        >
                          SHORT / SELL
                        </button>
                      </div>

                      <div className="grid grid-cols-2 gap-2.5">
                        <div>
                          <label className="block text-[11px] text-[#8B98A4] mb-1">
                            {lang === 'en' ? 'Quantity' : 'Quantité'} ({selectedSymbol})
                          </label>
                          <input
                            type="number"
                            step="any"
                            value={orderQty}
                            onChange={(e) => setOrderQty(e.target.value)}
                            className="w-full px-2.5 py-1.5 bg-[#080C0F] border border-white/10 rounded font-mono-tabular text-[#E8EEF2]"
                            required
                          />
                        </div>
                        <div>
                          <label className="block text-[11px] text-[#8B98A4] mb-1">{tr(lang, 'Levier (1x–20x)')}</label>
                          <input
                            type="number"
                            min="1"
                            max="20"
                            value={orderLeverage}
                            onChange={(e) => setOrderLeverage(e.target.value)}
                            className="w-full px-2.5 py-1.5 bg-[#080C0F] border border-white/10 rounded font-mono-tabular text-[#E8EEF2]"
                            required
                          />
                        </div>
                      </div>

                      <div className="grid grid-cols-2 gap-2.5">
                        <div>
                          <label className="block text-[11px] text-[#8B98A4] mb-1">Stop Loss (SL)</label>
                          <input
                            type="number"
                            step="any"
                            value={orderSL}
                            onChange={(e) => setOrderSL(e.target.value)}
                            className="w-full px-2.5 py-1.5 bg-[#080C0F] border border-white/10 rounded font-mono-tabular text-[#F04438]"
                            required
                          />
                        </div>
                        <div>
                          <label className="block text-[11px] text-[#8B98A4] mb-1">Take Profit (TP)</label>
                          <input
                            type="number"
                            step="any"
                            value={orderTP}
                            onChange={(e) => setOrderTP(e.target.value)}
                            className="w-full px-2.5 py-1.5 bg-[#080C0F] border border-white/10 rounded font-mono-tabular text-[#20C997]"
                            required
                          />
                        </div>
                      </div>

                      <button
                        type="submit"
                        disabled={isPending('paper-open')}
                        className="w-full py-2.5 bg-[#20C997] hover:bg-[#1AA67D] text-[#080C0F] font-semibold rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {isPending('paper-open')
                          ? lang === 'en'
                            ? 'Processing…'
                            : 'Traitement…'
                          : lang === 'en'
                          ? `Open Paper Position (${selectedSymbol})`
                          : `Ouvrir Position Paper (${selectedSymbol})`}
                      </button>
                    </form>
                  </div>
                </div>
              </div>

              {/* Multi-Symbol Scanner Section */}
              <div className="bg-[#0D1318] border border-white/[0.07] rounded-xl p-4 sm:p-5 space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2.5">
                      <h3 className="font-display font-semibold text-base text-[#E8EEF2]">
                        {tr(lang, 'Scanner Multi-Marchés (BTCUSDT • ETHUSDT • XAUUSDT)')}
                      </h3>
                      {lastScannedAt && (
                        <span className="text-[11px] font-mono-tabular text-[#20C997] bg-[#20C997]/10 border border-[#20C997]/30 px-2 py-0.5 rounded">
                          {lang === 'en' ? 'Updated at' : 'Mis à jour à'} {new Date(lastScannedAt).toLocaleTimeString()}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-[#6E7B88] mt-0.5">
                      {lang === 'en'
                        ? `Simultaneous real-time analysis on closed candles (${selectedTimeframe.toUpperCase()} • Style ${selectedStyle}). Click a card to load its detailed chart.`
                        : `Analyse simultanée en temps réel sur bougies clôturées (${selectedTimeframe.toUpperCase()} • Style ${selectedStyle}). Cliquez sur une carte pour charger son graphique détaillé.`}
                    </p>
                  </div>
                  <button
                    onClick={() => runMultiScan(selectedTimeframe, selectedStyle, true)}
                    disabled={loadingScan}
                    className="w-full sm:w-auto justify-center px-4 py-2 bg-[#20C997] hover:bg-[#1AA67D] text-[#080C0F] rounded-lg text-xs font-semibold flex items-center gap-2 transition-colors"
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
                      <div key={n} className="p-4 rounded-lg bg-[#080C0F] border border-white/[0.07] animate-pulse space-y-3">
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
                          className={`p-4 rounded-lg bg-[#080C0F] border cursor-pointer transition-all space-y-2.5 ${
                            selectedSymbol === sc.symbol
                              ? 'border-[#20C997]/60 ring-1 ring-[#20C997]/30'
                              : 'border-white/[0.07] hover:border-[#20C997]/40'
                          }`}
                        >
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              <span className="font-mono-tabular font-bold text-sm text-[#E8EEF2]">{sc.symbol}</span>
                              <span className="text-[10px] font-mono-tabular px-1.5 py-0.5 rounded bg-white/[0.05] text-[#8B98A4]">
                                {sc.timeframe.toUpperCase()}
                              </span>
                            </div>
                            <span
                              className={`font-mono-tabular text-xs font-bold px-2 py-0.5 rounded ${
                                sc.signal === 'BUY'
                                  ? 'bg-[#20C997]/15 text-[#20C997] border border-[#20C997]/30'
                                  : sc.signal === 'SELL'
                                  ? 'bg-[#F04438]/15 text-[#F04438] border border-[#F04438]/30'
                                  : 'bg-[#D6A84F]/15 text-[#D6A84F] border border-[#D6A84F]/30'
                              }`}
                            >
                              {sc.signal} • {sc.teddy_score}/100
                            </span>
                          </div>

                          <div className="flex items-baseline justify-between">
                            <div
                              className={`font-mono-tabular text-lg font-bold transition-colors ${
                                scFlash === 'up'
                                  ? 'text-[#20C997]'
                                  : scFlash === 'down'
                                  ? 'text-[#F04438]'
                                  : scTick?.direction === 'up'
                                  ? 'text-[#32D583]'
                                  : scTick?.direction === 'down'
                                  ? 'text-[#F97066]'
                                  : 'text-[#E8EEF2]'
                              }`}
                            >
                              {Number(scLivePrice).toLocaleString('en-US', {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2,
                              })}{' '}
                              <span className="text-xs font-normal text-[#6E7B88]">USD</span>
                            </div>
                            <div className="text-[11px] font-mono-tabular text-[#6E7B88]">
                              RSI: {scInd.rsi ? Number(scInd.rsi).toFixed(1) : '—'} • ADX:{' '}
                              {scInd.adx ? Number(scInd.adx).toFixed(1) : '—'}
                            </div>
                          </div>

                          <div className="grid grid-cols-3 gap-1.5 text-[10px] font-mono-tabular">
                            {(['1h', '4h', '1d'] as const).map((tfKey) => {
                              const trVal = scTrends[tfKey] || 'NEUTRE';
                              return (
                                <div key={tfKey} className="bg-[#0D1318] px-2 py-1 rounded text-center">
                                  <span className="text-[#6E7B88] uppercase mr-1">{tfKey}:</span>
                                  <span
                                    className={
                                      trVal === 'HAUSSIER' || trVal === 'BULLISH'
                                        ? 'text-[#20C997] font-semibold'
                                        : trVal === 'BAISSIER' || trVal === 'BEARISH'
                                        ? 'text-[#F04438] font-semibold'
                                        : 'text-[#8B98A4]'
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
                              <span className="text-[#F04438]">SL: {sc.sl ? Number(sc.sl).toLocaleString() : '—'}</span>
                              <span className="text-[#20C997]">TP1: {sc.tp1 ? Number(sc.tp1).toLocaleString() : '—'}</span>
                              <span className="text-[#D6A84F]">R:R {sc.rr_ratio ? `1:${Number(sc.rr_ratio).toFixed(2)}` : '—'}</span>
                            </div>
                          )}

                          <div className="text-xs text-[#8B98A4] line-clamp-2">{sc.reason}</div>
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
                  <p className="text-xs text-[#8B98A4]">
                    {tr(
                      lang,
                      "Simulation fidèle avec frais d'ouverture/clôture (0.04%), slippage (0.02%) et surveillance automatique des seuils SL/TP."
                    )}
                  </p>
                </div>
                <button
                  onClick={handleResetPaperAccount}
                  disabled={isPending('paper-reset')}
                  className="px-3.5 py-2 bg-[#172129] hover:bg-[#202A32] border border-white/10 rounded-lg text-xs text-[#E8EEF2] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {tr(lang, 'Réinitialiser le capital (10 000 USDT)')}
                </button>
              </div>

              {paperStats && (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
                  <div className="bg-[#0D1318] border border-white/[0.07] rounded-xl p-5">
                    <div className="text-xs text-[#8B98A4]">{tr(lang, 'Capital Disponible')}</div>
                    <div className="font-mono-tabular text-2xl font-bold text-[#E8EEF2] mt-1">
                      {Number(paperStats.capital ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USDT
                    </div>
                  </div>
                  <div className="bg-[#0D1318] border border-white/[0.07] rounded-xl p-5">
                    <div className="text-xs text-[#8B98A4]">{tr(lang, 'Équité Totale (Marge + Latent)')}</div>
                    <div className="font-mono-tabular text-2xl font-bold text-[#20C997] mt-1">
                      {Number(paperStats.equity ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USDT
                    </div>
                  </div>
                  <div className="bg-[#0D1318] border border-white/[0.07] rounded-xl p-5">
                    <div className="text-xs text-[#8B98A4]">{tr(lang, 'PnL Réalisé Cumulé')}</div>
                    <div
                      className={`font-mono-tabular text-2xl font-bold mt-1 ${
                        (paperStats.total_pnl ?? 0) >= 0 ? 'text-[#20C997]' : 'text-[#F04438]'
                      }`}
                    >
                      {(paperStats.total_pnl ?? 0) >= 0 ? '+' : ''}
                      {Number(paperStats.total_pnl ?? 0).toFixed(2)} USDT
                    </div>
                  </div>
                  <div className="bg-[#0D1318] border border-white/[0.07] rounded-xl p-5">
                    <div className="text-xs text-[#8B98A4]">{tr(lang, 'Taux de Réussite (Win Rate)')}</div>
                    <div className="font-mono-tabular text-2xl font-bold text-[#D6A84F] mt-1">
                      {Number(paperStats.win_rate ?? 0).toFixed(1)}%{' '}
                      <span className="text-xs font-normal text-[#6E7B88]">
                        ({paperStats.wins ?? 0}W / {paperStats.losses ?? 0}L)
                      </span>
                    </div>
                  </div>
                </div>
              )}

              {/* Open Positions Table */}
              <div className="bg-[#0D1318] border border-white/[0.07] rounded-xl overflow-hidden">
                <div className="px-5 py-4 border-b border-white/[0.07] flex items-center justify-between">
                  <h3 className="font-display font-semibold text-sm text-[#E8EEF2]">
                    {lang === 'en' ? 'Open Positions' : 'Positions Ouvertes'} ({openPaper.length})
                  </h3>
                </div>
                {/* Mobile : une carte par position (même données, mêmes actions que le tableau) */}
                <div className="md:hidden divide-y divide-[#202A32]">
                  {openPaper.length === 0 ? (
                    <div className="p-4 text-xs text-[#6E7B88]">
                      {tr(
                        lang,
                        "Aucune position Paper ouverte. Utilisez le ticket d'ordre depuis l'onglet Market Intelligence."
                      )}
                    </div>
                  ) : (
                    openPaper.map((pos) => {
                      const m = computePaperMetrics(pos);
                      return (
                        <div key={pos.id} className="p-4 space-y-2 font-mono-tabular text-xs">
                          <div className="flex items-center justify-between">
                            <span className="font-semibold text-sm text-[#E8EEF2]">{pos.symbol}</span>
                            <StatusBadge tone={pos.side === 'BUY' ? 'positive' : 'negative'}>
                              {pos.side === 'BUY' ? 'LONG' : 'SHORT'} {pos.leverage}x
                            </StatusBadge>
                          </div>
                          <div className={`text-lg font-bold ${m.upnl >= 0 ? 'text-[#32D583]' : 'text-[#F97066]'}`}>
                            {m.upnl >= 0 ? '+' : ''}
                            {m.upnl.toFixed(2)} USDT <span className="text-xs">({m.upnlPct.toFixed(2)}%)</span>
                          </div>
                          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[#8B98A4]">
                            <span>{tr(lang, 'Entrée')}</span>
                            <span className="text-right text-[#E8EEF2]">{m.entryVal.toLocaleString()}</span>
                            <span>{tr(lang, 'Cours Actuel')}</span>
                            <span className="text-right text-[#E8EEF2]">
                              {m.currVal.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                            </span>
                            <span>SL / TP</span>
                            <span className="text-right">
                              <span className="text-[#F97066]">{m.slVal ? m.slVal.toLocaleString() : '—'}</span> /{' '}
                              <span className="text-[#32D583]">{m.tpVal ? m.tpVal.toLocaleString() : '—'}</span>
                            </span>
                            <span>{tr(lang, 'Marge')}</span>
                            <span className="text-right text-[#E8EEF2]">{m.marginVal.toFixed(2)} USDT</span>
                          </div>
                          <button
                            onClick={() => handleClosePaperPosition(pos.id)}
                            disabled={isPending(`paper-close-${pos.id}`)}
                            className="w-full min-h-11 bg-[#F04438]/15 hover:bg-[#F04438]/25 border border-[#F04438]/40 text-[#F97066] rounded-md text-xs disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            {isPending(`paper-close-${pos.id}`) ? tr(lang, 'Traitement…') : tr(lang, 'Clôturer')}
                          </button>
                        </div>
                      );
                    })
                  )}
                </div>
                <div className="hidden md:block overflow-x-auto">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="border-b border-white/[0.07] text-[#6E7B88] font-mono-tabular uppercase">
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
                          <td colSpan={8} className="py-8 text-center text-[#6E7B88] font-sans">
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
                              <td className="py-3.5 px-4 font-semibold text-[#E8EEF2]">{pos.symbol}</td>
                              <td className="py-3.5 px-4">
                                <span className={pos.side === 'BUY' ? 'text-[#20C997]' : 'text-[#F04438]'}>
                                  {pos.side} {pos.leverage}x
                                </span>
                              </td>
                              <td className="py-3.5 px-4 text-right">{entryVal.toLocaleString()}</td>
                              <td className="py-3.5 px-4 text-right font-semibold text-[#E8EEF2]">
                                {currVal.toLocaleString('en-US', {
                                  minimumFractionDigits: 2,
                                  maximumFractionDigits: 2,
                                })}
                              </td>
                              <td className="py-3.5 px-4 text-right">
                                <span className="text-[#F04438]">{slVal ? slVal.toLocaleString() : '—'}</span> /{' '}
                                <span className="text-[#20C997]">{tpVal ? tpVal.toLocaleString() : '—'}</span>
                              </td>
                              <td className="py-3.5 px-4 text-right">{marginVal.toFixed(2)} USDT</td>
                              <td
                                className={`py-3.5 px-4 text-right font-semibold ${
                                  computedUpnl >= 0 ? 'text-[#20C997]' : 'text-[#F04438]'
                                }`}
                              >
                                {computedUpnl >= 0 ? '+' : ''}
                                {computedUpnl.toFixed(2)} USDT ({computedUpnlPct.toFixed(2)}%)
                              </td>
                              <td className="py-3.5 px-4 text-right">
                                <button
                                  onClick={() => handleClosePaperPosition(pos.id)}
                                  disabled={isPending(`paper-close-${pos.id}`)}
                                  className="px-2.5 py-1 bg-[#F04438]/15 hover:bg-[#F04438]/25 border border-[#F04438]/40 text-[#F97066] rounded text-[11px] disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                  {isPending(`paper-close-${pos.id}`) ? tr(lang, 'Traitement…') : tr(lang, 'Clôturer')}
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
              <div className="bg-[#0D1318] border border-white/[0.07] rounded-xl overflow-hidden">
                <div className="px-5 py-4 border-b border-white/[0.07]">
                  <h3 className="font-display font-semibold text-sm text-[#E8EEF2]">
                    {lang === 'en' ? 'Closed Positions History' : 'Historique des Positions Clôturées'} ({closedPaper.length})
                  </h3>
                </div>
                <div className="md:hidden divide-y divide-white/[0.05]">
                  {closedPaper.length === 0 ? (
                    <div className="p-4 text-xs text-[#8B98A4]">
                      {lang === 'en' ? 'No closed positions yet.' : 'Aucune position clôturée pour le moment.'}
                    </div>
                  ) : (
                    closedPaper.slice(0, 20).map((pos) => {
                      const entryVal = Number(pos.entry ?? pos.entry_price ?? 0);
                      const exitVal = Number(pos.exit_price ?? 0);
                      const pnlVal = Number(pos.pnl ?? pos.pnl_usdt ?? 0);
                      const pnlPctVal = Number(pos.pnl_pct ?? 0);
                      return (
                        <div key={pos.id} className="p-4 space-y-2 font-mono-tabular text-xs">
                          <div className="flex items-center justify-between">
                            <span className="font-semibold text-sm text-[#E8EEF2]">{pos.symbol}</span>
                            <StatusBadge tone={pos.side === 'BUY' ? 'positive' : 'negative'}>
                              {pos.side === 'BUY' ? 'LONG' : 'SHORT'} {pos.leverage}x
                            </StatusBadge>
                          </div>
                          <div className={`text-base font-bold ${pnlVal >= 0 ? 'text-[#32D583]' : 'text-[#F97066]'}`}>
                            {pnlVal >= 0 ? '+' : ''}
                            {pnlVal.toFixed(2)} USDT <span className="text-xs">({pnlPctVal.toFixed(2)}%)</span>
                          </div>
                          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[#8B98A4]">
                            <span>{tr(lang, 'Entrée')}</span>
                            <span className="text-right text-[#E8EEF2]">{entryVal.toLocaleString()}</span>
                            <span>{tr(lang, 'Sortie')}</span>
                            <span className="text-right text-[#E8EEF2]">{exitVal ? exitVal.toLocaleString() : '—'}</span>
                            <span>{tr(lang, 'Raison')}</span>
                            <span className="text-right">{pos.close_reason ?? pos.exit_reason ?? '—'}</span>
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
                <div className="hidden md:block overflow-x-auto">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="border-b border-white/[0.07] text-[#6E7B88] font-mono-tabular uppercase">
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
                            <td className="py-3 px-4 font-semibold text-[#E8EEF2]">{pos.symbol}</td>
                            <td className="py-3 px-4">
                              <span className={pos.side === 'BUY' ? 'text-[#20C997]' : 'text-[#F04438]'}>
                                {pos.side} {pos.leverage}x
                              </span>
                            </td>
                            <td className="py-3.5 px-4 text-right">{entryVal.toLocaleString()}</td>
                            <td className="py-3 px-4 text-right">{exitVal ? exitVal.toLocaleString() : '—'}</td>
                            <td className="py-3 px-4 text-[#8B98A4]">{pos.close_reason ?? pos.exit_reason ?? '—'}</td>
                            <td
                              className={`py-3 px-4 text-right font-semibold ${
                                pnlVal >= 0 ? 'text-[#20C997]' : 'text-[#F04438]'
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
              <div className="lg:col-span-5 bg-[#0D1318] border border-white/[0.07] rounded-xl p-5 space-y-4">
                <h3 className="font-display font-semibold text-base text-[#E8EEF2]">
                  {tr(lang, 'Créer une Alerte de Prix')}
                </h3>
                <p className="text-xs text-[#8B98A4]">
                  {lang === 'en'
                    ? `Current quota: ${alerts.length} / ${alertLimit} active alerts (${user?.role.toUpperCase()}).`
                    : `Quota actuel : ${alerts.length} / ${alertLimit} alertes actives (${user?.role.toUpperCase()}).`}
                </p>
                <form onSubmit={handleAddAlert} className="space-y-3.5 text-xs">
                  <div>
                    <label className="block text-[#8B98A4] mb-1">{tr(lang, 'Symbole')}</label>
                    <select
                      value={newAlertSymbol}
                      onChange={(e) => setNewAlertSymbol(e.target.value)}
                      className="w-full px-3 py-2 bg-[#080C0F] border border-white/10 rounded-lg font-mono-tabular text-[#E8EEF2]"
                    >
                      {SYMBOLS.map((s) => (
                        <option key={s.id} value={s.id}>
                          {lang === 'en' && s.labelEn ? s.labelEn : s.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-[#8B98A4] mb-1">{tr(lang, 'Condition de franchissement')}</label>
                    <select
                      value={newAlertCond}
                      onChange={(e) => setNewAlertCond(e.target.value as 'above' | 'below')}
                      className="w-full px-3 py-2 bg-[#080C0F] border border-white/10 rounded-lg text-[#E8EEF2]"
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
                    <label className="block text-[#8B98A4] mb-1">{tr(lang, 'Prix Cible (USD / USDT)')}</label>
                    <input
                      type="number"
                      step="any"
                      value={newAlertPrice}
                      onChange={(e) => setNewAlertPrice(e.target.value)}
                      placeholder="85000"
                      className="w-full px-3 py-2 bg-[#080C0F] border border-white/10 rounded-lg font-mono-tabular text-[#E8EEF2]"
                      required
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={isPending('alert-add')}
                    className="w-full py-2.5 bg-[#20C997] hover:bg-[#1AA67D] text-[#080C0F] font-semibold rounded-lg transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
                  >
                    {isPending('alert-add') ? tr(lang, 'Traitement…') : tr(lang, "Activer l'Alerte Prix")}
                  </button>
                </form>
              </div>

              <div className="lg:col-span-7 bg-[#0D1318] border border-white/[0.07] rounded-xl p-5 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="font-display font-semibold text-base text-[#E8EEF2]">
                    {lang === 'en' ? 'Active Alerts' : 'Alertes Actives'} ({alerts.length})
                  </h3>
                  {alerts.length > 0 && (
                    <button
                      onClick={handleClearAlerts}
                      disabled={isPending('alert-clear')}
                      className="text-xs text-[#F04438] hover:underline disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {isPending('alert-clear') ? tr(lang, 'Traitement…') : tr(lang, 'Tout effacer')}
                    </button>
                  )}
                </div>

                <div className="divide-y divide-white/[0.06]">
                  {alerts.length === 0 ? (
                    <div className="py-10 text-center text-xs text-[#6E7B88]">
                      {tr(lang, 'Aucune alerte active pour le moment.')}
                    </div>
                  ) : (
                    alerts.map((a) => (
                      <div key={a.id} className="py-3 flex items-center justify-between text-xs">
                        <div className="flex items-center gap-3">
                          <span className="font-mono-tabular font-bold text-sm text-[#E8EEF2]">{a.symbol}</span>
                          <span
                            className={`font-mono-tabular px-2 py-0.5 rounded ${
                              a.condition === 'above'
                                ? 'bg-[#20C997]/15 text-[#20C997]'
                                : 'bg-[#F04438]/15 text-[#F04438]'
                            }`}
                          >
                            {a.condition === 'above' ? tr(lang, '≥ HAUSSE') : tr(lang, '≤ BAISSE')}
                          </span>
                          <span className="font-mono-tabular text-sm font-semibold text-[#E8EEF2]">
                            {Number(a.price ?? 0).toLocaleString()} USD
                          </span>
                        </div>
                        <button
                          onClick={() => handleDeleteAlert(a.id)}
                          disabled={isPending(`alert-delete-${a.id}`)}
                          className="p-1.5 text-[#6E7B88] hover:text-[#F04438] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
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
          {activeTab === 'safety' && !tradingCfg && (
            <div className="bg-[#0D1318] border border-white/[0.07] rounded-xl p-6 flex flex-col sm:flex-row items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <RefreshCw className={`w-5 h-5 text-[#20C997] ${loadingLiveAccount ? 'animate-spin' : ''}`} />
                <div>
                  <h3 className="font-display font-semibold text-sm text-[#E8EEF2]">
                    {lang === 'en'
                      ? 'Loading Auto-Trade & Safety Center configuration...'
                      : 'Chargement de la configuration Auto-Trade & Safety Center...'}
                  </h3>
                  <p className="text-xs text-[#8B98A4]">
                    {lang === 'en'
                      ? 'Synchronizing risk guardrails, API keys, and live positions with the server.'
                      : 'Synchronisation des garde-fous de risque, des clés API et des positions avec le serveur.'}
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => loadLiveAccountAndOrders()}
                className="px-4 py-2 bg-[#20C997] hover:bg-[#1AA67D] text-[#080C0F] font-semibold text-xs rounded-lg transition-colors"
              >
                {tr(lang, 'Réessayer maintenant')}
              </button>
            </div>
          )}
          {activeTab === 'safety' && tradingCfg && (
            <div className="space-y-6">
              {/* Top Status & Safety State Banner */}
              <div
                className={`p-5 rounded-xl border flex flex-wrap items-center justify-between gap-4 ${
                  tradingCfg.safety_lock
                    ? 'bg-[#F04438]/10 border-[#F04438]/40'
                    : tradingCfg.safety_warn
                    ? 'bg-[#D6A84F]/10 border-[#D6A84F]/40'
                    : 'bg-[#20C997]/10 border-[#20C997]/30'
                }`}
              >
                <div className="space-y-1.5">
                  <div className="flex flex-wrap items-center gap-2.5 font-display font-bold text-base">
                    {tradingCfg.safety_lock ? (
                      <>
                        <ShieldAlert className="w-5 h-5 text-[#F04438]" />
                        <span className="text-[#F97066]">{tr(lang, 'SAFETY LOCK ACTIF (Auto-Trade Suspendu)')}</span>
                      </>
                    ) : tradingCfg.safety_warn ? (
                      <>
                        <AlertTriangle className="w-5 h-5 text-[#D6A84F]" />
                        <span className="text-[#E2BC6A]">{tr(lang, 'SAFETY WARN (Avertissement Temporaire Actif)')}</span>
                      </>
                    ) : (
                      <>
                        <ShieldCheck className="w-5 h-5 text-[#20C997]" />
                        <span className="text-[#32D583]">{tr(lang, 'SAFETY CENTER OPÉRATIONNEL')}</span>
                      </>
                    )}

                    <span
                      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-md text-xs font-mono-tabular border ${
                        tradingCfg.credentials_valid
                          ? 'bg-[#20C997]/20 text-[#32D583] border-[#20C997]/40'
                          : 'bg-[#F04438]/20 text-[#F97066] border-[#F04438]/40'
                      }`}
                    >
                      <span
                        className={`w-2 h-2 rounded-full ${
                          tradingCfg.credentials_valid ? 'bg-[#20C997] animate-pulse' : 'bg-[#F04438]'
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

                  <div className="text-xs text-[#8B98A4]">
                    {tradingCfg.safety_lock_reason ||
                      tradingCfg.safety_warn_reason ||
                      tradingCfg.api_status_message ||
                      tr(
                        lang,
                        'Tous les garde-fous de risque (exposition max 20%, fraîcheur de signal 180s, TTL 3600s) sont actifs.'
                      )}
                  </div>
                  {(tradingCfg.safety_lock_at || tradingCfg.safety_warn_at) && (
                    <div className="text-[11px] font-mono-tabular text-[#6E7B88]">
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
                      className="w-32 px-2.5 py-2 bg-[#080C0F] border border-white/15 rounded-lg font-mono-tabular text-[#E8EEF2]"
                    />
                  )}
                  {(tradingCfg.safety_lock || tradingCfg.safety_warn) && (
                    <button
                      onClick={() => handleSafetyAction('clearsafe')}
                      disabled={isPending('safety-clearsafe')}
                      className="px-3.5 py-2 bg-[#20C997] hover:bg-[#1AA67D] text-[#080C0F] font-semibold rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
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
                      className="px-3.5 py-2 bg-[#F04438]/20 hover:bg-[#F04438]/30 border border-[#F04438]/40 text-[#F97066] font-semibold rounded-lg transition-colors"
                    >
                      {tr(lang, 'Verrouiller Safe Mode')}
                    </button>
                  )}
                  <button
                    onClick={() => handleSafetyAction('emergency_stop')}
                    disabled={isPending('safety-emergency_stop')}
                    className="px-3.5 py-2 bg-[#F04438] hover:bg-[#D92D20] text-white font-semibold rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    title={
                      lang === 'en'
                        ? 'Close all open positions and disable AutoTrade (/emergency)'
                        : 'Ferme toutes les positions ouvertes et désactive AutoTrade (/emergency)'
                    }
                  >
                    {isPending('safety-emergency_stop') ? '⏳ Emergency Stop…' : '🛑 Emergency Stop All (/emergency)'}
                  </button>
                  <button
                    onClick={() =>
                      apiFetch('/api/trading/reconcile', { method: 'POST' })
                        .then(() => {
                          loadLiveAccountAndOrders();
                          showToast(tr(lang, 'Réconciliation DB ↔ Binance exécutée.'), 'success');
                        })
                        .catch((err: any) => showToast(err.message || 'Erreur lors de la réconciliation.', 'error'))
                    }
                    className="px-3.5 py-2 bg-[#0D1318] hover:bg-[#172129] border border-white/15 text-[#E8EEF2] rounded-lg transition-colors"
                  >
                    {tr(lang, 'Réconcilier DB ↔ Binance')}
                  </button>
                </div>
              </div>

              {/* Accès rapide aux sections de l'onglet (aucune fonction masquée) */}
              <div className="sticky top-0 z-20 -mx-3 sm:mx-0 px-3 sm:px-0 py-1.5 bg-[#080C0F]">
                <div className="flex gap-1.5 overflow-x-auto" role="navigation" aria-label={tr(lang, 'Sections Auto-Trade', 'Auto-Trade sections')}>
                  {[
                    { id: 'at-config', label: tr(lang, 'Configuration', 'Configuration') },
                    { id: 'at-binance', label: tr(lang, 'Binance & compte', 'Binance & account') },
                    { id: 'at-live-order', label: tr(lang, 'Ordre live', 'Live order') },
                    { id: 'at-positions', label: tr(lang, 'Positions & ordres', 'Positions & orders') },
                  ].map((sec) => (
                    <button
                      key={sec.id}
                      type="button"
                      onClick={() => document.getElementById(sec.id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
                      className="shrink-0 min-h-9 px-3 rounded-md border border-[#202A32] bg-[#0D1318] text-xs font-semibold text-[#8B98A4] hover:text-[#E8EEF2] hover:bg-[#172129]"
                    >
                      {sec.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Row 1: Complete Bot Auto-Trade Parameters + API Keys & Real-Time Account */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                {/* Left (7 cols): Full Bot Configuration (/config, /autotrade, /periodic_analysis) */}
                <div id="at-config" className="scroll-mt-24 lg:col-span-7 bg-[#0D1318] border border-white/[0.07] rounded-xl p-5 space-y-5">
                  <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.07] pb-3.5">
                    <div>
                      <h3 className="font-display font-semibold text-base text-[#E8EEF2]">
                        {tr(lang, 'Configuration Complète Auto-Trade & Stratégie (Miroir Bot Telegram)')}
                      </h3>
                      <p className="text-xs text-[#6E7B88]">
                        {tr(
                          lang,
                          'Synchronisé en temps réel avec `/config`, `/autotrade` et `/periodic_analysis`.'
                        )}
                      </p>
                      {tradingCfg.enabled && tradingCfg.engine_online === false && (
                        <p className="mt-1.5 text-xs text-[#E2BC6A] bg-[#D6A84F]/10 border border-[#D6A84F]/30 rounded-lg px-2.5 py-1.5">
                          {lang === 'en'
                            ? '⚠️ Auto-Trade is ON but the trading engine is offline: no order will be placed. Start the bot service (main.py), or set AUTOTRADE_EMBEDDED=1 on the web service and redeploy.'
                            : '⚠️ Auto-Trade est activé mais le moteur de trading est hors ligne : aucun ordre ne sera passé. Démarrez le service bot (main.py), ou définissez AUTOTRADE_EMBEDDED=1 sur le service web puis redéployez.'}
                        </p>
                      )}
                      {tradingCfg.enabled && tradingCfg.engine_online === true && (
                        <p className="mt-1.5 text-xs text-[#20C997]">
                          {lang === 'en' ? '● Trading engine online' : '● Moteur de trading en ligne'}
                        </p>
                      )}
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
                            ? 'bg-[#20C997] text-[#080C0F]'
                            : 'bg-[#172129] text-[#8B98A4] border border-white/10 hover:text-[#E8EEF2]'
                        }`}
                      >
                        Auto-Trade : {tradingCfg.enabled ? 'ON ✅' : 'OFF ❌'}
                      </button>
                      <button
                        onClick={() => handleUpdateTradingConfig({ testnet: !tradingCfg.testnet })}
                        className={`px-3 py-1.5 rounded-lg text-xs font-mono-tabular font-semibold border transition-colors ${
                          tradingCfg.testnet
                            ? 'bg-[#4EA1FF]/15 text-[#6BB1FF] border-[#4EA1FF]/40'
                            : 'bg-[#D6A84F]/15 text-[#E2BC6A] border-[#D6A84F]/40'
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
                    <div className="text-xs font-mono-tabular uppercase tracking-wider text-[#20C997]">
                      {tr(lang, '1. Marché, Style & Analyse Périodique')}
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
                      <div>
                        <label className="block text-[#8B98A4] mb-1">{tr(lang, 'Marché (/setmarket)')}</label>
                        <select
                          value={tradingCfg.market_type}
                          onChange={(e) =>
                            handleUpdateTradingConfig({ market_type: e.target.value as 'futures' | 'spot' })
                          }
                          className="w-full px-3 py-2 bg-[#080C0F] border border-white/10 rounded-lg text-[#E8EEF2]"
                        >
                          <option value="futures">FUTURES (USDT-M)</option>
                          <option value="spot">SPOT</option>
                        </select>
                      </div>

                      <div>
                        <label className="block text-[#8B98A4] mb-1">{tr(lang, 'Style (/settradingstyle)')}</label>
                        <select
                          value={tradingCfg.trading_style}
                          onChange={(e) => {
                            const st = e.target.value;
                            const patch: Partial<TradingConfigState> = { trading_style: st };
                            if (st === 'scalping') patch.analysis_timeframe = '5m';
                            if (st === 'scalping_15m') patch.analysis_timeframe = '15m';
                            handleUpdateTradingConfig(patch);
                          }}
                          className="w-full px-3 py-2 bg-[#080C0F] border border-white/10 rounded-lg text-[#E8EEF2]"
                        >
                          {STYLES.map((st) => (
                            <option key={st.id} value={st.id}>
                              {st.label}
                            </option>
                          ))}
                        </select>
                      </div>

                      <div>
                        <label className="block text-[#8B98A4] mb-1">Timeframe (/setanalysistf)</label>
                        <select
                          value={tradingCfg.analysis_timeframe}
                          onChange={(e) => handleUpdateTradingConfig({ analysis_timeframe: e.target.value })}
                          className="w-full px-3 py-2 bg-[#080C0F] border border-white/10 rounded-lg font-mono-tabular text-[#E8EEF2]"
                        >
                          {TIMEFRAMES.map((tf) => (
                            <option key={tf} value={tf}>
                              {tf.toUpperCase()}
                            </option>
                          ))}
                        </select>
                      </div>

                      <div>
                        <label className="block text-[#8B98A4] mb-1">{tr(lang, 'Intervalle Scan (/setanalysisinterval)')}</label>
                        <div className="flex gap-1.5">
                          {[5, 10].map((mins) => (
                            <button
                              key={mins}
                              type="button"
                              onClick={() => handleUpdateTradingConfig({ analysis_interval_minutes: mins })}
                              className={`flex-1 py-2 rounded-lg font-mono-tabular font-semibold border transition-colors ${
                                tradingCfg.analysis_interval_minutes === mins
                                  ? 'bg-[#20C997]/20 border-[#20C997] text-[#20C997]'
                                  : 'bg-[#080C0F] border-white/10 text-[#8B98A4] hover:text-[#E8EEF2]'
                              }`}
                            >
                              {mins} min
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-lg bg-[#080C0F] border border-white/[0.06] text-xs">
                      <label className="flex items-center gap-2.5 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={tradingCfg.periodic_analysis_enabled}
                          onChange={(e) =>
                            handleUpdateTradingConfig({ periodic_analysis_enabled: e.target.checked })
                          }
                        />
                        <span className="font-medium text-[#E8EEF2]">
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
                        className="px-3 py-1.5 bg-[#20C997]/15 hover:bg-[#20C997]/25 border border-[#20C997]/40 text-[#20C997] rounded-md font-semibold flex items-center gap-1.5"
                      >
                        <Play className="w-3.5 h-3.5" />
                        <span>{tr(lang, 'Scanner Maintenant (/periodic_analysis now)')}</span>
                      </button>
                    </div>
                  </div>

                  {/* Section 2: Leverage, Risk, Max Positions, Min Score, Daily Max Loss, Cooldown */}
                  <div className="space-y-3 pt-2 border-t border-white/[0.06]">
                    <div className="text-xs font-mono-tabular uppercase tracking-wider text-[#20C997]">
                      {tr(lang, "2. Paramètres de Risque, Levier & Filtres d'Exécution")}
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 text-xs">
                      {/* Leverage */}
                      <div className="p-3 rounded-lg bg-[#080C0F] border border-white/[0.06] space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-[#8B98A4]">{tr(lang, 'Levier (/setleverage 1–125)')}</span>
                          <span className="font-mono-tabular font-bold text-[#20C997]">x{tradingCfg.leverage}</span>
                        </div>
                        <div className="flex flex-wrap gap-1">
                          {[1, 2, 5, 10, 20, 50].map((lev) => (
                            <button
                              key={lev}
                              type="button"
                              onClick={() => handleUpdateTradingConfig({ leverage: lev })}
                              className={`px-2 py-1 rounded font-mono-tabular text-[11px] border ${
                                tradingCfg.leverage === lev
                                  ? 'bg-[#20C997] text-[#080C0F] border-[#20C997] font-bold'
                                  : 'bg-[#0D1318] text-[#8B98A4] border-white/10 hover:text-[#E8EEF2]'
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
                          className="w-full px-2.5 py-1.5 bg-[#0D1318] border border-white/10 rounded font-mono-tabular text-[#E8EEF2]"
                        />
                      </div>

                      {/* Risk per trade */}
                      <div className="p-3 rounded-lg bg-[#080C0F] border border-white/[0.06] space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-[#8B98A4]">{tr(lang, 'Risque / Trade (/setrisk)')}</span>
                          <span className="font-mono-tabular font-bold text-[#20C997]">
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
                                  ? 'bg-[#20C997] text-[#080C0F] border-[#20C997] font-bold'
                                  : 'bg-[#0D1318] text-[#8B98A4] border-white/10 hover:text-[#E8EEF2]'
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
                          className="w-full px-2.5 py-1.5 bg-[#0D1318] border border-white/10 rounded font-mono-tabular text-[#E8EEF2]"
                        />
                      </div>

                      {/* Max Positions */}
                      <div className="p-3 rounded-lg bg-[#080C0F] border border-white/[0.06] space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-[#8B98A4]">Max Positions (/setmaxpos)</span>
                          <span className="font-mono-tabular font-bold text-[#20C997]">
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
                                  ? 'bg-[#20C997] text-[#080C0F] border-[#20C997] font-bold'
                                  : 'bg-[#0D1318] text-[#8B98A4] border-white/10 hover:text-[#E8EEF2]'
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
                          className="w-full px-2.5 py-1.5 bg-[#0D1318] border border-white/10 rounded font-mono-tabular text-[#E8EEF2]"
                        />
                      </div>

                      {/* Min Score */}
                      <div className="p-3 rounded-lg bg-[#080C0F] border border-white/[0.06] space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-[#8B98A4]">{tr(lang, 'Score Min (/setminscore)')}</span>
                          <span className="font-mono-tabular font-bold text-[#20C997]">
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
                                  ? 'bg-[#20C997] text-[#080C0F] border-[#20C997] font-bold'
                                  : 'bg-[#0D1318] text-[#8B98A4] border-white/10 hover:text-[#E8EEF2]'
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
                          className="w-full px-2.5 py-1.5 bg-[#0D1318] border border-white/10 rounded font-mono-tabular text-[#E8EEF2]"
                        />
                      </div>

                      {/* Daily Max Loss */}
                      <div className="p-3 rounded-lg bg-[#080C0F] border border-white/[0.06] space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-[#8B98A4]">{tr(lang, 'Perte Max/Jour (/setdailymaxloss)')}</span>
                          <span className="font-mono-tabular font-bold text-[#F04438]">
                            {tradingCfg.max_daily_loss}%
                          </span>
                        </div>
                        <div className="text-[11px] font-mono-tabular text-[#6E7B88]">
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
                            className="flex-1 px-2.5 py-1.5 bg-[#0D1318] border border-white/10 rounded font-mono-tabular text-[#E8EEF2]"
                          />
                          <button
                            type="button"
                            onClick={() => handleSafetyAction('reset_daily_loss')}
                            disabled={isPending('safety-reset_daily_loss')}
                            className="px-2.5 py-1.5 bg-[#172129] hover:bg-[#202A32] rounded text-[11px] text-[#E8EEF2] disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            Reset
                          </button>
                        </div>
                      </div>

                      {/* Cooldown */}
                      <div className="p-3 rounded-lg bg-[#080C0F] border border-white/[0.06] space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-[#8B98A4]">Cooldown (/setcooldown)</span>
                          <span className="font-mono-tabular font-bold text-[#D6A84F]">
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
                                  ? 'bg-[#20C997] text-[#080C0F] border-[#20C997] font-bold'
                                  : 'bg-[#0D1318] text-[#8B98A4] border-white/10 hover:text-[#E8EEF2]'
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
                          className="w-full px-2.5 py-1.5 bg-[#0D1318] border border-white/10 rounded font-mono-tabular text-[#E8EEF2]"
                        />
                      </div>
                    </div>
                  </div>

                  {/* Section 3: Trailing Stop ATR & DCA Parameters (/settrailing, /setdca) */}
                  <div className="space-y-3 pt-2 border-t border-white/[0.06]">
                    <div className="text-xs font-mono-tabular uppercase tracking-wider text-[#20C997]">
                      {tr(lang, '3. Trailing Stop Dynamique (ATR) & DCA (/settrailing • /setdca)')}
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
                      {/* Trailing Stop */}
                      <div className="p-3.5 rounded-lg bg-[#080C0F] border border-white/[0.06] space-y-2.5">
                        <div className="flex items-center justify-between">
                          <label className="flex items-center gap-2 cursor-pointer font-semibold text-[#E8EEF2]">
                            <input
                              type="checkbox"
                              checked={tradingCfg.trailing_stop}
                              onChange={(e) => handleUpdateTradingConfig({ trailing_stop: e.target.checked })}
                            />
                            <span>Trailing Stop ATR (/settrailing)</span>
                          </label>
                          <span className="font-mono-tabular text-[#20C997]">
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
                                  ? 'bg-[#20C997] text-[#080C0F] border-[#20C997] font-bold'
                                  : 'bg-[#0D1318] text-[#8B98A4] border-white/10 hover:text-[#E8EEF2]'
                              }`}
                            >
                              {pct}%
                            </button>
                          ))}
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-[#8B98A4] text-[11px]">{tr(lang, 'Facteur / Distance (0.1–20%) :')}</span>
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
                            className="w-24 px-2 py-1 bg-[#0D1318] border border-white/10 rounded font-mono-tabular text-[#E8EEF2]"
                          />
                        </div>
                      </div>

                      {/* DCA */}
                      <div className="p-3.5 rounded-lg bg-[#080C0F] border border-white/[0.06] space-y-2.5">
                        <div className="flex items-center justify-between">
                          <label className="flex items-center gap-2 cursor-pointer font-semibold text-[#E8EEF2]">
                            <input
                              type="checkbox"
                              checked={tradingCfg.dca_enabled}
                              onChange={(e) => handleUpdateTradingConfig({ dca_enabled: e.target.checked })}
                            />
                            <span>{tr(lang, 'Configuration DCA (/setdca)')}</span>
                          </label>
                          <span className="font-mono-tabular text-[#D6A84F]">
                            {tradingCfg.dca_enabled ? 'ON' : 'OFF'} ({tradingCfg.dca_steps ?? 3}{' '}
                            {lang === 'en' ? 'st.' : 'ét.'}, {tradingCfg.dca_step_pct ?? 2.0}%)
                          </span>
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                          <div>
                            <label className="block text-[11px] text-[#8B98A4] mb-1">{tr(lang, 'Étapes (1–10)')}</label>
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
                              className="w-full px-2 py-1 bg-[#0D1318] border border-white/10 rounded font-mono-tabular text-[#E8EEF2]"
                            />
                          </div>
                          <div>
                            <label className="block text-[11px] text-[#8B98A4] mb-1">{tr(lang, 'Écart % (0.1–20%)')}</label>
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
                              className="w-full px-2 py-1 bg-[#0D1318] border border-white/10 rounded font-mono-tabular text-[#E8EEF2]"
                            />
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Section 4: Whitelist & Blacklist (/whitelist, /blacklist) */}
                  <div className="space-y-3 pt-2 border-t border-white/[0.06]">
                    <div className="text-xs font-mono-tabular uppercase tracking-wider text-[#20C997]">
                      {tr(lang, '4. Filtrage des Symboles Documentés (/whitelist • /blacklist)')}
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
                      {/* Whitelist */}
                      <div className="p-3.5 rounded-lg bg-[#080C0F] border border-white/[0.06] space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-[#E8EEF2]">✅ Whitelist AutoTrade</span>
                          {(tradingCfg.symbol_whitelist || []).length > 0 && (
                            <button
                              type="button"
                              onClick={() => handleUpdateTradingConfig({ symbol_whitelist: [] })}
                              className="text-[11px] text-[#F04438] hover:underline"
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
                                    ? 'bg-[#20C997]/20 border-[#20C997] text-[#20C997] font-semibold'
                                    : 'bg-[#0D1318] border-white/10 text-[#8B98A4] hover:text-[#E8EEF2]'
                                }`}
                              >
                                {active ? '✓ ' : '+ '}
                                {s.id}
                              </button>
                            );
                          })}
                        </div>
                        <div className="text-[11px] text-[#6E7B88]">
                          {(tradingCfg.symbol_whitelist || []).length === 0
                            ? tr(lang, 'Aucune restriction (tous les symboles documentés sont autorisés).')
                            : `${lang === 'en' ? 'Allowed assets:' : 'Actifs autorisés :'} ${(tradingCfg.symbol_whitelist || []).join(', ')}`}
                        </div>
                      </div>

                      {/* Blacklist */}
                      <div className="p-3.5 rounded-lg bg-[#080C0F] border border-white/[0.06] space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-[#E8EEF2]">🚫 Blacklist AutoTrade</span>
                          {(tradingCfg.symbol_blacklist || []).length > 0 && (
                            <button
                              type="button"
                              onClick={() => handleUpdateTradingConfig({ symbol_blacklist: [] })}
                              className="text-[11px] text-[#F04438] hover:underline"
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
                                    ? 'bg-[#F04438]/20 border-[#F04438] text-[#F97066] font-semibold'
                                    : 'bg-[#0D1318] border-white/10 text-[#8B98A4] hover:text-[#E8EEF2]'
                                }`}
                              >
                                {active ? '✕ ' : '+ '}
                                {s.id}
                              </button>
                            );
                          })}
                        </div>
                        <div className="text-[11px] text-[#6E7B88]">
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
                  <div id="at-binance" className="scroll-mt-24 bg-[#0D1318] border border-white/[0.07] rounded-xl p-5 space-y-4">
                    <div className="flex items-center justify-between border-b border-white/[0.07] pb-3">
                      <div className="flex items-center gap-2">
                        <Key className="w-4 h-4 text-[#20C997]" />
                        <h3 className="font-display font-semibold text-base text-[#E8EEF2]">
                          {tr(lang, 'Clés API Binance (/setapikeys)')}
                        </h3>
                      </div>
                      <span
                        className={`px-2 py-0.5 rounded text-[11px] font-mono-tabular font-semibold border ${
                          tradingCfg.credentials_valid
                            ? 'bg-[#20C997]/15 text-[#20C997] border-[#20C997]/40'
                            : 'bg-[#F04438]/15 text-[#F97066] border-[#F04438]/40'
                        }`}
                      >
                        {tradingCfg.credentials_valid
                          ? `● ${lang === 'en' ? 'OPERATIONAL' : 'OPÉRATIONNEL'} (${tradingCfg.api_key_masked || 'Testnet'})`
                          : tr(lang, '○ NON CONNECTÉ')}
                      </span>
                    </div>

                    <div className="flex items-center justify-between p-3 rounded-lg bg-[#080C0F] border border-white/[0.06] text-xs">
                      <div>
                        <div className="text-[#8B98A4]">{tr(lang, 'Clé active :')}</div>
                        <div className="font-mono-tabular font-semibold text-[#E8EEF2]">
                          {tradingCfg.api_key_masked || tr(lang, 'Aucune clé chargée')} •{' '}
                          {tradingCfg.testnet ? 'TESTNET' : 'LIVE'} ({tradingCfg.market_type.toUpperCase()})
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={handleTestBinanceConnection}
                        disabled={testingApiConn || isPending('binance-test')}
                        className="px-3 py-1.5 bg-[#172129] hover:bg-[#202A32] border border-white/10 rounded-lg text-xs text-[#E8EEF2] flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        <RefreshCw className={`w-3.5 h-3.5 ${testingApiConn ? 'animate-spin text-[#20C997]' : ''}`} />
                        <span>{testingApiConn ? tr(lang, 'Test en cours…') : tr(lang, 'Tester Connexion')}</span>
                      </button>
                    </div>

                    <form onSubmit={handleSaveBinanceKeys} className="space-y-3 text-xs">
                      <div>
                        <label className="block text-[#8B98A4] mb-1">Binance API Key</label>
                        <input
                          type="text"
                          value={binanceKey}
                          onChange={(e) => setBinanceKey(e.target.value)}
                          placeholder={tr(lang, 'Entrez votre clé API Binance...')}
                          className="w-full px-3 py-2 bg-[#080C0F] border border-white/10 rounded-lg font-mono-tabular text-[#E8EEF2]"
                          required
                        />
                      </div>
                      <div>
                        <label className="block text-[#8B98A4] mb-1">Binance API Secret</label>
                        <input
                          type="password"
                          value={binanceSecret}
                          onChange={(e) => setBinanceSecret(e.target.value)}
                          placeholder="••••••••••••••••••••••••••••••••"
                          className="w-full px-3 py-2 bg-[#080C0F] border border-white/10 rounded-lg font-mono-tabular text-[#E8EEF2]"
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
                        disabled={isPending('binance-save')}
                        className="w-full py-2.5 bg-[#20C997] hover:bg-[#1AA67D] text-[#080C0F] font-semibold rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {isPending('binance-save') ? tr(lang, 'Vérification en cours…') : tr(lang, 'Enregistrer & Vérifier les Clés API')}
                      </button>
                    </form>
                  </div>

                  {/* Real-Time Binance Account Balance & Margin Card (/account, /balance) */}
                  <div className="bg-[#0D1318] border border-white/[0.07] rounded-xl p-5 space-y-4">
                    <div className="flex items-center justify-between border-b border-white/[0.07] pb-3">
                      <div className="flex items-center gap-2">
                        <Wallet className="w-4 h-4 text-[#20C997]" />
                        <h3 className="font-display font-semibold text-base text-[#E8EEF2]">
                          {tr(lang, 'Solde & Marge Compte Binance (/account)')}
                        </h3>
                      </div>
                      <button
                        type="button"
                        onClick={loadLiveAccountAndOrders}
                        disabled={loadingLiveAccount}
                        className="text-xs text-[#20C997] hover:underline flex items-center gap-1"
                      >
                        <RefreshCw className={`w-3.5 h-3.5 ${loadingLiveAccount ? 'animate-spin' : ''}`} />
                        <span>{tr(lang, 'Rafraîchir')}</span>
                      </button>
                    </div>

                    {liveAccount ? (
                      <div className="space-y-3 text-xs">
                        <div className="grid grid-cols-2 gap-3 font-mono-tabular">
                          <div className="p-3 rounded-lg bg-[#080C0F] border border-white/[0.06]">
                            <div className="text-[10px] text-[#6E7B88] uppercase">{tr(lang, 'Solde Total Wallet')}</div>
                            <div className="text-base font-bold text-[#E8EEF2] mt-0.5">
                              {Number(liveAccount.total_wallet_balance || 0).toLocaleString('en-US', {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2,
                              })}{' '}
                              USDT
                            </div>
                          </div>
                          <div className="p-3 rounded-lg bg-[#080C0F] border border-white/[0.06]">
                            <div className="text-[10px] text-[#6E7B88] uppercase">{tr(lang, 'Disponible')}</div>
                            <div className="text-base font-bold text-[#20C997] mt-0.5">
                              {Number(liveAccount.available_balance || 0).toLocaleString('en-US', {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2,
                              })}{' '}
                              USDT
                            </div>
                          </div>
                          <div className="p-3 rounded-lg bg-[#080C0F] border border-white/[0.06]">
                            <div className="text-[10px] text-[#6E7B88] uppercase">{tr(lang, 'PnL Non Réalisé')}</div>
                            <div
                              className={`text-base font-bold mt-0.5 ${
                                Number(liveAccount.unrealized_pnl || 0) >= 0 ? 'text-[#20C997]' : 'text-[#F04438]'
                              }`}
                            >
                              {Number(liveAccount.unrealized_pnl || 0) >= 0 ? '+' : ''}
                              {Number(liveAccount.unrealized_pnl || 0).toFixed(2)} USDT
                            </div>
                          </div>
                          <div className="p-3 rounded-lg bg-[#080C0F] border border-white/[0.06]">
                            <div className="text-[10px] text-[#6E7B88] uppercase">{tr(lang, 'Marge Utilisée')}</div>
                            <div className="text-base font-bold text-[#D6A84F] mt-0.5">
                              {liveAccount.market_type === 'futures' ? `${liveAccount.margin_used_pct || 0}%` : 'SPOT'}
                            </div>
                          </div>
                        </div>

                        {Array.isArray(liveAccount.assets) && liveAccount.assets.length > 0 && (
                          <div className="space-y-1.5 pt-1">
                            <div className="text-[11px] text-[#8B98A4] font-semibold">{tr(lang, 'Actifs détectés :')}</div>
                            <div className="max-h-32 overflow-y-auto divide-y divide-white/[0.05] font-mono-tabular">
                              {liveAccount.assets.slice(0, 6).map((a: any) => (
                                <div key={a.asset} className="py-1.5 flex items-center justify-between text-[11px]">
                                  <span className="font-bold text-[#E8EEF2]">{a.asset}</span>
                                  <span className="text-[#8B98A4]">
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
                      <div className="p-4 rounded-lg bg-[#080C0F] border border-white/[0.06] text-xs text-[#8B98A4]">
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
                <div id="at-live-order" className="scroll-mt-24 lg:col-span-5 bg-[#0D1318] border border-white/[0.07] rounded-xl p-5 space-y-4">
                  <div className="flex items-center justify-between border-b border-white/[0.07] pb-3">
                    <div>
                      <h3 className="font-display font-semibold text-base text-[#E8EEF2]">
                        {tr(lang, "Ticket d'Ordre Live Manuel (/live_long • /live_short)")}
                      </h3>
                      <p className="text-xs text-[#6E7B88]">
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
                            ? 'bg-[#20C997] text-[#080C0F] border-[#20C997]'
                            : 'bg-[#080C0F] text-[#8B98A4] border-white/10'
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
                            ? 'bg-[#F04438] text-white border-[#F04438]'
                            : 'bg-[#080C0F] text-[#8B98A4] border-white/10'
                        }`}
                      >
                        {tr(lang, '🔴 OUVRIR SHORT (SELL)')}
                      </button>
                    </div>

                    <div className="grid grid-cols-2 gap-2.5">
                      <div>
                        <label className="block text-[11px] text-[#8B98A4] mb-1">{tr(lang, 'Symbole')}</label>
                        <select
                          value={liveOrderSymbol}
                          onChange={(e) => {
                            setLiveOrderSymbol(e.target.value);
                            setLiveOrderDraftCheck(null);
                          }}
                          className="w-full px-2.5 py-1.5 bg-[#080C0F] border border-white/10 rounded font-mono-tabular text-[#E8EEF2]"
                        >
                          {SYMBOLS.map((s) => (
                            <option key={s.id} value={s.id}>
                              {s.id}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="block text-[11px] text-[#8B98A4] mb-1">{tr(lang, "Type d'Ordre")}</label>
                        <select
                          value={liveOrderType}
                          onChange={(e) => {
                            setLiveOrderType(e.target.value as 'MARKET' | 'LIMIT');
                            setLiveOrderDraftCheck(null);
                          }}
                          className="w-full px-2.5 py-1.5 bg-[#080C0F] border border-white/10 rounded font-mono-tabular text-[#E8EEF2]"
                        >
                          <option value="MARKET">MARKET</option>
                          <option value="LIMIT">LIMIT</option>
                        </select>
                      </div>
                    </div>

                    <div className="grid grid-cols-3 gap-2.5">
                      <div>
                        <label className="block text-[11px] text-[#8B98A4] mb-1">{tr(lang, 'Montant')}</label>
                        <input
                          type="number"
                          step="any"
                          value={liveOrderAmount}
                          onChange={(e) => {
                            setLiveOrderAmount(e.target.value);
                            setLiveOrderDraftCheck(null);
                          }}
                          className="w-full px-2.5 py-1.5 bg-[#080C0F] border border-white/10 rounded font-mono-tabular text-[#E8EEF2]"
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] text-[#8B98A4] mb-1">{tr(lang, 'Mode Montant')}</label>
                        <select
                          value={liveOrderAmountMode}
                          onChange={(e) => {
                            setLiveOrderAmountMode(e.target.value as 'fixed' | 'percentage');
                            setLiveOrderDraftCheck(null);
                          }}
                          className="w-full px-2.5 py-1.5 bg-[#080C0F] border border-white/10 rounded text-[#E8EEF2]"
                        >
                          <option value="fixed">{tr(lang, 'USDT Fixe')}</option>
                          <option value="percentage">{tr(lang, '% Solde')}</option>
                        </select>
                      </div>
                      <div>
                        <label className="block text-[11px] text-[#8B98A4] mb-1">{tr(lang, 'Levier (1–125)')}</label>
                        <input
                          type="number"
                          min="1"
                          max="125"
                          value={liveOrderLeverage}
                          onChange={(e) => {
                            setLiveOrderLeverage(e.target.value);
                            setLiveOrderDraftCheck(null);
                          }}
                          className="w-full px-2.5 py-1.5 bg-[#080C0F] border border-white/10 rounded font-mono-tabular text-[#E8EEF2]"
                        />
                      </div>
                    </div>

                    {liveOrderType === 'LIMIT' && (
                      <div>
                        <label className="block text-[11px] text-[#8B98A4] mb-1">{tr(lang, "Prix Limite d'Entrée")}</label>
                        <input
                          type="number"
                          step="any"
                          value={liveOrderEntryPrice}
                          onChange={(e) => {
                            setLiveOrderEntryPrice(e.target.value);
                            setLiveOrderDraftCheck(null);
                          }}
                          placeholder="Ex: 82500"
                          className="w-full px-2.5 py-1.5 bg-[#080C0F] border border-white/10 rounded font-mono-tabular text-[#E8EEF2]"
                        />
                      </div>
                    )}

                    <div className="grid grid-cols-2 gap-2.5">
                      <div>
                        <label className="block text-[11px] text-[#8B98A4] mb-1">Stop Loss (SL)</label>
                        <input
                          type="number"
                          step="any"
                          value={liveOrderSL}
                          onChange={(e) => {
                            setLiveOrderSL(e.target.value);
                            setLiveOrderDraftCheck(null);
                          }}
                          placeholder={tr(lang, 'Prix SL...')}
                          className="w-full px-2.5 py-1.5 bg-[#080C0F] border border-white/10 rounded font-mono-tabular text-[#F04438]"
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] text-[#8B98A4] mb-1">Take Profit (TP)</label>
                        <input
                          type="number"
                          step="any"
                          value={liveOrderTP}
                          onChange={(e) => {
                            setLiveOrderTP(e.target.value);
                            setLiveOrderDraftCheck(null);
                          }}
                          placeholder={tr(lang, 'Prix TP...')}
                          className="w-full px-2.5 py-1.5 bg-[#080C0F] border border-white/10 rounded font-mono-tabular text-[#20C997]"
                        />
                      </div>
                    </div>

                    <div className="flex items-center justify-between gap-2 pt-1">
                      <div className="flex items-center gap-2">
                        <span className="text-[#8B98A4]">{lang === 'en' ? 'Margin:' : 'Marge :'}</span>
                        {(['ISOLATED', 'CROSS'] as const).map((mt) => (
                          <button
                            key={mt}
                            type="button"
                            onClick={() => setLiveOrderMarginType(mt)}
                            className={`px-2 py-1 rounded text-[11px] font-mono-tabular border ${
                              liveOrderMarginType === mt
                                ? 'bg-[#20C997]/20 border-[#20C997] text-[#20C997]'
                                : 'bg-[#080C0F] border-white/10 text-[#8B98A4]'
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
                      <div className="p-3 rounded-lg bg-[#080C0F] border border-[#20C997]/40 space-y-1 font-mono-tabular text-[11px]">
                        <div className="text-[#20C997] font-bold">{tr(lang, '✅ Pré-validation Binance réussie :')}</div>
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
                        disabled={isPending('live-order')}
                        onClick={() => handleLiveOrderAction('validate')}
                        className="flex-1 py-2.5 bg-[#172129] hover:bg-[#202A32] border border-white/10 text-[#E8EEF2] font-semibold rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {isPending('live-order') ? tr(lang, 'Traitement…') : tr(lang, "1. Valider l'Ordre")}
                      </button>
                      <button
                        type="button"
                        disabled={!liveOrderDraftCheck || isPending('live-order')}
                        onClick={() => handleLiveOrderAction('execute')}
                        className={`flex-1 py-2.5 font-semibold rounded-lg transition-colors ${
                          liveOrderDraftCheck
                            ? 'bg-[#20C997] hover:bg-[#1AA67D] text-[#080C0F]'
                            : 'bg-[#080C0F] text-[#6E7B88] border border-white/5 cursor-not-allowed'
                        }`}
                      >
                        {isPending('live-order') ? tr(lang, 'Exécution en cours…') : tr(lang, '2. Confirmer Envoi Réel')}
                      </button>
                    </div>
                  </div>
                </div>

                {/* Open Positions, Open Orders & Trade History (7 cols) */}
                <div id="at-positions" className="scroll-mt-24 lg:col-span-7 space-y-6">
                  {/* Open Positions (/positions, /close) */}
                  <div className="bg-[#0D1318] border border-white/[0.07] rounded-xl overflow-hidden">
                    <div className="px-5 py-4 border-b border-white/[0.07] flex items-center justify-between">
                      <h3 className="font-display font-semibold text-sm text-[#E8EEF2]">
                        {lang === 'en'
                          ? `Open AutoTrade & Live Positions (${
                              liveTrades.open.length +
                              ((liveAccount?.positions || []).filter(
                                (rp: any) =>
                                  !liveTrades.open.some(
                                    (lt: any) =>
                                      String(lt.symbol).toUpperCase() === String(rp.symbol).toUpperCase() &&
                                      String(rp.side || '').toUpperCase().startsWith(String(lt.direction || '').toUpperCase())
                                  )
                              ).length || 0)
                            }) — /positions`
                          : `Positions AutoTrade & Live Ouvertes (${
                              liveTrades.open.length +
                              ((liveAccount?.positions || []).filter(
                                (rp: any) =>
                                  !liveTrades.open.some(
                                    (lt: any) =>
                                      String(lt.symbol).toUpperCase() === String(rp.symbol).toUpperCase() &&
                                      String(rp.side || '').toUpperCase().startsWith(String(lt.direction || '').toUpperCase())
                                  )
                              ).length || 0)
                            }) — /positions`}
                      </h3>
                      <button
                        type="button"
                        onClick={loadLiveAccountAndOrders}
                        className="text-xs text-[#20C997] hover:underline"
                      >
                        {tr(lang, 'Actualiser')}
                      </button>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="bs-stack w-full text-left border-collapse text-xs">
                        <thead>
                          <tr className="border-b border-white/[0.07] text-[#6E7B88] font-mono-tabular uppercase">
                            <th className="py-2.5 px-4">{tr(lang, 'ID / Actif')}</th>
                            <th className="py-2.5 px-4">{tr(lang, 'Sens & Marché')}</th>
                            <th className="py-2.5 px-4 text-right">{tr(lang, 'Quantité')}</th>
                            <th className="py-2.5 px-4 text-right">{tr(lang, 'Entrée')}</th>
                            <th className="py-2.5 px-4 text-right">SL / TP</th>
                            <th className="py-2.5 px-4 text-right">{tr(lang, 'PNL actuel')}</th>
                            <th className="py-2.5 px-4 text-right">{tr(lang, 'Action (/close)')}</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-white/[0.05] font-mono-tabular">
                          {(() => {
                            const remoteUnmatched = (liveAccount?.positions || []).filter(
                              (rp: any) =>
                                !liveTrades.open.some(
                                  (lt: any) =>
                                    String(lt.symbol).toUpperCase() === String(rp.symbol).toUpperCase() &&
                                    String(rp.side || '').toUpperCase().startsWith(String(lt.direction || '').toUpperCase())
                                )
                            );
                            if (liveTrades.open.length === 0 && remoteUnmatched.length === 0) {
                              return (
                                <tr>
                                  <td colSpan={7} className="py-6 text-center text-[#6E7B88] font-sans">
                                    {tr(lang, 'Aucune position ouverte enregistrée localement ou sur Binance.')}
                                  </td>
                                </tr>
                              );
                            }
                            return (
                              <>
                                {liveTrades.open.map((t: any) => (
                                  <tr key={`local-${t.id}`} className="hover:bg-white/[0.02]">
                                    <td className="py-3 px-4 font-semibold text-[#E8EEF2]">
                                      #{t.id} {t.symbol}
                                    </td>
                                    <td className="py-3 px-4">
                                      <span className={t.direction === 'BUY' ? 'text-[#20C997]' : 'text-[#F04438]'}>
                                        {t.direction} x{t.leverage || 1}
                                      </span>{' '}
                                      <span className="text-[10px] text-[#6E7B88] uppercase">({t.market_type})</span>
                                    </td>
                                    <td className="py-3 px-4 text-right">{t.quantity}</td>
                                    <td className="py-3 px-4 text-right">{Number(t.entry_price || 0).toLocaleString()}</td>
                                    <td className="py-3 px-4 text-right">
                                      <span className="text-[#F04438]">{t.sl_price ?? '—'}</span> /{' '}
                                      <span className="text-[#20C997]">{t.tp_price ?? '—'}</span>
                                    </td>
                                    <td className="py-3 px-4 text-right whitespace-nowrap">
                                      {renderOpenPnl(
                                        computeOpenPnl(
                                          t.symbol,
                                          t.direction,
                                          t.entry_price,
                                          t.quantity,
                                          t.leverage,
                                          (liveAccount?.positions || []).find(
                                            (rp: any) =>
                                              String(rp.symbol).toUpperCase() === String(t.symbol).toUpperCase() &&
                                              String(rp.side || '').toUpperCase().startsWith(String(t.direction || '').toUpperCase())
                                          )?.unrealized_pnl
                                        )
                                      )}
                                    </td>
                                    <td className="py-3 px-4 text-right">
                                      <button
                                        type="button"
                                        onClick={() => handleCloseLivePosition(t.id, t.symbol, t.direction)}
                                        disabled={isPending(`live-close-${t.id}-${t.symbol}`)}
                                        className="px-2.5 py-1 bg-[#F04438]/15 hover:bg-[#F04438]/25 border border-[#F04438]/40 text-[#F97066] rounded text-[11px] disabled:opacity-50 disabled:cursor-not-allowed"
                                      >
                                        {isPending(`live-close-${t.id}-${t.symbol}`) ? tr(lang, 'Fermeture…') : <>{tr(lang, 'Fermer')} (#{t.id})</>}
                                      </button>
                                    </td>
                                  </tr>
                                ))}
                                {remoteUnmatched.map((rp: any) => {
                                  const dir = String(rp.side || '').toUpperCase().startsWith('SELL') ? 'SELL' : 'BUY';
                                  const remotePnl = computeOpenPnl(
                                    rp.symbol,
                                    dir,
                                    rp.entry_price,
                                    rp.quantity,
                                    rp.leverage,
                                    rp.unrealized_pnl
                                  );
                                  const upnl = remotePnl ? remotePnl.usdt : Number(rp.unrealized_pnl || 0);
                                  return (
                                    <tr key={`remote-${rp.symbol}-${dir}`} className="hover:bg-white/[0.02] bg-[#D6A84F]/[0.03]">
                                      <td className="py-3 px-4 font-semibold text-[#E8EEF2]">
                                        <span className="text-[#D6A84F] text-[10px] mr-1">[BINANCE]</span>
                                        {rp.symbol}
                                      </td>
                                      <td className="py-3 px-4">
                                        <span className={dir === 'BUY' ? 'text-[#20C997]' : 'text-[#F04438]'}>
                                          {dir} x{rp.leverage || 1}
                                        </span>{' '}
                                        <span className="text-[10px] text-[#6E7B88] uppercase">(futures)</span>
                                      </td>
                                      <td className="py-3 px-4 text-right">{rp.quantity}</td>
                                      <td className="py-3 px-4 text-right">{Number(rp.entry_price || 0).toLocaleString()}</td>
                                      <td className="py-3 px-4 text-right">
                                        <span className={upnl >= 0 ? 'text-[#20C997]' : 'text-[#F04438]'}>
                                          PnL: {upnl >= 0 ? '+' : ''}
                                          {upnl.toFixed(2)} USDT
                                        </span>
                                      </td>
                                      <td className="py-3 px-4 text-right whitespace-nowrap">{renderOpenPnl(remotePnl)}</td>
                                      <td className="py-3 px-4 text-right">
                                        <button
                                          type="button"
                                          onClick={() => handleCloseLivePosition(0, rp.symbol, dir)}
                                          disabled={isPending(`live-close-0-${rp.symbol}`)}
                                          className="px-2.5 py-1 bg-[#F04438]/15 hover:bg-[#F04438]/25 border border-[#F04438]/40 text-[#F97066] rounded text-[11px] disabled:opacity-50 disabled:cursor-not-allowed"
                                        >
                                          {isPending(`live-close-0-${rp.symbol}`) ? tr(lang, 'Fermeture…') : <>{tr(lang, 'Fermer')} ({rp.symbol})</>}
                                        </button>
                                      </td>
                                    </tr>
                                  );
                                })}
                              </>
                            );
                          })()}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* Open Binance Orders (live_orders / live_cancel_menu) */}
                  <div className="bg-[#0D1318] border border-white/[0.07] rounded-xl overflow-hidden">
                    <div className="px-5 py-4 border-b border-white/[0.07] flex items-center justify-between">
                      <h3 className="font-display font-semibold text-sm text-[#E8EEF2]">
                        {lang === 'en'
                          ? `Protective & Limit Orders Open on Binance (${liveOpenOrders.length})`
                          : `Ordres Protecteurs & Limites Ouverts sur Binance (${liveOpenOrders.length})`}
                      </h3>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="bs-stack w-full text-left border-collapse text-xs">
                        <thead>
                          <tr className="border-b border-white/[0.07] text-[#6E7B88] font-mono-tabular uppercase">
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
                              <td colSpan={5} className="py-5 text-center text-[#6E7B88] font-sans">
                                {tr(lang, 'Aucun ordre ouvert sur Binance actuellement.')}
                              </td>
                            </tr>
                          ) : (
                            liveOpenOrders.map((ord: any) => (
                              <tr key={ord.orderId} className="hover:bg-white/[0.02]">
                                <td className="py-2.5 px-4 font-semibold text-[#E8EEF2]">{ord.symbol}</td>
                                <td className="py-2.5 px-4">
                                  <span className={ord.side === 'BUY' ? 'text-[#20C997]' : 'text-[#F04438]'}>
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
                                    disabled={isPending(`live-cancel-${String(ord.orderId)}`)}
                                    className="px-2 py-1 bg-[#172129] hover:bg-[#F04438]/20 text-[#8B98A4] hover:text-[#F97066] rounded text-[11px] disabled:opacity-50 disabled:cursor-not-allowed"
                                  >
                                    {isPending(`live-cancel-${String(ord.orderId)}`) ? tr(lang, 'Annulation…') : tr(lang, 'Annuler')}
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
              <div className="bg-[#0D1318] border border-white/[0.07] rounded-xl overflow-hidden">
                <div className="px-5 py-4 border-b border-white/[0.07] flex items-center justify-between">
                  <div>
                    <h3 className="font-display font-semibold text-base text-[#E8EEF2]">
                      {lang === 'en' ? 'Validated Signals History' : 'Historique des Signaux Validés'} ({signalHistory.length})
                    </h3>
                    <p className="text-xs text-[#6E7B88]">
                      {tr(lang, 'Registre persistant des signaux générés par SignalEngine avec suivi de performance.')}
                    </p>
                  </div>
                </div>
                <div className="overflow-x-auto">
                  <table className="bs-stack w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="border-b border-white/[0.07] text-[#6E7B88] font-mono-tabular uppercase">
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
                          <td className="py-3 px-4 text-[#6E7B88]">#{sig.id.slice(0, 8)}</td>
                          <td className="py-3 px-4 font-semibold text-[#E8EEF2]">
                            {sig.symbol} • {sig.timeframe.toUpperCase()}
                          </td>
                          <td className="py-3 px-4">
                            <span className={sig.direction === 'BUY' ? 'text-[#20C997] font-bold' : 'text-[#F04438] font-bold'}>
                              {sig.direction}
                            </span>
                          </td>
                          <td className="py-3 px-4 text-right">{sig.score}/100</td>
                          <td className="py-3 px-4 text-right">{sig.entry_price?.toLocaleString()}</td>
                          <td className="py-3 px-4 text-right">
                            <span className="text-[#F04438]">{sig.sl?.toLocaleString() || '—'}</span> /{' '}
                            <span className="text-[#20C997]">{sig.tp?.toLocaleString() || '—'}</span>
                          </td>
                          <td className="py-3 px-4 text-right text-[#D6A84F]">
                            {sig.rr_ratio ? `1:${sig.rr_ratio.toFixed(2)}` : '—'}
                          </td>
                          <td className="py-3 px-4">
                            <span
                              className={`px-2 py-0.5 rounded text-[11px] uppercase ${
                                sig.status === 'win'
                                  ? 'bg-[#20C997]/15 text-[#20C997]'
                                  : sig.status === 'loss'
                                  ? 'bg-[#F04438]/15 text-[#F04438]'
                                  : 'bg-white/[0.06] text-[#8B98A4]'
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
                <div className="bg-[#0D1318] border border-white/[0.07] rounded-xl p-5 space-y-4">
                  <h3 className="font-display font-semibold text-base text-[#E8EEF2]">
                    {tr(lang, 'Abonnement PRO / VIP & Codes Promotionnels')}
                  </h3>
                  <form onSubmit={handleRedeemPromo} className="flex gap-2 text-xs">
                    <input
                      type="text"
                      value={promoCodeInput}
                      onChange={(e) => setPromoCodeInput(e.target.value)}
                      placeholder={tr(lang, 'Code Promo (ex: TEDDYPRO ou TEDDYVIP)')}
                      className="flex-1 px-3 py-2 bg-[#080C0F] border border-white/10 rounded-lg font-mono-tabular uppercase text-[#E8EEF2]"
                      required
                    />
                    <button
                      type="submit"
                      disabled={isPending('promo')}
                      className="px-4 py-2 bg-[#20C997] text-[#080C0F] font-semibold rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {isPending('promo') ? tr(lang, 'Vérification…') : tr(lang, 'Activer Code')}
                    </button>
                  </form>

                  <div className="grid grid-cols-2 gap-3 pt-2 text-xs">
                    <button
                      onClick={() => handleGenerateBinancePay('pro')}
                      disabled={isPending('binance-pay')}
                      className="p-3.5 rounded-lg bg-[#080C0F] border border-[#20C997]/40 hover:bg-[#20C997]/10 text-left space-y-1 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <div className="font-semibold text-[#20C997]">{tr(lang, 'Générer Mémo Binance Pay PRO')}</div>
                      <div className="font-mono-tabular text-[#E8EEF2]">{tr(lang, '19 USDT / mois')}</div>
                    </button>
                    <button
                      onClick={() => handleGenerateBinancePay('vip')}
                      disabled={isPending('binance-pay')}
                      className="p-3.5 rounded-lg bg-[#080C0F] border border-[#D6A84F]/40 hover:bg-[#D6A84F]/10 text-left space-y-1 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <div className="font-semibold text-[#D6A84F]">{tr(lang, 'Générer Mémo Binance Pay VIP')}</div>
                      <div className="font-mono-tabular text-[#E8EEF2]">{tr(lang, '49 USDT / mois')}</div>
                    </button>
                  </div>

                  {paymentInfo && (
                    <div className="p-4 rounded-lg bg-[#080C0F] border border-[#20C997]/40 space-y-1.5 text-xs font-mono-tabular">
                      <div className="text-[#20C997] font-semibold">{tr(lang, 'Instructions Binance Pay :')}</div>
                      <div>
                        {tr(lang, 'Binance ID destinataire :')}{' '}
                        <strong className="text-[#E8EEF2]">{paymentInfo.binance_id || tr(lang, 'Non configuré')}</strong>
                      </div>
                      <div>
                        {tr(lang, 'Montant à envoyer :')} <strong className="text-[#E8EEF2]">{paymentInfo.amount_usdt} USDT</strong>
                      </div>
                      <div>
                        {tr(lang, 'Mémo obligatoire :')} <strong className="text-[#D6A84F]">{paymentInfo.memo}</strong>
                      </div>
                    </div>
                  )}
                </div>

                {/* Security PIN Configuration */}
                <div className="bg-[#0D1318] border border-white/[0.07] rounded-xl p-5 space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="font-display font-semibold text-base text-[#E8EEF2]">
                      {lang === 'en' ? 'Security PIN Code (4-6 digits)' : 'Code PIN de Sécurité (4 à 6 chiffres)'}
                    </h3>
                    <span className="text-xs font-mono-tabular text-[#20C997]">
                      {user.has_pin ? tr(lang, '● PIN Configuré') : tr(lang, '○ Aucun PIN')}
                    </span>
                  </div>
                  <form onSubmit={handleSavePin} className="space-y-3 text-xs">
                    {user.has_pin && (
                      <div>
                        <label className="block text-[#8B98A4] mb-1">{tr(lang, 'Ancien Code PIN')}</label>
                        <input
                          type="password"
                          maxLength={6}
                          value={oldPin}
                          onChange={(e) => setOldPin(e.target.value)}
                          className="w-full px-3 py-2 bg-[#080C0F] border border-white/10 rounded-lg font-mono-tabular text-[#E8EEF2]"
                          required
                        />
                      </div>
                    )}
                    <div>
                      <label className="block text-[#8B98A4] mb-1">
                        {lang === 'en' ? 'New Security PIN (4 to 6 digits)' : 'Nouveau Code PIN (4 à 6 chiffres)'}
                      </label>
                      <input
                        type="password"
                        maxLength={6}
                        value={newPin}
                        onChange={(e) => setNewPin(e.target.value)}
                        placeholder="123456"
                        className="w-full px-3 py-2 bg-[#080C0F] border border-white/10 rounded-lg font-mono-tabular text-[#E8EEF2]"
                        required
                      />
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="submit"
                        disabled={isPending('save-pin')}
                        className="px-4 py-2 bg-[#172129] hover:bg-[#202A32] border border-white/10 rounded-lg text-[#E8EEF2] font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {isPending('save-pin') ? tr(lang, 'Enregistrement…') : tr(lang, 'Enregistrer le Code PIN')}
                      </button>
                      {user.has_pin && (
                        <>
                          <button
                            type="button"
                            onClick={handleResetPinLockout}
                            disabled={isPending('pin-unlock')}
                            className="px-3 py-2 bg-[#080C0F] hover:bg-white/[0.05] border border-white/15 rounded-lg text-[#8B98A4] hover:text-[#E8EEF2] disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            {lang === 'en' ? 'Reset PIN Lockout' : 'Débloquer essai PIN'}
                          </button>
                          <button
                            type="button"
                            onClick={async () => {
                              if (!newPin.trim()) {
                                showToast(
                                  lang === 'en'
                                    ? 'Enter a new 6-digit PIN above first.'
                                    : 'Saisissez d’abord votre nouveau code PIN (6 chiffres) ci-dessus.',
                                  'info'
                                );
                                return;
                              }
                              try {
                                const res = await apiFetch('/api/user/pin', {
                                  method: 'POST',
                                  body: JSON.stringify({ action: 'reset_force', pin: newPin.trim() }),
                                });
                                if (res.user) setUser(res.user);
                                setNewPin('');
                                setOldPin('');
                                showToast(res.message, 'success');
                              } catch (err: any) {
                                showToast(err.message, 'error');
                              }
                            }}
                            className="px-3 py-2 bg-[#D6A84F]/15 hover:bg-[#D6A84F]/25 border border-[#D6A84F]/40 rounded-lg text-[#E2BC6A]"
                          >
                            {lang === 'en' ? 'Force Reset Forgotten PIN' : 'Réinitialiser PIN oublié'}
                          </button>
                        </>
                      )}
                    </div>
                  </form>
                </div>
              </div>

              {/* Right: Direct Admin Support Messaging */}
              <div className="lg:col-span-6 bg-[#0D1318] border border-white/[0.07] rounded-xl p-5 space-y-4">
                <h3 className="font-display font-semibold text-base text-[#E8EEF2]">
                  {tr(lang, 'Support Direct Administrateur')}
                </h3>
                <form onSubmit={handleCreateSupportTicket} className="space-y-3 text-xs">
                  <div>
                    <label className="block text-[#8B98A4] mb-1">{tr(lang, 'Sujet')}</label>
                    <input
                      type="text"
                      value={ticketSubject}
                      onChange={(e) => setTicketSubject(e.target.value)}
                      placeholder={tr(lang, 'Validation paiement / Question stratégie...')}
                      className="w-full px-3 py-2 bg-[#080C0F] border border-white/10 rounded-lg text-[#E8EEF2]"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-[#8B98A4] mb-1">{tr(lang, 'Message')}</label>
                    <textarea
                      rows={3}
                      value={ticketMessage}
                      onChange={(e) => setTicketMessage(e.target.value)}
                      placeholder={tr(lang, 'Décrivez votre demande...')}
                      className="w-full px-3 py-2 bg-[#080C0F] border border-white/10 rounded-lg text-[#E8EEF2]"
                      required
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={isPending('support-ticket')}
                    className="px-4 py-2 bg-[#20C997] text-[#080C0F] font-semibold rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isPending('support-ticket') ? tr(lang, 'Envoi…') : tr(lang, "Envoyer à l'Administrateur")}
                  </button>
                </form>

                <div className="space-y-2.5 pt-3 border-t border-white/[0.07]">
                  <div className="text-xs font-semibold text-[#8B98A4]">{tr(lang, 'Vos échanges récents :')}</div>
                  {tickets.map((t) => (
                    <div key={t.id} className="p-3 rounded-lg bg-[#080C0F] border border-white/[0.06] space-y-1.5 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-[#E8EEF2]">{t.subject}</span>
                        <span className="font-mono-tabular text-[11px] text-[#20C997] uppercase">{t.status}</span>
                      </div>
                      <p className="text-[#8B98A4]">{t.message}</p>
                      {t.admin_reply && (
                        <div className="p-2 rounded bg-[#20C997]/10 border border-[#20C997]/30 text-[#32D583]">
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
              {/* Direct Banner to Open Users 360° Dossier & Public Terms */}
              <div className="bg-[#0D1318] border border-[#20C997]/40 rounded-xl p-4 flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-[#20C997]/15 border border-[#20C997]/40 flex items-center justify-center text-[#20C997]">
                    <Users className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="text-sm font-display font-bold text-[#E8EEF2]">
                      {tr(lang, 'Dossier Utilisateurs 360° & Consentement CGU')}
                    </div>
                    <div className="text-xs text-[#8B98A4]">
                      {tr(
                        lang,
                        'Consultez toutes les informations par utilisateur : appareil, OS, navigateur, batterie, IP, géolocalisation GPS/IP, preuves CGU et trading.'
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setActiveTab('users_intelligence')}
                    className="px-3.5 py-2 rounded-lg bg-[#20C997] hover:bg-[#1AA67D] text-[#080C0F] font-semibold text-xs flex items-center gap-1.5"
                  >
                    <Users className="w-4 h-4" />
                    <span>{tr(lang, 'Ouvrir Utilisateurs 360°')}</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setActiveTab('terms')}
                    className="px-3 py-2 rounded-lg bg-[#172129] hover:bg-[#202A32] border border-white/10 text-[#E2BC6A] font-semibold text-xs flex items-center gap-1.5"
                  >
                    <Shield className="w-4 h-4" />
                    <span>{tr(lang, 'Voir les CGU publiques')}</span>
                  </button>
                </div>
              </div>

              {/* Top Summary Metrics for Admin */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                <div className="bg-[#0D1318] border border-white/[0.07] rounded-xl p-4">
                  <div className="text-[11px] text-[#6E7B88] uppercase font-mono-tabular">{tr(lang, 'Total Comptes')}</div>
                  <div className="text-xl font-bold font-mono-tabular text-[#E8EEF2] mt-1">
                    {(adminData?.users || []).length}
                  </div>
                </div>
                <div className="bg-[#0D1318] border border-[#D6A84F]/30 rounded-xl p-4">
                  <div className="text-[11px] text-[#D6A84F] uppercase font-mono-tabular">
                    {tr(lang, "En Attente d'Approbation")}
                  </div>
                  <div className="text-xl font-bold font-mono-tabular text-[#D6A84F] mt-1">
                    {(adminData?.users || []).filter((u: any) => u.account_status === 'PENDING_APPROVAL').length}
                  </div>
                </div>
                <div className="bg-[#0D1318] border border-[#20C997]/30 rounded-xl p-4">
                  <div className="text-[11px] text-[#20C997] uppercase font-mono-tabular">
                    {tr(lang, 'Comptes Approuvés')}
                  </div>
                  <div className="text-xl font-bold font-mono-tabular text-[#20C997] mt-1">
                    {(adminData?.users || []).filter((u: any) => u.account_status === 'APPROVED').length}
                  </div>
                </div>
                <div className="bg-[#0D1318] border border-[#F04438]/30 rounded-xl p-4">
                  <div className="text-[11px] text-[#F97066] uppercase font-mono-tabular">
                    {tr(lang, 'Suspendus / Refusés')}
                  </div>
                  <div className="text-xl font-bold font-mono-tabular text-[#F97066] mt-1">
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
                <div className="lg:col-span-8 bg-[#0D1318] border border-white/[0.07] rounded-xl p-5 space-y-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <h3 className="font-display font-semibold text-base text-[#E8EEF2]">
                        {tr(lang, 'Contrôle des Accès, Approbation des Comptes & Quotas Utilisateurs')}
                      </h3>
                      <p className="text-xs text-[#6E7B88]">
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
                              ? 'bg-[#20C997]/20 border-[#20C997] text-[#20C997]'
                              : 'bg-[#080C0F] border-white/10 text-[#8B98A4] hover:text-[#E8EEF2]'
                          }`}
                        >
                          {f.label}
                        </button>
                      ))}
                      <button
                        onClick={loadAdminOverview}
                        className="px-2.5 py-1 bg-[#172129] hover:bg-[#202A32] rounded text-xs text-[#20C997] flex items-center gap-1"
                      >
                        <RefreshCw className="w-3.5 h-3.5" /> {tr(lang, 'Actualiser')}
                      </button>
                    </div>
                  </div>

                  {/* Per-User Quota Editor Modal/Drawer Inline */}
                  {editingQuotasUid !== null && (
                    <div className="p-4 rounded-xl bg-[#080C0F] border border-[#20C997]/40 space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="text-xs font-semibold text-[#20C997]">
                          {lang === 'en'
                            ? `Quota Configuration — User #${editingQuotasUid}`
                            : `Configuration des quotas — Utilisateur #${editingQuotasUid}`}
                        </div>
                        <button
                          type="button"
                          onClick={() => setEditingQuotasUid(null)}
                          className="text-xs text-[#8B98A4] hover:text-[#E8EEF2]"
                        >
                          {tr(lang, 'Fermer')}
                        </button>
                      </div>
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                        <div>
                          <label className="block text-[11px] text-[#8B98A4] mb-1">{tr(lang, 'Analyses / jour')}</label>
                          <input
                            type="number"
                            min={1}
                            value={quotaForm.daily_analyses}
                            onChange={(e) =>
                              setQuotaForm((prev) => ({ ...prev, daily_analyses: parseInt(e.target.value, 10) || 1 }))
                            }
                            className="w-full px-2.5 py-1.5 bg-[#0D1318] border border-white/10 rounded font-mono-tabular text-[#E8EEF2]"
                          />
                        </div>
                        <div>
                          <label className="block text-[11px] text-[#8B98A4] mb-1">{tr(lang, 'Scans / jour')}</label>
                          <input
                            type="number"
                            min={1}
                            value={quotaForm.daily_scans}
                            onChange={(e) =>
                              setQuotaForm((prev) => ({ ...prev, daily_scans: parseInt(e.target.value, 10) || 1 }))
                            }
                            className="w-full px-2.5 py-1.5 bg-[#0D1318] border border-white/10 rounded font-mono-tabular text-[#E8EEF2]"
                          />
                        </div>
                        <div>
                          <label className="block text-[11px] text-[#8B98A4] mb-1">{tr(lang, 'Alertes actives max')}</label>
                          <input
                            type="number"
                            min={1}
                            value={quotaForm.max_alerts}
                            onChange={(e) =>
                              setQuotaForm((prev) => ({ ...prev, max_alerts: parseInt(e.target.value, 10) || 1 }))
                            }
                            className="w-full px-2.5 py-1.5 bg-[#0D1318] border border-white/10 rounded font-mono-tabular text-[#E8EEF2]"
                          />
                        </div>
                        <div>
                          <label className="block text-[11px] text-[#8B98A4] mb-1">{tr(lang, 'Paper Trades / jour')}</label>
                          <input
                            type="number"
                            min={1}
                            value={quotaForm.max_paper_trades}
                            onChange={(e) =>
                              setQuotaForm((prev) => ({ ...prev, max_paper_trades: parseInt(e.target.value, 10) || 1 }))
                            }
                            className="w-full px-2.5 py-1.5 bg-[#0D1318] border border-white/10 rounded font-mono-tabular text-[#E8EEF2]"
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
                          className="px-4 py-1.5 bg-[#20C997] hover:bg-[#1AA67D] text-[#080C0F] font-semibold text-xs rounded-lg"
                        >
                          {tr(lang, 'Enregistrer les Quotas')}
                        </button>
                      </div>
                    </div>
                  )}

                  <div className="overflow-x-auto">
                    <table className="bs-stack w-full text-left border-collapse text-xs">
                      <thead>
                        <tr className="border-b border-white/[0.07] text-[#6E7B88] font-mono-tabular uppercase">
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
                                  <div className="font-semibold text-[#E8EEF2]">
                                    {u.display_name || u.username || `Trader #${u.user_id}`}
                                  </div>
                                  <div className="text-[11px] text-[#8B98A4]">{u.email || tr(lang, 'Compte Telegram')}</div>
                                  <div className="text-[10px] text-[#6E7B88]">
                                    ID: #{u.user_id} {u.auth_provider ? `• ${u.auth_provider.toUpperCase()}` : ''}
                                  </div>
                                </td>
                                <td className="py-3 px-3 space-y-1">
                                  <div>
                                    <span
                                      className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${
                                        status === 'APPROVED'
                                          ? 'bg-[#20C997]/15 border-[#20C997]/40 text-[#20C997]'
                                          : status === 'PENDING_APPROVAL'
                                          ? 'bg-[#D6A84F]/15 border-[#D6A84F]/40 text-[#D6A84F]'
                                          : 'bg-[#F04438]/15 border-[#F04438]/40 text-[#F97066]'
                                      }`}
                                    >
                                      {status}
                                    </span>
                                  </div>
                                  <div className="text-[11px] uppercase text-[#20C997] font-bold">
                                    {lang === 'en' ? 'Role:' : 'Rôle :'} {u.role} {u.memo ? `• Memo: ${u.memo}` : ''}
                                  </div>
                                </td>
                                <td className="py-3 px-3 text-[11px] space-y-0.5">
                                  <div>
                                    Analyses: <span className="text-[#E8EEF2]">{qu.analyses_used}</span>/{q.daily_analyses}
                                  </div>
                                  <div>
                                    Scans: <span className="text-[#E8EEF2]">{qu.scans_used}</span>/{q.daily_scans}
                                  </div>
                                  <div>
                                    {lang === 'en' ? 'Max alerts:' : 'Alertes max:'}{' '}
                                    <span className="text-[#E8EEF2]">{q.max_alerts}</span> • Paper:{' '}
                                    <span className="text-[#E8EEF2]">{qu.paper_trades_used}</span>/{q.max_paper_trades}
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
                                    className="text-[10px] text-[#20C997] hover:underline"
                                  >
                                    {tr(lang, 'Modifier quotas')}
                                  </button>
                                </td>
                                <td className="py-3 px-3 text-[10px] text-[#8B98A4] space-y-1">
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
                                        className="px-2.5 py-1 bg-[#20C997] hover:bg-[#1AA67D] text-[#080C0F] font-bold rounded text-[10px]"
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
                                        className="px-2 py-1 bg-[#F04438]/20 hover:bg-[#F04438]/30 border border-[#F04438]/40 text-[#F97066] rounded text-[10px]"
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
                                        className="px-2 py-1 bg-[#D6A84F]/20 hover:bg-[#D6A84F]/30 border border-[#D6A84F]/40 text-[#D6A84F] rounded text-[10px]"
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
                                        className="px-2 py-1 bg-[#20C997]/20 hover:bg-[#20C997]/30 border border-[#20C997]/40 text-[#20C997] rounded text-[10px]"
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
                                            ? 'bg-[#20C997]/25 text-[#20C997] border border-[#20C997]/40'
                                            : 'bg-[#172129] hover:bg-[#202A32] text-[#E8EEF2]'
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
                                        className="px-2 py-1 bg-[#20C997] text-[#080C0F] font-semibold rounded text-[10px]"
                                      >
                                        {tr(lang, 'Valider Pay')}
                                      </button>
                                    )}
                                    {!u.is_admin && (
                                      <button
                                        onClick={() =>
                                          apiFetch('/api/admin/user-role', {
                                            method: 'POST',
                                            body: JSON.stringify({
                                              target_user_id: u.user_id,
                                              action: 'delete',
                                            }),
                                          }).then((res) => {
                                            showToast(res.message, 'info');
                                            loadAdminOverview();
                                          })
                                        }
                                        title={lang === 'en' ? 'Delete user account' : 'Supprimer le compte utilisateur'}
                                        className="px-2 py-1 bg-[#F04438]/15 hover:bg-[#F04438]/25 border border-[#F04438]/30 text-[#F97066] rounded text-[10px] inline-flex items-center gap-1"
                                      >
                                        <Trash2 className="w-3 h-3" />
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
                  <div className="bg-[#0D1318] border border-white/[0.07] rounded-xl p-5 space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="font-display font-semibold text-base text-[#E8EEF2] flex items-center gap-2">
                        <Shield className="w-4 h-4 text-[#20C997]" />
                        <span>{tr(lang, 'Journal de Sécurité & Accès')}</span>
                      </h3>
                      <span className="text-[10px] font-mono-tabular text-[#6E7B88]">
                        {(adminData?.security_events || []).length} {lang === 'en' ? 'events' : 'événements'}
                      </span>
                    </div>
                    <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                      {(adminData?.security_events || []).length === 0 ? (
                        <div className="text-xs text-[#6E7B88]">
                          {tr(lang, 'Aucun événement de sécurité enregistré.')}
                        </div>
                      ) : (
                        (adminData?.security_events || []).map((ev: SecurityEvent) => (
                          <div
                            key={ev.id}
                            className="p-2.5 rounded-lg bg-[#080C0F] border border-white/[0.06] text-[11px] space-y-1"
                          >
                            <div className="flex items-center justify-between font-mono-tabular">
                              <span
                                className={`font-bold ${
                                  ev.severity === 'critical'
                                    ? 'text-[#F97066]'
                                    : ev.severity === 'warning'
                                    ? 'text-[#D6A84F]'
                                    : 'text-[#20C997]'
                                }`}
                              >
                                {ev.event_type}
                              </span>
                              <span className="text-[10px] text-[#6E7B88]">
                                {ev.created_at
                                  ? new Date(Number(ev.created_at) * 1000).toLocaleTimeString(
                                      lang === 'en' ? 'en-US' : 'fr-FR'
                                    )
                                  : ''}
                              </span>
                            </div>
                            <div className="text-[#8B98A4]">{ev.details}</div>
                            <div className="text-[10px] text-[#6E7B88] font-mono-tabular">
                              {ev.email ? `Email: ${ev.email} • ` : ''}
                              {ev.user_id ? `UID: #${ev.user_id} • ` : ''}
                              IP: {ev.ip_address || '—'}
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>

                  <div className="bg-[#0D1318] border border-white/[0.07] rounded-xl p-5 space-y-4">
                    <h3 className="font-display font-semibold text-base text-[#E8EEF2]">
                      {tr(lang, 'Diagnostic Système (Log Doctor)')}
                    </h3>
                    <div className="flex gap-2 text-xs">
                      <input
                        type="text"
                        value={doctorQuestion}
                        onChange={(e) => setDoctorQuestion(e.target.value)}
                        placeholder={tr(lang, 'Posez une question diagnostic (ex: erreur Binance, DB, Telegram)...')}
                        className="flex-1 px-3 py-2 bg-[#080C0F] border border-white/10 rounded-lg text-[#E8EEF2]"
                      />
                      <button
                        onClick={() =>
                          runAction('log-doctor', en ? 'Analyzing logs…' : 'Analyse des logs…', async () => {
                            try {
                              const r = await apiFetch('/api/admin/log-doctor', {
                                method: 'POST',
                                body: JSON.stringify({ question: doctorQuestion }),
                              });
                              setDoctorReport(r.report);
                            } catch (err: any) {
                              showToast(err.message, 'error');
                            }
                          })
                        }
                        disabled={isPending('log-doctor')}
                        className="px-3.5 py-2 bg-[#20C997] text-[#080C0F] font-semibold rounded-lg disabled:opacity-60 disabled:cursor-not-allowed"
                      >
                        {isPending('log-doctor') ? tr(lang, 'Traitement…') : tr(lang, 'Analyser')}
                      </button>
                    </div>
                    <pre className="p-3.5 rounded-lg bg-[#080C0F] border border-white/[0.06] text-[11px] font-mono-tabular text-[#8B98A4] whitespace-pre-wrap max-h-64 overflow-y-auto">
                      {doctorReport || tr(lang, 'Chargement du diagnostic...')}
                    </pre>
                  </div>

                  {/* Admin Broadcast */}
                  <div className="bg-[#0D1318] border border-white/[0.07] rounded-xl p-5 space-y-3">
                    <h3 className="font-display font-semibold text-base text-[#E8EEF2]">
                      {tr(lang, 'Diffusion Globale (Broadcast)')}
                    </h3>
                    <input
                      type="text"
                      value={broadcastTitle}
                      onChange={(e) => setBroadcastTitle(e.target.value)}
                      placeholder={tr(lang, "Titre de l'annonce...")}
                      className="w-full px-3 py-2 bg-[#080C0F] border border-white/10 rounded-lg text-xs text-[#E8EEF2]"
                    />
                    <textarea
                      rows={2}
                      value={broadcastBody}
                      onChange={(e) => setBroadcastBody(e.target.value)}
                      placeholder={tr(lang, 'Message diffusé à tous les utilisateurs...')}
                      className="w-full px-3 py-2 bg-[#080C0F] border border-white/10 rounded-lg text-xs text-[#E8EEF2]"
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
                      className="w-full py-2 bg-[#D6A84F] text-[#080C0F] font-semibold text-xs rounded-lg"
                    >
                      {tr(lang, 'Diffuser à tous les comptes')}
                    </button>
                  </div>
                </div>
              </div>

              {/* =========================================================
                  ADMIN OPERATIONS, SUPPORT INBOX, GLOBAL TRADES & TOOLKIT
                 ========================================================= */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                {/* 1. Admin Support Tickets Inbox & Reply */}
                <div className="lg:col-span-6 bg-[#0D1318] border border-white/[0.07] rounded-xl p-5 space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="font-display font-semibold text-base text-[#E8EEF2] flex items-center gap-2">
                      <MessageSquare className="w-4 h-4 text-[#20C997]" />
                      <span>
                        {lang === 'en'
                          ? 'Support Tickets & User Requests'
                          : 'Boîte de Réception Support & Demandes Utilisateurs'}
                      </span>
                    </h3>
                    <span className="text-xs font-mono-tabular text-[#6E7B88]">
                      {tickets.length} {lang === 'en' ? 'ticket(s)' : 'ticket(s)'}
                    </span>
                  </div>
                  <div className="space-y-3 max-h-96 overflow-y-auto pr-1">
                    {tickets.length === 0 ? (
                      <div className="text-xs text-[#6E7B88]">
                        {lang === 'en' ? 'No support tickets opened yet.' : 'Aucun ticket support ouvert pour le moment.'}
                      </div>
                    ) : (
                      tickets.map((t) => (
                        <div
                          key={t.id}
                          className="p-3.5 rounded-lg bg-[#080C0F] border border-white/[0.07] space-y-2 text-xs"
                        >
                          <div className="flex items-center justify-between">
                            <div>
                              <span className="font-semibold text-[#E8EEF2]">{t.subject}</span>
                              <span className="ml-2 text-[11px] font-mono-tabular text-[#6E7B88]">
                                {t.username || `#${t.user_id}`} (UID #{t.user_id})
                              </span>
                            </div>
                            <span
                              className={`px-2 py-0.5 rounded text-[10px] font-mono-tabular uppercase ${
                                t.status === 'answered'
                                  ? 'bg-[#20C997]/15 text-[#20C997]'
                                  : 'bg-[#D6A84F]/15 text-[#D6A84F]'
                              }`}
                            >
                              {t.status}
                            </span>
                          </div>
                          <p className="text-[#8B98A4]">{t.message}</p>
                          {t.admin_reply && (
                            <div className="p-2 rounded bg-[#20C997]/10 border border-[#20C997]/30 text-[#32D583]">
                              <strong>{tr(lang, 'Réponse Admin :')}</strong> {t.admin_reply}
                            </div>
                          )}
                          <div className="flex gap-2 pt-1">
                            <input
                              type="text"
                              value={adminReplyMap[t.id] || ''}
                              onChange={(e) =>
                                setAdminReplyMap((prev) => ({ ...prev, [t.id]: e.target.value }))
                              }
                              placeholder={
                                lang === 'en' ? 'Write a reply to this user...' : 'Répondre à cet utilisateur...'
                              }
                              className="flex-1 px-2.5 py-1.5 bg-[#0D1318] border border-white/10 rounded text-xs text-[#E8EEF2]"
                            />
                            <button
                              type="button"
                              onClick={() => {
                                const replyText = (adminReplyMap[t.id] || '').trim();
                                if (!replyText) return;
                                apiFetch('/api/support/tickets', {
                                  method: 'POST',
                                  body: JSON.stringify({
                                    action: 'reply',
                                    ticket_id: t.id,
                                    reply: replyText,
                                  }),
                                })
                                  .then((res) => {
                                    setAdminReplyMap((prev) => ({ ...prev, [t.id]: '' }));
                                    showToast(res.message, 'success');
                                    loadTickets();
                                  })
                                  .catch((err) => showToast(err.message, 'error'));
                              }}
                              className="px-3 py-1.5 bg-[#20C997] hover:bg-[#1AA67D] text-[#080C0F] font-semibold rounded text-xs"
                            >
                              {lang === 'en' ? 'Reply' : 'Répondre'}
                            </button>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>

                {/* 2. Global AutoTrade Supervision, Memo Finder & Signal Maintenance */}
                <div className="lg:col-span-6 space-y-6">
                  {/* Global AutoTrade Stats & Open Trades (/trading_stats, /trades, /forceclose) */}
                  <div className="bg-[#0D1318] border border-white/[0.07] rounded-xl p-5 space-y-4">
                    <div className="flex items-center justify-between">
                      <h3 className="font-display font-semibold text-base text-[#E8EEF2]">
                        {lang === 'en'
                          ? 'Global AutoTrade Supervision & Force Close'
                          : 'Supervision Globale AutoTrade & Clôture Forcée'}
                      </h3>
                      <span className="text-[11px] font-mono-tabular text-[#20C997]">
                        {lang === 'en' ? 'Source:' : 'Source :'}{' '}
                        {(adminData?.active_data_source || 'binance').toUpperCase()}
                      </span>
                    </div>

                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs font-mono-tabular">
                      <div className="p-2.5 rounded-lg bg-[#080C0F] border border-white/[0.06]">
                        <div className="text-[10px] text-[#6E7B88]">
                          {lang === 'en' ? 'AutoTrade ON' : 'AutoTrade Actifs'}
                        </div>
                        <div className="text-sm font-bold text-[#20C997] mt-0.5">
                          {adminData?.global_trading_stats?.active_auto_users ?? 0}
                        </div>
                      </div>
                      <div className="p-2.5 rounded-lg bg-[#080C0F] border border-white/[0.06]">
                        <div className="text-[10px] text-[#6E7B88]">
                          {lang === 'en' ? 'Open Trades' : 'Positions Ouvertes'}
                        </div>
                        <div className="text-sm font-bold text-[#E8EEF2] mt-0.5">
                          {adminData?.global_trading_stats?.open_trades_count ?? 0}
                        </div>
                      </div>
                      <div className="p-2.5 rounded-lg bg-[#080C0F] border border-white/[0.06]">
                        <div className="text-[10px] text-[#6E7B88]">Win Rate</div>
                        <div className="text-sm font-bold text-[#E8EEF2] mt-0.5">
                          {adminData?.global_trading_stats?.win_rate ?? 0}%
                        </div>
                      </div>
                      <div className="p-2.5 rounded-lg bg-[#080C0F] border border-white/[0.06]">
                        <div className="text-[10px] text-[#6E7B88]">
                          {lang === 'en' ? 'Realized PnL' : 'PnL Réalisé'}
                        </div>
                        <div
                          className={`text-sm font-bold mt-0.5 ${
                            (adminData?.global_trading_stats?.total_pnl_usdt || 0) >= 0
                              ? 'text-[#20C997]'
                              : 'text-[#F97066]'
                          }`}
                        >
                          {(adminData?.global_trading_stats?.total_pnl_usdt || 0) >= 0 ? '+' : ''}
                          {adminData?.global_trading_stats?.total_pnl_usdt ?? 0} USDT
                        </div>
                      </div>
                    </div>

                    {(adminData?.global_open_trades || []).length > 0 && (
                      <div className="space-y-2 max-h-44 overflow-y-auto">
                        {(adminData?.global_open_trades || []).map((gt: any) => (
                          <div
                            key={gt.id}
                            className="p-2.5 rounded-lg bg-[#080C0F] border border-white/[0.06] flex items-center justify-between text-xs font-mono-tabular"
                          >
                            <div>
                              <span className="text-[#20C997] font-bold">#{gt.id}</span> • UID #{gt.user_id} •{' '}
                              <span className="text-[#E8EEF2] font-semibold">{gt.symbol}</span> ({gt.direction}){' '}
                              qty={gt.quantity} @ {gt.entry_price}
                            </div>
                            <button
                              type="button"
                              onClick={() =>
                                apiFetch('/api/admin/operations', {
                                  method: 'POST',
                                  body: JSON.stringify({
                                    operation: 'force_close_trade',
                                    trade_id: gt.id,
                                  }),
                                })
                                  .then((res) => {
                                    showToast(res.message, 'success');
                                    loadAdminOverview();
                                  })
                                  .catch((err) => showToast(err.message, 'error'))
                              }
                              className="px-2.5 py-1 bg-[#F04438]/20 hover:bg-[#F04438]/30 border border-[#F04438]/40 text-[#F97066] rounded text-[10px] font-semibold"
                            >
                              {lang === 'en' ? 'Force Close' : 'Forcer Clôture'}
                            </button>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Data Source Switch, Memo Finder & Signal Maintenance Actions */}
                    <div className="pt-2 border-t border-white/[0.07] space-y-3">
                      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                        <span className="text-[#8B98A4]">
                          {lang === 'en' ? 'Market Data Source (/switchapi):' : 'Source de données marché (/switchapi) :'}
                        </span>
                        <div className="flex gap-1.5">
                          {(['binance', 'twelve', 'real'] as const).map((src) => (
                            <button
                              key={src}
                              type="button"
                              onClick={() =>
                                apiFetch('/api/admin/operations', {
                                  method: 'POST',
                                  body: JSON.stringify({ operation: 'switch_api', source: src }),
                                })
                                  .then((res) => {
                                    showToast(res.message, 'success');
                                    loadAdminOverview();
                                  })
                                  .catch((err) => showToast(err.message, 'error'))
                              }
                              className={`px-2.5 py-1 rounded text-[11px] font-mono-tabular uppercase border ${
                                (adminData?.active_data_source || 'binance') === src
                                  ? 'bg-[#20C997]/20 border-[#20C997] text-[#20C997]'
                                  : 'bg-[#080C0F] border-white/10 text-[#8B98A4] hover:text-[#E8EEF2]'
                              }`}
                            >
                              {src}
                            </button>
                          ))}
                        </div>
                      </div>

                      {/* Find Memo & Confirm Payment (/find_memo, /confirm_payment) */}
                      <div className="flex flex-wrap gap-2 text-xs">
                        <input
                          type="text"
                          value={adminMemoSearch}
                          onChange={(e) => setAdminMemoSearch(e.target.value)}
                          placeholder={
                            lang === 'en'
                              ? 'Search Binance Pay Memo (e.g. TEDDY-PRO-...)'
                              : 'Rechercher un mémo Binance Pay (ex: TEDDY-PRO-...)'
                          }
                          className="flex-1 px-3 py-1.5 bg-[#080C0F] border border-white/10 rounded-lg font-mono-tabular text-[#E8EEF2]"
                        />
                        <button
                          type="button"
                          onClick={() =>
                            apiFetch('/api/admin/operations', {
                              method: 'POST',
                              body: JSON.stringify({ operation: 'find_memo', memo: adminMemoSearch }),
                            })
                              .then((res) => {
                                setAdminFoundMemoUid(res.found_user_id || null);
                                showToast(res.message, res.ok ? 'success' : 'info');
                              })
                              .catch((err) => showToast(err.message, 'error'))
                          }
                          className="px-3 py-1.5 bg-[#172129] hover:bg-[#202A32] border border-white/10 rounded-lg text-[#E8EEF2] font-semibold"
                        >
                          {lang === 'en' ? 'Find Memo' : 'Chercher Mémo'}
                        </button>
                        {adminFoundMemoUid && (
                          <button
                            type="button"
                            onClick={() =>
                              apiFetch('/api/admin/user-role', {
                                method: 'POST',
                                body: JSON.stringify({
                                  target_user_id: adminFoundMemoUid,
                                  action: 'confirm_binance',
                                }),
                              }).then((res) => {
                                showToast(res.message, 'success');
                                setAdminFoundMemoUid(null);
                                loadAdminOverview();
                              })
                            }
                            className="px-3 py-1.5 bg-[#20C997] text-[#080C0F] font-bold rounded-lg"
                          >
                            {lang === 'en'
                              ? `Confirm PRO #${adminFoundMemoUid}`
                              : `Activer PRO #${adminFoundMemoUid}`}
                          </button>
                        )}
                      </div>

                      {/* Signal History Maintenance Buttons (/exportsignals, /refreshhistory, /cleanwaits, /clearhistory) */}
                      <div className="flex flex-wrap gap-2 pt-1">
                        <button
                          type="button"
                          onClick={() =>
                            runAction('export-signals', en ? 'Exporting signals…' : 'Export des signaux…', async () => {
                              try {
                                const res = await apiFetch('/api/admin/operations', {
                                  method: 'POST',
                                  body: JSON.stringify({ operation: 'export_signals_csv' }),
                                });
                                if (res.csv) {
                                  const blob = new Blob([res.csv], { type: 'text/csv;charset=utf-8;' });
                                  const url = URL.createObjectURL(blob);
                                  const a = document.createElement('a');
                                  a.href = url;
                                  a.download = res.filename || 'signals_export.csv';
                                  document.body.appendChild(a);
                                  a.click();
                                  document.body.removeChild(a);
                                  URL.revokeObjectURL(url);
                                  showToast(res.message || (en ? 'Export downloaded.' : 'Export téléchargé.'), 'success');
                                } else {
                                  // Aucun fichier reçu : ce n'est pas un succès, on affiche le message du backend tel quel.
                                  showToast(res.message || (en ? 'No data to export.' : 'Aucune donnée à exporter.'), 'info');
                                }
                              } catch (err: any) {
                                showToast(err.message, 'error');
                              }
                            })
                          }
                          disabled={isPending('export-signals')}
                          className="px-3 py-1.5 bg-[#20C997]/15 hover:bg-[#20C997]/25 border border-[#20C997]/40 text-[#20C997] rounded-lg text-xs font-semibold disabled:opacity-60 disabled:cursor-not-allowed"
                        >
                          {isPending('export-signals') ? tr(lang, 'Traitement…') : lang === 'en' ? 'Export Signals CSV' : 'Exporter Signaux CSV'}
                        </button>
                        <button
                          type="button"
                          onClick={() =>
                            apiFetch('/api/admin/operations', {
                              method: 'POST',
                              body: JSON.stringify({ operation: 'refresh_history' }),
                            })
                              .then((res) => {
                                showToast(res.message, 'success');
                                loadHistoryAndJournal();
                              })
                              .catch((err) => showToast(err.message, 'error'))
                          }
                          className="px-3 py-1.5 bg-[#172129] hover:bg-[#202A32] border border-white/10 text-[#E8EEF2] rounded-lg text-xs"
                        >
                          {lang === 'en' ? 'Refresh Signal Outcomes' : 'Vérifier Issue Signaux'}
                        </button>
                        <button
                          type="button"
                          onClick={() =>
                            apiFetch('/api/admin/operations', {
                              method: 'POST',
                              body: JSON.stringify({ operation: 'clean_waits' }),
                            })
                              .then((res) => {
                                showToast(res.message, 'info');
                                loadHistoryAndJournal();
                              })
                              .catch((err) => showToast(err.message, 'error'))
                          }
                          className="px-3 py-1.5 bg-[#172129] hover:bg-[#202A32] border border-white/10 text-[#8B98A4] hover:text-[#E8EEF2] rounded-lg text-xs"
                        >
                          {lang === 'en' ? 'Purge WAIT Signals' : 'Purger Signaux WAIT'}
                        </button>
                        <button
                          type="button"
                          onClick={() =>
                            apiFetch('/api/admin/operations', {
                              method: 'POST',
                              body: JSON.stringify({ operation: 'clear_history' }),
                            })
                              .then((res) => {
                                showToast(res.message, 'info');
                                loadHistoryAndJournal();
                              })
                              .catch((err) => showToast(err.message, 'error'))
                          }
                          className="px-3 py-1.5 bg-[#F04438]/15 hover:bg-[#F04438]/25 border border-[#F04438]/30 text-[#F97066] rounded-lg text-xs"
                        >
                          {lang === 'en' ? 'Clear Signal History' : 'Vider Historique Signaux'}
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* SQL Inspector (/dbquery) */}
                  <div className="bg-[#0D1318] border border-white/[0.07] rounded-xl p-5 space-y-3">
                    <h3 className="font-display font-semibold text-base text-[#E8EEF2]">
                      {lang === 'en' ? 'Database Inspector (/dbquery SELECT)' : 'Inspecteur Base de Données (/dbquery SELECT)'}
                    </h3>
                    <div className="flex gap-2 text-xs">
                      <input
                        type="text"
                        value={adminSqlQuery}
                        onChange={(e) => setAdminSqlQuery(e.target.value)}
                        className="flex-1 px-3 py-2 bg-[#080C0F] border border-white/10 rounded-lg font-mono-tabular text-[#E8EEF2]"
                      />
                      <button
                        type="button"
                        onClick={() =>
                          apiFetch('/api/admin/operations', {
                            method: 'POST',
                            body: JSON.stringify({ operation: 'db_query', sql: adminSqlQuery }),
                          })
                            .then((res) => {
                              setAdminSqlRows(res.rows || []);
                              showToast(res.message, 'success');
                            })
                            .catch((err) => showToast(err.message, 'error'))
                        }
                        className="px-3.5 py-2 bg-[#20C997] text-[#080C0F] font-semibold rounded-lg"
                      >
                        {lang === 'en' ? 'Run SQL' : 'Exécuter'}
                      </button>
                    </div>
                    {adminSqlRows && (
                      <pre className="p-3 rounded-lg bg-[#080C0F] border border-white/[0.06] text-[11px] font-mono-tabular text-[#8B98A4] max-h-48 overflow-auto">
                        {JSON.stringify(adminSqlRows, null, 2)}
                      </pre>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* =========================================================
              TAB 7B: PUBLIC TERMS & CONDITIONS OF USE (CGU & PRIVACY)
             ========================================================= */}
          {activeTab === 'terms' && (
            <TermsOfUsePage
              showAcceptButton={false}
              isAccepted={Boolean(user?.terms_accepted)}
              onBack={() => setActiveTab('intelligence')}
            />
          )}

          {/* =========================================================
              TAB 8A: USERS INTELLIGENCE 360° DOSSIER (ADMIN ONLY)
             ========================================================= */}
          {activeTab === 'users_intelligence' && Boolean(user?.is_admin || user?.role === 'admin') && (
            <AdminUsersIntelligenceTab
              apiFetch={apiFetch}
              onOpenTermsPage={() => setActiveTab('terms')}
              onAdminUserAction={async (action, targetUserId, extra = {}) => {
                if (action === 'approve' || action === 'suspend' || action === 'reject' || action === 'reactivate') {
                  const res = await apiFetch('/api/admin/user-status', {
                    method: 'POST',
                    body: JSON.stringify({
                      target_user_id: targetUserId,
                      action,
                      role: extra.role || 'tester',
                    }),
                  });
                  showToast(res.message || 'Statut utilisateur mis à jour.', 'success');
                  loadAdminOverview();
                } else if (action === 'set_plan') {
                  const res = await apiFetch('/api/admin/user-role', {
                    method: 'POST',
                    body: JSON.stringify({
                      target_user_id: targetUserId,
                      action: 'set_role',
                      role: extra.plan || 'pro',
                    }),
                  });
                  showToast(res.message || 'Plan utilisateur mis à jour.', 'success');
                  loadAdminOverview();
                }
              }}
            />
          )}

          {/* =========================================================
              TAB 8: STRATEGY LAB & BACKTESTING ENGINE (tous les utilisateurs approuvés)
             ========================================================= */}
          {activeTab === 'strategy_lab' && Boolean(user) && (
            <StrategyLabView
              lang={lang}
              isAdmin={isAdminUser}
              onShowToast={(type, text) => showToast(text, type)}
            />
          )}
        </main>

        {/* Mobile Bottom Consolidated Hub Navigation Bar (4 Hubs for standard users, 5 for Admins) */}
        <nav aria-label={tr(lang, 'Navigation mobile', 'Mobile navigation')} className="md:hidden fixed bottom-0 inset-x-0 z-30 bg-[#0D1318] border-t border-[#202A32] flex items-center justify-around py-1 px-1">
          {mobileHubGroups.map((hub) => {
            const Icon = hub.icon;
            const isHubActive = hub.tabs.some((t) => t.id === activeTab);
            return (
              <button
                key={hub.hubId}
                aria-current={isHubActive ? 'page' : undefined}
                onClick={() => {
                  if (isHubActive) {
                    // Pas de changement d'onglet involontaire : le choix se fait via la barre de sous-onglets.
                    window.scrollTo({ top: 0, behavior: 'smooth' });
                  } else {
                    const remembered = lastTabByHubRef.current[hub.hubId];
                    setActiveTab(remembered && hub.tabs.some((t) => t.id === remembered) ? remembered : hub.tabs[0].id);
                  }
                }}
                className={`flex flex-col items-center justify-center min-h-[48px] min-w-[56px] py-1 px-2 rounded-md text-[10px] font-medium relative transition-colors ${
                  isHubActive ? 'text-[#20C997]' : 'text-[#8B98A4]'
                }`}
              >
                <Icon className="w-4 h-4 mb-0.5" />
                <span className="truncate max-w-[68px]">{hub.label}</span>
                {hub.tabs.length > 1 && (
                  <span
                    className={`w-1 h-1 rounded-full mt-0.5 ${
                      isHubActive ? 'bg-[#20C997]' : 'bg-white/20'
                    }`}
                  />
                )}
                {hub.hasSafetyDot && (
                  <span
                    className={`absolute top-1 right-2 w-2 h-2 rounded-full ${
                      hub.apiConnected ? 'bg-[#20C997]' : 'bg-[#F04438]'
                    }`}
                  />
                )}
              </button>
            );
          })}
        </nav>
        {/* Interactive Security PIN Confirmation Modal for Auto-Trade & Safe Mode Unlock */}
        {pinModalAction && (
          <div className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-4">
            <div className="bg-[#0D1318] border border-white/15 rounded-lg max-w-md w-full p-6 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="font-display text-base font-bold text-[#E8EEF2]">
                  {pinModalAction === 'enable_autotrade'
                    ? lang === 'en'
                      ? 'Confirm Auto-Trade Activation'
                      : 'Confirmer l’activation Auto-Trade'
                    : pinModalAction === 'execute_live_order'
                    ? lang === 'en'
                      ? 'Confirm Live Order Execution'
                      : 'Confirmer l’envoi de l’ordre réel'
                    : lang === 'en'
                    ? 'Unlock Safety Mode (/clearsafe)'
                    : 'Déverrouiller le Safe Mode (/clearsafe)'}
                </h3>
                <button
                  type="button"
                  onClick={() => {
                    setPinModalAction(null);
                    setPinModalValue('');
                    setPinModalError('');
                  }}
                  className="text-xs text-[#8B98A4] hover:text-[#E8EEF2]"
                >
                  ✕
                </button>
              </div>

              <p className="text-xs text-[#8B98A4] leading-relaxed">
                {lang === 'en'
                  ? 'Please enter your 6-digit Security PIN code to authorize this sensitive live trading action.'
                  : 'Veuillez saisir votre code PIN de sécurité (6 chiffres) pour autoriser cette opération de trading réel.'}
              </p>

              {pinModalError && (
                <div className="p-3 rounded-lg bg-[#F04438]/15 border border-[#F04438]/40 text-xs text-[#F97066] space-y-2">
                  <div>{pinModalError}</div>
                  {pinModalError.toLowerCase().includes('tentatives') && (
                    <button
                      type="button"
                      onClick={handleResetPinLockout}
                      disabled={isPending('pin-unlock')}
                      className="px-3 py-1.5 rounded bg-[#20C997] text-[#080C0F] font-semibold text-xs inline-block disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {lang === 'en'
                        ? 'Reset anti-bruteforce timer now'
                        : 'Réinitialiser le compteur de blocage immédiatement'}
                    </button>
                  )}
                </div>
              )}

              <div>
                <label className="block text-xs text-[#8B98A4] mb-1.5">
                  {lang === 'en' ? 'Security PIN (6 digits)' : 'Code PIN de Sécurité (6 chiffres)'}
                </label>
                <input
                  type="password"
                  maxLength={6}
                  autoFocus
                  value={pinModalValue}
                  onChange={(e) => setPinModalValue(e.target.value)}
                  placeholder="••••••"
                  className="w-full px-3.5 py-2.5 bg-[#080C0F] border border-white/20 rounded-xl font-mono-tabular text-base tracking-widest text-center text-[#E8EEF2] focus:outline-none focus:border-[#20C997]"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && pinModalValue.trim()) {
                      const entered = pinModalValue.trim();
                      setSafetyPinInput(entered);
                      if (pinModalAction === 'enable_autotrade') {
                        handleUpdateTradingConfig({ enabled: true, pin: entered });
                      } else if (pinModalAction === 'execute_live_order') {
                        handleLiveOrderAction('execute', entered);
                      } else {
                        handleSafetyAction('clearsafe', undefined, entered);
                      }
                    }
                  }}
                />
              </div>

              <div className="flex items-center justify-between gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => {
                    setPinModalAction(null);
                    setActiveTab('account');
                  }}
                  className="text-xs text-[#6BB1FF] hover:underline"
                >
                  {lang === 'en' ? 'Manage / Reset PIN in Account →' : 'Gérer / Réinitialiser mon PIN dans Compte →'}
                </button>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setPinModalAction(null);
                      setPinModalValue('');
                      setPinModalError('');
                    }}
                    className="px-4 py-2 rounded-lg bg-[#172129] text-xs text-[#8B98A4] hover:text-[#E8EEF2]"
                  >
                    {lang === 'en' ? 'Cancel' : 'Annuler'}
                  </button>
                  <button
                    type="button"
                    disabled={!pinModalValue.trim()}
                    onClick={() => {
                      const entered = pinModalValue.trim();
                      setSafetyPinInput(entered);
                      if (pinModalAction === 'enable_autotrade') {
                        handleUpdateTradingConfig({ enabled: true, pin: entered });
                      } else if (pinModalAction === 'execute_live_order') {
                        handleLiveOrderAction('execute', entered);
                      } else {
                        handleSafetyAction('clearsafe', undefined, entered);
                      }
                    }}
                    className="px-4 py-2 rounded-lg bg-[#20C997] hover:bg-[#1AA67D] disabled:opacity-50 text-[#080C0F] font-semibold text-xs"
                  >
                    {lang === 'en' ? 'Confirm' : 'Valider'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
export default App;
