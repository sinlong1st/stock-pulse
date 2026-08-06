# Expo HAS CHANGED

This app is pinned to **Expo SDK 54** (React Native 0.81, React 19.1) to match the
Expo Go build on the owner's phone. **Do not bump it** without being asked.

Read the exact versioned docs at https://docs.expo.dev/versions/v54.0.0/ before
writing any code. Newer Expo docs describe APIs that do not exist here.

## Shipping

JS-only changes go out over the air (`eas update`, runtimeVersion = appVersion).
Adding a **native** dependency means an APK rebuild, so prefer packages already in
`package.json` when a change needs to ship OTA.
