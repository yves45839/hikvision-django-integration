/**
 * Fetch wrapper for the LR Time backend.
 *
 * Token strategy:
 * - Access token (15 min lifetime) lives in memory only.
 * - Refresh token lives in expo-secure-store.
 * - SimpleJWT REFRESH ROTATION is enabled server-side: every call to
 *   /api/auth/refresh/ returns a NEW refresh token, and the old one is
 *   blacklisted. The rotated refresh token is therefore persisted
 *   IMMEDIATELY after every refresh, before anything else happens.
 * - Refresh is proactive (JWT `exp` decoded, 45 s leeway) and single-flight:
 *   concurrent requests share one in-flight refresh promise.
 * - A 401 on an authenticated request triggers one forced refresh + retry.
 */
import * as SecureStore from 'expo-secure-store';

const REFRESH_TOKEN_KEY = 'lrtime.refresh_token';
export const SESSION_USER_KEY = 'lrtime.session_user';

const REFRESH_LEEWAY_SECONDS = 45;
const REQUEST_TIMEOUT_MS = 20_000;

export const API_BASE_URL: string =
  process.env.EXPO_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

export interface ApiErrorPayload {
  code?: string;
  detail?: string;
  [key: string]: unknown;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly detail: string;
  /** Full parsed error body, for typed extras (retry_after_s, nearest_site…). */
  readonly payload: ApiErrorPayload;

  constructor(status: number, payload: ApiErrorPayload) {
    const detail =
      typeof payload.detail === 'string' ? payload.detail : `HTTP ${status}`;
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.code = typeof payload.code === 'string' ? payload.code : undefined;
    this.detail = detail;
    this.payload = payload;
  }
}

/** Thrown when the request never reached the server (offline, timeout…). */
export class NetworkError extends Error {
  constructor(cause?: unknown) {
    super('Network request failed');
    this.name = 'NetworkError';
    if (cause instanceof Error && cause.message) {
      this.message = cause.message;
    }
  }
}

// ---------------------------------------------------------------------------
// JWT decoding (no external dependency; atob is not guaranteed on Hermes)
// ---------------------------------------------------------------------------

const B64_CHARS =
  'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';

function base64Decode(input: string): string {
  let str = input.replace(/-/g, '+').replace(/_/g, '/').replace(/=+$/, '');
  let output = '';
  let buffer = 0;
  let bits = 0;
  for (const char of str) {
    const value = B64_CHARS.indexOf(char);
    if (value === -1) continue;
    buffer = (buffer << 6) | value;
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      output += String.fromCharCode((buffer >> bits) & 0xff);
    }
  }
  return output;
}

function decodeJwtExp(token: string): number | null {
  try {
    const parts = token.split('.');
    const payloadPart = parts[1];
    if (!payloadPart) return null;
    const payload = JSON.parse(base64Decode(payloadPart)) as { exp?: number };
    return typeof payload.exp === 'number' ? payload.exp : null;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Token state
// ---------------------------------------------------------------------------

let accessToken: string | null = null;
let accessTokenExp: number | null = null; // Unix seconds
let refreshPromise: Promise<string | null> | null = null;

type SessionExpiredListener = () => void;
let sessionExpiredListener: SessionExpiredListener | null = null;

/** Called (once per expiry) when the refresh token is dead — route to /login. */
export function setOnSessionExpired(listener: SessionExpiredListener | null) {
  sessionExpiredListener = listener;
}

export function setAccessToken(token: string) {
  accessToken = token;
  accessTokenExp = decodeJwtExp(token);
}

export async function persistRefreshToken(token: string): Promise<void> {
  await SecureStore.setItemAsync(REFRESH_TOKEN_KEY, token);
}

export async function getStoredRefreshToken(): Promise<string | null> {
  return SecureStore.getItemAsync(REFRESH_TOKEN_KEY);
}

/** Store both tokens after login / invitation-accept / refresh. */
export async function setSessionTokens(
  access: string,
  refresh: string
): Promise<void> {
  setAccessToken(access);
  await persistRefreshToken(refresh);
}

/** Clear all credentials (memory + secure storage). */
export async function clearSessionTokens(): Promise<void> {
  accessToken = null;
  accessTokenExp = null;
  await SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY).catch(() => undefined);
  await SecureStore.deleteItemAsync(SESSION_USER_KEY).catch(() => undefined);
}

function isAccessTokenFresh(): boolean {
  if (!accessToken) return false;
  if (accessTokenExp === null) return true; // Undecodable exp: let the 401 path handle it.
  const now = Math.floor(Date.now() / 1000);
  return accessTokenExp - now > REFRESH_LEEWAY_SECONDS;
}

// ---------------------------------------------------------------------------
// Refresh (single-flight)
// ---------------------------------------------------------------------------

async function doRefresh(): Promise<string | null> {
  const storedRefresh = await getStoredRefreshToken();
  if (!storedRefresh) {
    return null;
  }

  let response: Response;
  try {
    response = await fetchWithTimeout(`${API_BASE_URL}/api/auth/refresh/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh: storedRefresh }),
    });
  } catch (err) {
    // Network failure: keep the refresh token, the session may still be valid.
    throw new NetworkError(err);
  }

  if (response.status === 400 || response.status === 401) {
    // Refresh token invalid/blacklisted/expired: the session is dead.
    await clearSessionTokens();
    sessionExpiredListener?.();
    return null;
  }
  if (!response.ok) {
    throw new ApiError(response.status, await safeJson(response));
  }

  const data = (await response.json()) as { access: string; refresh?: string };

  // CRITICAL: rotation is on — persist the new refresh token before returning,
  // otherwise the old (blacklisted) token stays stored and the session dies.
  if (typeof data.refresh === 'string' && data.refresh.length > 0) {
    await persistRefreshToken(data.refresh);
  }
  setAccessToken(data.access);
  return data.access;
}

function refreshAccessToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = doRefresh().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

/**
 * Returns a valid access token, refreshing proactively when it expires in
 * less than REFRESH_LEEWAY_SECONDS. Returns null when there is no session.
 */
export async function getValidAccessToken(): Promise<string | null> {
  if (isAccessTokenFresh()) return accessToken;
  return refreshAccessToken();
}

/** True when a refresh token is stored (a session probably exists). */
export async function hasStoredSession(): Promise<boolean> {
  return (await getStoredRefreshToken()) !== null;
}

// ---------------------------------------------------------------------------
// Fetch helpers
// ---------------------------------------------------------------------------

async function safeJson(response: Response): Promise<ApiErrorPayload> {
  try {
    const data: unknown = await response.json();
    if (data && typeof data === 'object') return data as ApiErrorPayload;
    return {};
  } catch {
    return {};
  }
}

async function fetchWithTimeout(
  url: string,
  init: RequestInit
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

export interface ApiFetchOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  /** Attach the Authorization header (default true). */
  auth?: boolean;
}

/**
 * Perform an API request. Throws ApiError on non-2xx responses and
 * NetworkError when the server was unreachable.
 */
export async function apiFetch<T>(
  path: string,
  options: ApiFetchOptions = {}
): Promise<T> {
  const { method = 'GET', body, auth = true } = options;
  return doApiFetch<T>(path, method, body, auth, true);
}

async function doApiFetch<T>(
  path: string,
  method: NonNullable<ApiFetchOptions['method']>,
  body: unknown,
  auth: boolean,
  allowRetryOn401: boolean
): Promise<T> {
  const headers: Record<string, string> = {
    Accept: 'application/json',
  };
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
  }

  if (auth) {
    const token = await getValidAccessToken();
    if (!token) {
      throw new ApiError(401, {
        code: 'NOT_AUTHENTICATED',
        detail: 'No active session.',
      });
    }
    headers['Authorization'] = `Bearer ${token}`;
  }

  let response: Response;
  try {
    response = await fetchWithTimeout(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (err) {
    throw new NetworkError(err);
  }

  if (response.status === 401 && auth && allowRetryOn401) {
    // Access token rejected (e.g. clock drift): force one refresh + retry.
    accessToken = null;
    accessTokenExp = null;
    const token = await refreshAccessToken();
    if (token) {
      return doApiFetch<T>(path, method, body, auth, false);
    }
    throw new ApiError(401, {
      code: 'NOT_AUTHENTICATED',
      detail: 'Session expired.',
    });
  }

  if (!response.ok) {
    throw new ApiError(response.status, await safeJson(response));
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
