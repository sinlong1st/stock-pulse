/**
 * Maps domain enums → colors + glyph/label. Every semantic signal pairs color
 * with a glyph and a word so it never relies on hue alone (color-blind safe).
 */
import { Importance, Sentiment } from '../data/types';
import { ThemeColors } from './tokens';

export function sentiment(colors: ThemeColors, s: Sentiment) {
  switch (s) {
    case 'BULLISH':
      return { fg: colors.bull, ink: colors.bullInk, bg: colors.bullBg, glyph: '▲', label: 'BULLISH' };
    case 'BEARISH':
      return { fg: colors.bear, ink: colors.bearInk, bg: colors.bearBg, glyph: '▼', label: 'BEARISH' };
    default:
      return { fg: colors.neutral, ink: colors.neutralInk, bg: colors.neutralBg, glyph: '→', label: 'NEUTRAL' };
  }
}

/** Signed % → the sentiment color to tint a price change. */
export function changeColor(colors: ThemeColors, pct: number) {
  if (pct > 0.05) return colors.bull;
  if (pct < -0.05) return colors.bear;
  return colors.neutral;
}

/** Format a signed % with a direction glyph, e.g. "▼ 4.2%". */
export function formatChange(pct: number) {
  const glyph = pct > 0.05 ? '▲' : pct < -0.05 ? '▼' : '→';
  return `${glyph} ${Math.abs(pct).toFixed(1)}%`;
}

const IMPORTANCE_CELLS: Record<Importance, number> = {
  LOW: 1,
  MEDIUM: 2,
  HIGH: 3,
  CRITICAL: 4,
};

/** Importance → notch count (of 4) + its color pairing. */
export function importance(colors: ThemeColors, i: Importance) {
  const filled = IMPORTANCE_CELLS[i];
  switch (i) {
    case 'CRITICAL':
      return { filled, fg: colors.bear, bg: colors.bearBg, label: 'CRITICAL' };
    case 'HIGH':
      return { filled, fg: colors.bearInk, bg: colors.bearBg, label: 'HIGH' };
    case 'MEDIUM':
      return { filled, fg: colors.accentInk, bg: colors.accentBg, label: 'MEDIUM' };
    default:
      return { filled, fg: colors.neutralInk, bg: colors.neutralBg, label: 'LOW' };
  }
}
