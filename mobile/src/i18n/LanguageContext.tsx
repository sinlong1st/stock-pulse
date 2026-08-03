/**
 * App-wide language. Reads the user's choice from the backend once, provides a
 * `t(key)` translator, and lets Settings flip it live. Falls back to the key
 * (which is English-ish) if a string is missing.
 */
import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { fetchSettings, usingMockData } from '../data/api';
import { STRINGS } from './strings';

type Params = Record<string, string | number>;
type I18n = {
  vi: boolean;
  language: string;
  t: (key: string, params?: Params) => string;
  setLanguage: (language: string) => void;
};

const Ctx = createContext<I18n | null>(null);

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguage] = useState('English');

  useEffect(() => {
    if (usingMockData) return;
    fetchSettings()
      .then((s) => setLanguage(s.language))
      .catch(() => {});
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

  const value = useMemo<I18n>(() => ({ vi, language, t, setLanguage }), [vi, language, t]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useI18n(): I18n {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useI18n must be used inside <LanguageProvider>');
  return ctx;
}
