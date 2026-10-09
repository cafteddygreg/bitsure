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

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 15000);

  let response: Response;
  try {
    response = await fetch(path, {
      ...options,
      credentials: 'include',
      headers,
      signal: options.signal || controller.signal,
    });
  } catch (err: any) {
    clearTimeout(timeoutId);
    if (err?.name === 'AbortError') {
      throw new ApiError(`Délai d'attente dépassé sur ${path}`, 504, 'TIMEOUT');
    }
    throw new ApiError(err?.message || `Serveur inaccessible (${path})`, 503, 'NETWORK_ERROR');
  } finally {
    clearTimeout(timeoutId);
  }

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

export interface EndpointProbeResult {
  endpoint: string;
  label: string;
  reachable: boolean;
  status: number;
  latencyMs: number;
  detail: string;
}

export interface CoreApiDiagnosticReport {
  ok: boolean;
  checkedAt: number;
  databaseOk: boolean;
  authenticated: boolean;
  probes: EndpointProbeResult[];
  errorSummary?: string;
}

async function probeEndpoint(
  endpoint: string,
  label: string,
  validStatuses: number[] = [200],
  timeoutMs = 6000
): Promise<{ probe: EndpointProbeResult; payload: any }> {
  const start = performance.now();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const token = getStoredToken();
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
    headers['X-Session-Token'] = token;
  }

  try {
    const res = await fetch(endpoint, {
      method: 'GET',
      credentials: 'include',
      headers,
      signal: controller.signal,
      cache: 'no-store',
    });
    const latencyMs = Math.round(performance.now() - start);
    const contentType = res.headers.get('content-type') || '';
    const isJson = contentType.includes('application/json');
    const payload = isJson ? await res.json().catch(() => null) : null;
    const statusOk = validStatuses.includes(res.status) && isJson && payload !== null;

    return {
      probe: {
        endpoint,
        label,
        reachable: statusOk,
        status: res.status,
        latencyMs,
        detail: statusOk
          ? `HTTP ${res.status} (${latencyMs} ms)`
          : !isJson
          ? `Réponse non-JSON (HTTP ${res.status})`
          : payload?.error || `HTTP ${res.status}`,
      },
      payload,
    };
  } catch (err: any) {
    const latencyMs = Math.round(performance.now() - start);
    const isTimeout = err?.name === 'AbortError';
    return {
      probe: {
        endpoint,
        label,
        reachable: false,
        status: 0,
        latencyMs,
        detail: isTimeout ? `Timeout après ${timeoutMs} ms` : err?.message || 'Connexion refusée',
      },
      payload: null,
    };
  } finally {
    clearTimeout(timer);
  }
}

export async function runCoreApiDiagnostic(): Promise<CoreApiDiagnosticReport> {
  const [healthRes, authMeRes] = await Promise.all([
    probeEndpoint('/api/health', 'Santé Serveur & Base de données', [200]),
    probeEndpoint('/api/auth/me', 'Service Session & Authentification', [200, 401]),
  ]);

  const probes = [healthRes.probe, authMeRes.probe];
  const allReachable = probes.every((p) => p.reachable);
  const databaseOk = Boolean(healthRes.payload?.database_ok ?? healthRes.probe.reachable);
  const authenticated = Boolean(authMeRes.payload?.authenticated && authMeRes.payload?.user);

  const failed = probes.filter((p) => !p.reachable);
  const errorSummary =
    failed.length > 0
      ? failed.map((f) => `${f.endpoint}: ${f.detail}`).join(' • ')
      : undefined;

  return {
    ok: allReachable,
    checkedAt: Date.now(),
    databaseOk,
    authenticated,
    probes,
    errorSummary,
  };
}

