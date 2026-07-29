import { Stack, useRouter, useSegments } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import React, { useEffect } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';
import { useSession, SessionProvider } from '../src/auth/session';
import { I18nProvider } from '../src/i18n';
import { colors } from '../src/lib/theme';

/**
 * Auth gate:
 * - no session -> redirect to /login
 * - signed in on /login -> redirect to the tabs
 * - /accept-invitation stays reachable in BOTH states so the
 *   lrtime://accept-invitation?token=... deep link always works
 *   (expo-router maps the scheme URL to the route automatically).
 */
function AuthGate({ children }: { children: React.ReactNode }) {
  const { status } = useSession();
  const segments = useSegments();
  const router = useRouter();

  const first = segments[0] as string | undefined;
  const isPublicRoute = first === 'login' || first === 'accept-invitation';

  useEffect(() => {
    if (status === 'loading') return;
    if (status === 'signedOut' && !isPublicRoute) {
      router.replace('/login');
    } else if (status === 'signedIn' && first === 'login') {
      router.replace('/(tabs)');
    }
  }, [status, first, isPublicRoute, router]);

  if (status === 'loading') {
    return (
      <View style={styles.loading}>
        <ActivityIndicator size="large" color={colors.accent} />
      </View>
    );
  }

  return <>{children}</>;
}

export default function RootLayout() {
  return (
    <I18nProvider>
      <SessionProvider>
        <StatusBar style="light" backgroundColor={colors.bg} />
        <AuthGate>
          <Stack
            screenOptions={{
              headerShown: false,
              contentStyle: { backgroundColor: colors.bg },
              animation: 'fade',
            }}
          >
            <Stack.Screen name="login" />
            <Stack.Screen name="accept-invitation" />
            <Stack.Screen name="(tabs)" />
          </Stack>
        </AuthGate>
      </SessionProvider>
    </I18nProvider>
  );
}

const styles = StyleSheet.create({
  loading: {
    flex: 1,
    backgroundColor: colors.bg,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
