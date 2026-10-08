export interface UserProfile {
  user_id: number;
  email: string;
  display_name: string;
  telegram_handle: string;
  role: 'free' | 'tester' | 'pro' | 'vip' | 'admin';
  is_admin: boolean;
  is_premium: boolean;
  approved: boolean;
  terms_accepted: boolean;
  lang: 'fr' | 'en';
  timeframe: string;
  risk: 'low' | 'medium' | 'high';
  remaining_requests: number;
  daily_limit: number;
  trial_days: number;
  trial_valid: boolean;
  memo?: string | null;
  has_pin: boolean;
  watchlist: string[];
  watchlist_limit: number;
  alert_limit: number;
  trading_style: string;
}

export interface DemoAccount {
  email: string;
  role: string;
  label: string;
  user_id: number;
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
  sl: number;
  tp: number;
  qty: number;
  leverage: number;
  margin_used: number;
  open_fee: number;
  opened_at: string;
  current_price?: number;
  unrealized_pnl?: number;
  unrealized_pnl_pct?: number;
  exit_price?: number;
  pnl?: number;
  pnl_pct?: number;
  close_reason?: string;
  closed_at?: string;
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
