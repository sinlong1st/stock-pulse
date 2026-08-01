/**
 * Push-notification registration (Step B of the push plan).
 *
 * Asks permission, gets this device's Expo push token, and registers it with
 * the backend. Best-effort: on a build without FCM configured (before Step C),
 * `getExpoPushTokenAsync` throws — we catch it and skip, so the app never
 * crashes and lights up automatically once FCM is set up + the APK rebuilt.
 */
import Constants from 'expo-constants';
import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';

import { registerPushToken, usingMockData } from './data/api';

// Show notifications while the app is in the foreground too.
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

export async function registerForPush(): Promise<void> {
  if (usingMockData) return; // no backend to register with

  try {
    if (Platform.OS === 'android') {
      await Notifications.setNotificationChannelAsync('default', {
        name: 'Alerts',
        importance: Notifications.AndroidImportance.HIGH,
        lightColor: '#6495ED',
      });
    }

    const existing = await Notifications.getPermissionsAsync();
    let status = existing.status;
    if (status !== 'granted') {
      status = (await Notifications.requestPermissionsAsync()).status;
    }
    if (status !== 'granted') return;

    const projectId = Constants.expoConfig?.extra?.eas?.projectId;
    const token = (await Notifications.getExpoPushTokenAsync({ projectId })).data;
    await registerPushToken(token, Platform.OS);
  } catch (e) {
    // Expected before FCM is configured, or if permission is denied.
    console.log('Push registration skipped:', e);
  }
}
