import * as Application from 'expo-application';
import Constants from 'expo-constants';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';
import { deletePushToken, registerPushToken } from './api/mobile';
import { getInstallationId } from './lib/installation';

// Show notifications while the app is foregrounded.
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: false,
    shouldSetBadge: false,
  }),
});

/** Last push token successfully registered with the backend (this run). */
let registeredToken: string | null = null;

export function getRegisteredPushToken(): string | null {
  return registeredToken;
}

/**
 * Ask for notification permission, obtain the Expo push token and register
 * it with the backend. Silently no-ops when permission is denied or when
 * running on a simulator/emulator (no push support there).
 */
export async function registerForPushNotifications(
  locale: string
): Promise<void> {
  try {
    if (!Device.isDevice) return;

    if (Platform.OS === 'android') {
      await Notifications.setNotificationChannelAsync('default', {
        name: 'default',
        importance: Notifications.AndroidImportance.DEFAULT,
        lightColor: '#f97316',
      });
    }

    const existing = await Notifications.getPermissionsAsync();
    let status = existing.status;
    if (status !== 'granted') {
      const requested = await Notifications.requestPermissionsAsync();
      status = requested.status;
    }
    if (status !== 'granted') return;

    const projectId: string | undefined =
      Constants.expoConfig?.extra?.eas?.projectId ??
      Constants.easConfig?.projectId;

    const tokenResponse = await Notifications.getExpoPushTokenAsync(
      projectId ? { projectId } : undefined
    );
    const token = tokenResponse.data;

    await registerPushToken({
      token,
      platform: Platform.OS,
      installation_id: await getInstallationId(),
      app_version: Application.nativeApplicationVersion ?? undefined,
      locale,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    });
    registeredToken = token;
  } catch {
    // Push registration must never break the app (e.g. Expo Go without
    // a projectId, or the backend being unreachable). Retried on next launch.
  }
}

/** Unregister the current push token from the backend (called on logout). */
export async function unregisterPushNotifications(): Promise<void> {
  const token = registeredToken;
  registeredToken = null;
  if (!token) return;
  try {
    await deletePushToken(token);
  } catch {
    // Best effort — the backend also invalidates tokens on push failures.
  }
}

/**
 * Listen for notification taps and navigate to Home. Returns a cleanup
 * function for the subscription.
 */
export function addNotificationTapListener(
  onNavigateHome: () => void
): () => void {
  const subscription = Notifications.addNotificationResponseReceivedListener(
    () => {
      onNavigateHome();
    }
  );
  return () => subscription.remove();
}
