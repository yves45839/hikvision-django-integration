import * as Crypto from 'expo-crypto';
import * as SecureStore from 'expo-secure-store';

const INSTALLATION_ID_KEY = 'lrtime.installation_id';

let cachedId: string | null = null;

/**
 * Stable per-install identifier, generated once and kept in SecureStore.
 * Survives app restarts and OS backups tied to the keychain/keystore;
 * regenerated after a full uninstall on Android.
 */
export async function getInstallationId(): Promise<string> {
  if (cachedId) return cachedId;
  let id = await SecureStore.getItemAsync(INSTALLATION_ID_KEY);
  if (!id) {
    id = Crypto.randomUUID();
    await SecureStore.setItemAsync(INSTALLATION_ID_KEY, id);
  }
  cachedId = id;
  return id;
}

/** UUID v4 helper (used for punch idempotency keys). */
export function newUuid(): string {
  return Crypto.randomUUID();
}
