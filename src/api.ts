const SESSION_TOKEN_KEY = 'bitsure_session_token';
const ACTIVE_UID_KEY = 'bitsure_active_uid_v2';

export function getStoredToken(): string {
  return localStorage.getItem(SESSION_TOKEN_KEY) || '';
}

export function setStoredSession(token: string, userId?: number) {
  if (token) {
    localStorage.setItem(SESSION_TOKEN_KEY, token);
  } else {
    localStorage.removeItem(SESSION_TOKEN_KEY);
  }
  if (userId) {
    localStorage.setItem(ACTIVE_UID_KEY, String(userId));
  }
}

export async function apiFetch<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getStoredToken();
  const uid = localStorage.getItem(ACTIVE_UID_KEY) || '';
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> || {}),
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
    headers['X-Session-Token'] = token;
  }
  if (uid) {
    headers['X-User-Id'] = uid;
  }

  const response = await fetch(path, {
    ...options,
    headers,
  });

  const data = await response.json();
  if (!response.ok || data.ok === false) {
    throw new Error(data.error || data.message || `API Error (${response.status})`);
  }
  return data as T;
}
