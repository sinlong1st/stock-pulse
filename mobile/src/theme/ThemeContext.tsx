/**
 * Theme provider + hook. Dark is the default (per the design); the user can
 * flip to light. Later this can follow the OS via `useColorScheme()`.
 */
import React, { createContext, useContext, useMemo, useState } from 'react';

import { ThemeColors, dark, light, radius, space, type } from './tokens';

export type ThemeMode = 'dark' | 'light';

type Theme = {
  mode: ThemeMode;
  colors: ThemeColors;
  space: typeof space;
  radius: number;
  type: typeof type;
  toggle: () => void;
};

const ThemeCtx = createContext<Theme | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setMode] = useState<ThemeMode>('light');

  const value = useMemo<Theme>(
    () => ({
      mode,
      colors: mode === 'dark' ? dark : light,
      space,
      radius,
      type,
      toggle: () => setMode((m) => (m === 'dark' ? 'light' : 'dark')),
    }),
    [mode],
  );

  return <ThemeCtx.Provider value={value}>{children}</ThemeCtx.Provider>;
}

export function useTheme(): Theme {
  const ctx = useContext(ThemeCtx);
  if (!ctx) throw new Error('useTheme must be used inside <ThemeProvider>');
  return ctx;
}
