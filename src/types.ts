export type AccountStatus = 'PENDING_APPROVAL' | 'APPROVED' | 'REJECTED' | 'SUSPENDED';

export interface UserQuotas {
  daily_analyses: number;
  daily_scans: number;
  max_alerts: number;
  max_paper_trades: number;
}

export interface QuotaUsage {
  analyses_used: number;
  scans_used: number;
  paper_trades_used: number;
}

export interface SecurityEvent {
  id: number;
  event_type: string;
  severity: 'info' | 'warning' | 'critical';
  user_id?: number | null;
  email?: string | null;
  ip_address?: string | null;
  details?: string | null;
  created_at: number;
}

export interface UserProfile {
  user_id: number;
  email: string;
  display_name: string;
  telegram_handle: string;
  auth_provider?: 'local' | 'google';
  role: 'free' | 'tester' | 'pro' | 'vip' | 'admin';
  is_admin: boolean;
  is_premium: boolean;
  account_status: AccountStatus;
  approved: boolean;
  terms_accepted: boolean;
  lang: 'fr' | 'en';
  timeframe: string;
  risk: 'low' | 'medium' | 'high';
  remaining_requests: number;
  daily_limit: number;
  quotas?: UserQuotas;
  quota_usage?: QuotaUsage;
  trial_days: number;
  trial_valid: boolean;
  memo?: string | null;
  has_pin: boolean;
  watchlist: string[];
  watchlist_limit: number;
  alert_limit: number;
  trading_style: string;
  csrf_token?: string;
  google_oauth_enabled?: boolean;
}

export interface CandlePoint {
  index: number;
  timestamp: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
  sma20: number | null;
  sma50: number | null;
  bb_upper: number | null;
  bb_lower: number | null;
  rsi: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_hist: number | null;
}

export interface SizingRecommendation {
  capital: number;
  risk_pct: number;
  risk_amount_usd: number;
  position_size: number;
  notional_usd: number;
  margin_required_usd: number;
  leverage: number;
  market_type: string;
}

export interface MarketAnalysis {
  symbol: string;
  display_symbol: string;
  timeframe: string;
  style: string;
  data_source: string;
  market_status: {
    is_open: boolean;
    message: string;
  };
  signal: 'BUY' | 'SELL' | 'WAIT';
  signal_text: string;
  teddy_score: number;
  confidence: string;
  validation_status: string;
  reason: string;
  rejection_reason: string;
  risk_advice: string;
  current_price: number;
  sl: number | null;
  tp: number | null;
  tp1: number | null;
  tp2: number | null;
  rr_ratio: number | null;
  asset_class: string;
  params_used: Record<string, any>;
  score_detail: Record<string, any>;
  indicators: Record<string, any>;
  sizing_recommendation: SizingRecommendation;
  candles: CandlePoint[];
}

export interface PaperStats {
  capital: number;
  equity: number;
  total_pnl: number;
  open_positions: number;
  total_trades: number;
  wins: number;
  losses: number;
  win_rate: number;
}

export interface PaperPosition {
  id: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  entry: number;
  entry_price?: number;
  sl: number;
  tp: number;
  qty: number;
  leverage: number;
  margin_used: number;
  open_fee?: number;
  fees_total?: number;
  opened_at: string | number;
  current_price?: number;
  unrealized_pnl?: number;
  unrealized_pnl_pct?: number;
  pnl_usdt?: number;
  exit_price?: number;
  pnl?: number;
  pnl_pct?: number;
  close_reason?: string;
  exit_reason?: string;
  closed_at?: string | number;
}

export interface PriceAlert {
  id: number;
  symbol: string;
  condition: 'above' | 'below';
  price: number;
  created_at?: number;
}

export interface HistoricalSignal {
  id: string;
  symbol: string;
  direction: 'BUY' | 'SELL' | 'WAIT';
  entry_price: number;
  timeframe: string;
  type: string;
  score: number;
  timestamp: string;
  created_at: number;
  closed_at: number | null;
  status: string;
  result: string | null;
  validation_status: string | null;
  validation_reason: string | null;
  rejection_reason: string | null;
  sl: number | null;
  tp: number | null;
  result_price: number | null;
  result_pct: number | null;
  pnl: number | null;
  rr_ratio: number | null;
  asset_class: string | null;
}

export interface TradingConfigState {
  user_id: number;
  enabled: boolean;
  auto_trade?: boolean;
  periodic_analysis_enabled: boolean;
  analysis_interval_minutes: number;
  analysis_timeframe: string;
  trading_style: string;
  market_type: 'futures' | 'spot';
  leverage: number;
  risk_per_trade: number;
  max_positions: number;
  max_daily_loss: number;
  min_score: number;
  trailing_stop: boolean;
  trailing_stop_pct: number;
  dca_enabled: boolean;
  dca_steps: number;
  dca_step_pct: number;
  cooldown_seconds: number;
  symbols: string[];
  symbol_whitelist: string[];
  symbol_blacklist: string[];
  daily_loss_tracked: number;
  credentials_loaded?: boolean;
  credentials_valid: boolean;
  api_status_message?: string;
  has_custom_credentials: boolean;
  api_key_masked: string | null;
  testnet: boolean;
  is_testnet: boolean;
  safety_lock: boolean;
  safety_lock_reason: string | null;
  safety_lock_at: number | null;
  safety_lock_age_seconds: number | null;
  safety_lock_ttl_seconds: number;
  safety_warn: boolean;
  safety_warn_reason: string | null;
  safety_warn_at?: number | null;
}

export interface SupportTicket {
  id: number;
  user_id: number;
  username: string;
  subject: string;
  message: string;
  admin_reply?: string | null;
  status: 'open' | 'answered';
  created_at: number;
  replied_at?: number;
}

export interface WebNotification {
  id: number;
  category: string;
  title: string;
  body: string;
  is_read: number;
  created_at: number;
}

export interface StrategyLabParams {
  initial_capital: number;
  position_sizing_mode: 'risk_pct' | 'fixed_usdt' | 'capital_pct';
  risk_per_trade_pct: number;
  fixed_position_usdt: number;
  capital_allocation_pct: number;
  leverage: number;
  fee_bps: number;
  slippage_bps: number;
  allow_long: boolean;
  allow_short: boolean;
  max_open_positions: number;
  cooldown_candles: number;
  max_trades_per_day: number;
  max_consecutive_losses: number;
  ema_fast: number;
  ema_slow: number;
  ema_trend: number;
  rsi_period: number;
  rsi_oversold: number;
  rsi_overbought: number;
  adx_period: number;
  adx_min: number;
  atr_period: number;
  min_atr_pct: number;
  volume_ma_period: number;
  min_volume_ratio: number;
  min_teddy_score: number;
  require_ema_alignment: boolean;
  require_macd_confirmation: boolean;
  require_trend_filter_ema200: boolean;
  block_against_strong_trend: boolean;
  sl_mode: 'atr' | 'fixed_pct';
  sl_atr_mult: number;
  sl_fixed_pct: number;
  tp_mode: 'rr' | 'atr' | 'fixed_pct';
  min_rr_ratio: number;
  tp_atr_mult: number;
  tp_fixed_pct: number;
  partial_tp_enabled: boolean;
  partial_tp_rr: number;
  partial_tp_close_pct: number;
  breakeven_enabled: boolean;
  breakeven_trigger_rr: number;
  trailing_stop_enabled: boolean;
  trailing_activation_rr: number;
  trailing_distance_atr: number;
  exit_on_opposite_signal: boolean;
  max_bars_in_trade: number;
}

export interface StrategyLabPreset {
  id: number;
  name: string;
  description: string;
  symbol: string;
  timeframe: string;
  trading_style: string;
  params: StrategyLabParams;
  tags: string;
  is_favorite: boolean;
  notes: string;
  created_at: number;
  updated_at: number;
}

export interface StrategyLabTrade {
  id: number;
  symbol: string;
  side: 'BUY' | 'SELL';
  entry_time: string;
  exit_time: string;
  entry_index: number;
  exit_index: number;
  bars_held: number;
  entry_price: number;
  exit_price: number;
  sl_initial: number;
  tp_initial: number;
  qty: number;
  notional_usdt: number;
  margin_used: number;
  pnl_usdt: number;
  pnl_pct: number;
  r_multiple: number;
  fees_usdt: number;
  mfe_pct: number;
  mae_pct: number;
  teddy_score: number;
  entry_reasons: string[];
  exit_reason: string;
  partial_taken: boolean;
}

export interface StrategyLabMetrics {
  initial_capital: number;
  final_capital: number;
  net_profit_usdt: number;
  total_return_pct: number;
  buy_hold_return_pct: number;
  alpha_vs_buy_hold_pct: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate_pct: number;
  profit_factor: number;
  expectancy_usdt: number;
  avg_r_multiple: number;
  payoff_ratio: number;
  avg_win_usdt: number;
  avg_loss_usdt: number;
  best_trade_usdt: number;
  worst_trade_usdt: number;
  max_drawdown_pct: number;
  max_drawdown_usdt: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  calmar_ratio: number;
  max_win_streak: number;
  max_loss_streak: number;
  avg_bars_held: number;
  avg_duration_minutes: number;
  total_fees_usdt: number;
  long_trades: number;
  long_win_rate_pct: number;
  long_pnl_usdt: number;
  short_trades: number;
  short_win_rate_pct: number;
  short_pnl_usdt: number;
  by_exit_reason: Record<string, { count: number; pnl_usdt: number; wins: number }>;
}

export interface StrategyLabRun {
  id?: number;
  name?: string;
  symbol: string;
  timeframe: string;
  trading_style: string;
  data_source: string;
  start_date: string;
  end_date: string;
  candles_count: number;
  execution_ms?: number;
  params: StrategyLabParams;
  metrics: StrategyLabMetrics;
  diagnostics?: { severity: string; title: string; detail: string }[];
  signals_summary?: {
    total_candles_evaluated: number;
    valid_signals: number;
    executed_trades: number;
    rejection_counts: Record<string, number>;
    rejected_sample: {
      timestamp: string;
      price: number;
      candidate: string;
      score: number;
      rejected_by: string;
      reason: string;
    }[];
  };
  trades?: StrategyLabTrade[];
  equity_curve?: {
    timestamp: string;
    equity: number;
    balance: number;
    drawdown_pct: number;
    drawdown_usdt: number;
    price: number;
  }[];
  candles?: {
    index: number;
    timestamp: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
    ema_fast: number;
    ema_slow: number;
    ema_trend: number;
    bb_upper: number | null;
    bb_lower: number | null;
    rsi: number;
    adx: number;
    marker: {
      type: 'ENTRY' | 'EXIT';
      trade_id?: number;
      side: 'BUY' | 'SELL';
      price: number;
      entry_price?: number;
      exit_price?: number;
      sl?: number;
      tp?: number;
      score?: number;
      reason?: string;
      pnl_usdt?: number;
      pnl_pct?: number;
      r_multiple?: number;
      bars_held?: number;
      exit_reason?: string;
    } | null;
  }[];
  tags?: string;
  is_favorite?: boolean;
  notes?: string;
  created_at?: number;
}

