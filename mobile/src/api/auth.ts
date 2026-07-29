import * as SecureStore from 'expo-secure-store';
import {
  apiFetch,
  clearSessionTokens,
  SESSION_USER_KEY,
  setSessionTokens,
} from './client';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TenantMembership {
  id: number;
  code: string;
  name: string;
  role: string;
}

/**
 * The backend returns a `user` object with the login response. Only the
 * fields the app relies on are typed; extras are preserved untouched.
 */
export interface SessionUser {
  id: number;
  email?: string | null;
  username?: string;
  first_name?: string;
  last_name?: string;
  name?: string;
  [key: string]: unknown;
}

export interface AuthResponse {
  access: string;
  refresh: string;
  user: SessionUser;
  tenants: TenantMembership[];
}

export interface StoredSession {
  user: SessionUser;
  tenants: TenantMembership[];
}

export interface InvitationPreview {
  employee_name: string;
  tenant_name: string;
  email: string;
  status: string;
  expires_at: string;
}

// ---------------------------------------------------------------------------
// Session persistence (user profile; tokens live in client.ts)
// ---------------------------------------------------------------------------

async function persistSessionUser(session: StoredSession): Promise<void> {
  try {
    await SecureStore.setItemAsync(SESSION_USER_KEY, JSON.stringify(session));
  } catch {
    // Non-fatal: identity display falls back to /api/mobile/me/.
  }
}

export async function getStoredSessionUser(): Promise<StoredSession | null> {
  try {
    const raw = await SecureStore.getItemAsync(SESSION_USER_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredSession;
    if (!parsed || typeof parsed !== 'object' || !parsed.user) return null;
    return parsed;
  } catch {
    return null;
  }
}

async function establishSession(data: AuthResponse): Promise<StoredSession> {
  await setSessionTokens(data.access, data.refresh);
  const session: StoredSession = {
    user: data.user,
    tenants: data.tenants ?? [],
  };
  await persistSessionUser(session);
  return session;
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

export async function login(
  identifier: string,
  password: string
): Promise<StoredSession> {
  const data = await apiFetch<AuthResponse>('/api/auth/login/', {
    method: 'POST',
    body: { identifier, password },
    auth: false,
  });
  return establishSession(data);
}

export async function previewInvitation(
  token: string
): Promise<InvitationPreview> {
  return apiFetch<InvitationPreview>(
    `/api/auth/employee-invitations/preview/?token=${encodeURIComponent(token)}`,
    { auth: false }
  );
}

/** Accept an invitation; the backend auto-logs the new account in (201). */
export async function acceptInvitation(
  token: string,
  password: string
): Promise<StoredSession> {
  const data = await apiFetch<AuthResponse>(
    '/api/auth/employee-invitations/accept/',
    { method: 'POST', body: { token, password }, auth: false }
  );
  return establishSession(data);
}

/** Clear all local credentials. Server-side blacklisting happens via rotation. */
export async function logout(): Promise<void> {
  await clearSessionTokens();
}
