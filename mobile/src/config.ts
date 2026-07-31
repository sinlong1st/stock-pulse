/**
 * App configuration.
 *
 * Point the app at your StockPulse backend to see REAL data. Leave the base URL
 * empty to use the bundled mock data (the app always renders).
 *
 * Set these ONCE via a gitignored env file, so the token never lands in git:
 *
 *   mobile/.env.local
 *     EXPO_PUBLIC_API_BASE_URL=https://your-droplet.tailXXXX.ts.net
 *     EXPO_PUBLIC_API_TOKEN=<matches MOBILE_API_TOKEN on the server>
 *
 * `EXPO_PUBLIC_*` vars are read by Expo automatically (dev + `eas update`). For
 * `eas build` in the cloud, set the same two as EAS environment variables:
 *   eas env:create --name EXPO_PUBLIC_API_TOKEN --value <token> --environment preview
 *
 * See .env.example. (You can also just hardcode the fallback strings below for a
 * throwaway local test — but don't commit a real token.)
 */
export const API_BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL ?? '';
export const API_TOKEN = process.env.EXPO_PUBLIC_API_TOKEN ?? '';
