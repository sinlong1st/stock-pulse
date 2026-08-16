# 11 — Secure storage on the device

## The problem

The refresh token must survive the app closing, the phone rebooting, and thirty
days passing — otherwise you log in constantly and the design in file 10 buys
nothing.

So it has to be written down somewhere on the phone. It is a 30-day credential
that grants full access to your account. Where do you put it?

## What's available

| Option | What it really is | Suitable for a credential? |
|---|---|---|
| A JS variable | RAM, gone on close | Access token only |
| `AsyncStorage` | **Unencrypted file** in the app's sandbox | ❌ No |
| `expo-secure-store` | iOS **Keychain** / Android **Keystore** | ✅ Yes |
| A file you wrote | An unencrypted file, with extra steps | ❌ No |

The middle row is the trap, because `AsyncStorage` is what every tutorial uses
and it works perfectly — until the day it matters.

## Why AsyncStorage is wrong here

`AsyncStorage` on Android is a SQLite database in the app's private directory.
"Private" means *other apps* cannot read it, which sounds sufficient. It is not,
in three situations:

- **A rooted or jailbroken device** — the sandbox is advisory once root exists.
- **Backups** — the file can be swept into a device backup and end up on a
  computer or in cloud storage.
- **Physical access with the right tools** — an unencrypted file is an
  unencrypted file.

The sandbox is an *access control*, not encryption. For "dark mode: on", perfect.
For a 30-day credential to your financial data, not enough.

## What the Keychain / Keystore actually adds

Both are OS services that store secrets **encrypted**, with keys the app itself
never sees.

**iOS Keychain** — encrypted store, hardware-backed on modern devices, with
accessibility classes controlling *when* a secret can be read (e.g. only while
the device is unlocked).

**Android Keystore** — key material lives in hardware where available (TEE or a
dedicated secure element). The app asks the OS to encrypt/decrypt; the raw key
never enters the app's memory. `expo-secure-store` uses it to encrypt values in
`EncryptedSharedPreferences`.

The important property in both: **your app never holds the encryption key.**
Compromising the app's files does not yield the secret, because the key isn't
among them.

```
  AsyncStorage                    SecureStore
  ┌──────────────┐                ┌──────────────┐
  │ app sandbox  │                │ app sandbox  │
  │  data.db     │                │  encrypted   │──┐
  │  "token123"  │← readable      │  blob        │  │ decrypt via OS
  └──────────────┘                └──────────────┘  │
                                  ┌──────────────┐  │
                                  │ Keychain /   │◄─┘
                                  │ Keystore     │  key never leaves
                                  │ (hardware)   │
                                  └──────────────┘
```

### Optional: require the fingerprint

SecureStore can gate a read behind device authentication:

```js
await SecureStore.setItemAsync('refresh', token, {
  requireAuthentication: true,
  keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
});
```

Now the token is readable only after a fingerprint/face check, and
`THIS_DEVICE_ONLY` keeps it out of backups so it cannot be restored onto another
phone.

Worth being precise about what this does: **the biometric is not authenticating
you to StockPulse.** It is a local gate on a stored credential that your
*password* minted earlier. Useful — it means a briefly-unlocked phone doesn't
hand over the token — but it is not a second factor in the server's eyes.

## The cost: this one needs an APK rebuild

`expo-secure-store` is a **native module**. It is not JavaScript, so it cannot
arrive over the air.

> ⚠️ Everything else in this login project ships via `eas update` in about a
> minute. **This one line requires a full `eas build`** and installing a new APK,
> with an `app.json` version bump. Plan it into the same build as any other native
> change you're sitting on. See `mobile/AGENTS.md`.

## And the secret you're removing

Today the app ships with `EXPO_PUBLIC_API_TOKEN` baked in.

`EXPO_PUBLIC_*` variables are **compiled into the JavaScript bundle**. Anyone who
downloads the APK can extract it — unzip, find the bundle, search for the string.
There is no obfuscation that fixes this; the code has to be able to read it, so
whoever holds the code holds the secret.

It is acceptable *today* only because Tailscale means possessing the token gets
you nowhere without also being on the private network. As the only lock on a
public endpoint, it would be a single shared password, identical on every
install, that never expires.

**After this project the app ships with no secret at all.** Your password stays in
your head; the tokens are minted per device and expire on their own. That is the
real prize here — bigger than the battery.

```
  BEFORE                              AFTER
  APK contains a permanent            APK contains nothing secret
  shared API token                    Keychain holds a per-device,
  ↓                                   expiring, revocable token
  extractable, unrevocable            ↓
  (except by rebuilding)              revoke one device from the server
```

## In StockPulse

- **Refresh token** → `expo-secure-store`, key `stockpulse.refresh`.
- **Access token** → memory only. It lives 15 minutes; writing it to disk adds
  risk and saves nothing.
- **Password** → never stored, anywhere, in any form.
- Logout: delete from SecureStore **and** call `/api/auth/logout` so the server
  revokes the row. Deleting only locally leaves a valid token in the database.

## Misconceptions

**"The app sandbox means other apps can't read it, so it's encrypted."** Sandbox
is access control; encryption is encryption. Root, backups and forensic tools all
go around a sandbox.

**"I'll encrypt it myself before AsyncStorage."** Then where does the key live?
In the app — which is the problem you were solving. The Keystore exists precisely
because the key must live somewhere the app cannot read.

**"Biometric unlock is a second factor."** It is a local gate on a stored
credential. The server sees a valid token either way. Useful defence in depth;
not MFA.

**"I can hide the token with obfuscation."** You can make it take ten minutes
instead of two. Anything shipped to a client is readable by whoever holds it.

## Remember this

- `AsyncStorage` is an **unencrypted file**. Never put credentials in it.
- Keychain/Keystore keep the encryption key **outside your app** — that's the
  whole point.
- SecureStore is native → **one APK rebuild**, not an OTA.
- Assume every secret you ship is readable. The best outcome is shipping none —
  which is exactly what this project achieves.
