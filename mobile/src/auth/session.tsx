import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import {
  getStoredSessionUser,
  logout as apiLogout,
  StoredSession,
} from '../api/auth';
import { hasStoredSession, setOnSessionExpired } from '../api/client';
import { unregisterPushNotifications } from '../notifications';

export type SessionStatus = 'loading' | 'signedIn' | 'signedOut';

interface SessionContextValue {
  status: SessionStatus;
  session: StoredSession | null;
  /** Called after a successful login or invitation acceptance. */
  signIn: (session: StoredSession) => void;
  /** Clears push token registration and all local credentials. */
  signOut: () => Promise<void>;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<SessionStatus>('loading');
  const [session, setSession] = useState<StoredSession | null>(null);
  const statusRef = useRef(status);
  statusRef.current = status;

  // Bootstrap: a stored refresh token means a probable session. The first
  // API call will refresh proactively; if the refresh token is dead the
  // client fires the session-expired listener below.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [hasSession, storedUser] = await Promise.all([
        hasStoredSession(),
        getStoredSessionUser(),
      ]);
      if (cancelled) return;
      if (hasSession) {
        setSession(storedUser);
        setStatus('signedIn');
      } else {
        setStatus('signedOut');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    setOnSessionExpired(() => {
      if (statusRef.current !== 'signedOut') {
        setSession(null);
        setStatus('signedOut');
      }
    });
    return () => setOnSessionExpired(null);
  }, []);

  const signIn = useCallback((next: StoredSession) => {
    setSession(next);
    setStatus('signedIn');
  }, []);

  const signOut = useCallback(async () => {
    await unregisterPushNotifications();
    await apiLogout();
    setSession(null);
    setStatus('signedOut');
  }, []);

  const value = useMemo<SessionContextValue>(
    () => ({ status, session, signIn, signOut }),
    [status, session, signIn, signOut]
  );

  return (
    <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
  );
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) {
    throw new Error('useSession must be used within a SessionProvider');
  }
  return ctx;
}
