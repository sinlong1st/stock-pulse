/**
 * Dynamic Expo config layered on top of app.json.
 *
 * Purpose: keep `google-services.json` OUT of this PUBLIC repo. For EAS cloud
 * builds the file is supplied via the `GOOGLE_SERVICES_JSON` file environment
 * variable (set once with `eas env:create --type file`); EAS materializes it and
 * sets the var to its path. Locally it falls back to ./google-services.json
 * (which is gitignored but present on your machine).
 *
 * Everything else still comes from app.json.
 */
module.exports = ({ config }) => ({
  ...config,
  android: {
    ...config.android,
    googleServicesFile:
      process.env.GOOGLE_SERVICES_JSON ?? config.android?.googleServicesFile,
  },
});
