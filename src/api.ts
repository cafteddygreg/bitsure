const SESSION_TOKEN_KEY = 'bitsure_session_token';
const CSRF_TOKEN_KEY = 'bitsure_csrf_token';

export class ApiError extends Error {
  status: number;
  code?: string;
  accountStatus?: string;

  constructor(message: string, status: number, code?: string, accountStatus?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.accountStatus = accountStatus;
  }
}

export function getStoredToken(): string {
  return localStorage.getItem(SESSION_TOKEN_KEY) || '';
}

export function getStoredCsrfToken(): string {
  return localStorage.getItem(CSRF_TOKEN_KEY) || '';
}

export function setStoredSession(token: string, csrfToken?: string) {
  if (token) {
    localStorage.setItem(SESSION_TOKEN_KEY, token);
  } else {
    localStorage.removeItem(SESSION_TOKEN_KEY);
  }
  if (csrfToken !== undefined) {
    if (csrfToken) {
      localStorage.setItem(CSRF_TOKEN_KEY, csrfToken);
    } else {
      localStorage.removeItem(CSRF_TOKEN_KEY);
    }
  }
}

export function clearStoredSession() {
  localStorage.removeItem(SESSION_TOKEN_KEY);
  localStorage.removeItem(CSRF_TOKEN_KEY);
  localStorage.removeItem('bitsure_active_uid_v2');
}

export async function apiFetch<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getStoredToken();
  const csrf = getStoredCsrfToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((options.headers as Record<string, string>) || {}),
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
    headers['X-Session-Token'] = token;
  }
  if (csrf) {
    headers['X-CSRF-Token'] = csrf;
  }

  const response = await fetch(path, {
    ...options,
    credentials: 'include',
    headers,
  });

  const data = await response.json().catch(() => ({ ok: false, error: `Erreur HTTP ${response.status}` }));
  if (!response.ok || data.ok === false) {
    throw new ApiError(
      data.error || data.message || `Erreur API (${response.status})`,
      response.status,
      data.code,
      data.account_status
    );
  }
  return data as T;
}
