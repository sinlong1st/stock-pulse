/**
 * Design tokens — transcribed from the Claude Design handoff
 * (design/project/StockPulse.dc.html). "Modernist" system:
 * Archivo type, 0px radius, cornflower accent. Dark is the default theme.
 *
 * Sentiment/importance carry shape + label, never hue alone (see components).
 */

export type ThemeColors = {
  bg: string;
  surface: string;
  surface2: string;
  elevated: string;
  text: string;
  muted: string;
  faint: string;
  divider: string;
  dividerStrong: string;
  accent: string;
  accentInk: string;
  accentBg: string;
  onAccent: string;
  bull: string;
  bullInk: string;
  bullBg: string;
  bear: string;
  bearInk: string;
  bearBg: string;
  neutral: string;
  neutralInk: string;
  neutralBg: string;
  shimmer: string;
  shimmer2: string;
};

export const dark: ThemeColors = {
  bg: '#151312',
  surface: '#201e1d',
  surface2: '#2b2827',
  elevated: '#2b2827',
  text: '#f3f2f2',
  muted: '#9b9797',
  faint: '#726f6e',
  divider: 'rgba(243,242,242,0.13)',
  dividerStrong: 'rgba(243,242,242,0.34)',
  accent: '#6495ED',
  accentInk: '#a9c6f5',
  accentBg: 'rgba(100,149,237,0.18)',
  onAccent: '#0f1b2e',
  bull: '#3fbf6a',
  bullInk: '#7ad598',
  bullBg: 'rgba(63,191,106,0.16)',
  bear: '#e5942f',
  bearInk: '#f0b25e',
  bearBg: 'rgba(229,148,47,0.16)',
  neutral: '#9b9797',
  neutralInk: '#b6b3b3',
  neutralBg: 'rgba(155,151,151,0.16)',
  shimmer: 'rgba(243,242,242,0.07)',
  shimmer2: 'rgba(243,242,242,0.14)',
};

export const light: ThemeColors = {
  bg: '#f3f2f2',
  surface: '#eae9e9',
  surface2: '#e0dedd',
  elevated: '#ffffff',
  text: '#201e1d',
  muted: '#726f6e',
  faint: '#9b9797',
  divider: 'rgba(32,30,29,0.15)',
  dividerStrong: 'rgba(32,30,29,0.4)',
  accent: '#6495ED',
  accentInk: '#2f5aa8',
  accentBg: '#dde8fb',
  onAccent: '#0f1b2e',
  bull: '#1a7d3c',
  bullInk: '#155f2e',
  bullBg: '#e0efe4',
  bear: '#b3590f',
  bearInk: '#8a440b',
  bearBg: '#f4e6d7',
  neutral: '#605d5d',
  neutralInk: '#444141',
  neutralBg: '#e2dfde',
  shimmer: 'rgba(32,30,29,0.055)',
  shimmer2: 'rgba(32,30,29,0.11)',
};

/** 4px base scale. */
export const space = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
} as const;

/** Sharp corners are the brand — radius is 0 everywhere. */
export const radius = 0;

/**
 * Type scale. Archivo is the brand face (heavy 800–900 headings); until the
 * font is bundled we fall back to the system sans, which honors these weights.
 * Add @expo-google-fonts/archivo to swap it in — see README.
 */
export const type = {
  family: undefined as string | undefined, // set to 'Archivo_800ExtraBold' etc. once bundled
  display: { fontSize: 34, fontWeight: '900' as const, letterSpacing: -1 },
  title: { fontSize: 24, fontWeight: '800' as const, letterSpacing: -0.5 },
  headline: { fontSize: 15, fontWeight: '700' as const },
  body: { fontSize: 13, fontWeight: '400' as const },
  label: { fontSize: 10, fontWeight: '800' as const, letterSpacing: 1 },
};
