/**
 * Version/OTA helpers so you can *see* which build the phone is running and
 * pull the latest on demand. In dev (Expo Go / `npm start`) OTA is inactive.
 */
import * as Updates from 'expo-updates';

const APP_VERSION = '1.0.0';

/** A short, human-readable label for the running build/update. */
export function versionLabel(): string {
  if (__DEV__) return `v${APP_VERSION} · dev`;
  // A fresh install with no OTA update yet runs the bundle baked into the APK.
  if (Updates.isEmbeddedLaunch || !Updates.updateId) return `v${APP_VERSION} · base build`;
  const when = Updates.createdAt ? Updates.createdAt.toLocaleString() : '';
  return `v${APP_VERSION} · OTA ${Updates.updateId.slice(0, 6)} · ${when}`;
}

export type UpdateCheck = 'dev' | 'current' | 'downloading' | 'error';

/** Check for a newer OTA update; if found, download it and reload the app. */
export async function checkForUpdate(): Promise<UpdateCheck> {
  if (__DEV__) return 'dev';
  try {
    const res = await Updates.checkForUpdateAsync();
    if (res.isAvailable) {
      await Updates.fetchUpdateAsync();
      await Updates.reloadAsync(); // restarts into the new update
      return 'downloading';
    }
    return 'current';
  } catch {
    return 'error';
  }
}
