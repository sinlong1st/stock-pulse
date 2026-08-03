/**
 * App-wide language. Reads the user's choice from the backend once, provides a
 * `t(key)` translator, and lets Settings flip it live. Falls back to the key
 * (which is English-ish) if a string is missing.
 *
 * `ready` flips once that first read settles, so the app can hold the splash
 * screen instead of flashing English at a Vietnamese user for a second.
 */
import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { fetchSettings, usingMockData } from '../data/api';
import { STRINGS } from './strings';

/** Don't hold the splash longer than this if the backend is slow or down. */
const RESOLVE_TIMEOUT_MS = 2500;

type Params = Record<string, string | number>;
type I18n = {
  vi: boolean;
  language: string;
  /** False only during the very first settings read. */
  ready: boolean;
  t: (key: string, params?: Params) => string;
  setLanguage: (language: string) => void;
};

const Ctx = createContext<I18n | null>(null);

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguage] = useState('English');
  const [ready, setReady] = useState(usingMockData);

  useEffect(() => {
    if (usingMockData) return;
    let done = false;
    const settle = () => {
      if (!done) {
        done = true;
        setReady(true);
      }
    };
    // Whichever lands first wins: the real answer, or the timeout that stops a
    // dead backend from leaving the user staring at the splash forever.
    const timer = setTimeout(settle, RESOLVE_TIMEOUT_MS);
    fetchSettings()
      .then((s) => setLanguage(s.language))
      .catch(() => {})
      .finally(settle);
    return () => clearTimeout(timer);
  }, []);

  const vi = language.trim().toLowerCase() === 'vietnamese';

  const t = useCallback(
    (key: string, params?: Params) => {
      let s = STRINGS[key]?.[vi ? 'vi' : 'en'] ?? key;
      if (params) {
        for (const [p, v] of Object.entries(params)) s = s.replace(`{${p}}`, String(v));
      }
      return s;
    },
    [vi],
  );

  const value = useMemo<I18n>(
    () => ({ vi, language, ready, t, setLanguage }),
    [vi, language, ready, t],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useI18n(): I18n {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useI18n must be used inside <LanguageProvider>');
  return ctx;
}
