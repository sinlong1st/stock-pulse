/**
 * Earnings presentation: when a stock next reports, and how the last report
 * landed vs expectations. Shared so the Report list and the Predict chip agree
 * on wording, colour and date formatting.
 *
 * Every field is best-effort (the backend hides the section entirely when Yahoo
 * is unavailable), so each piece renders only when its data is actually there.
 */
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { EarningsRow } from '../data/types';
import { useI18n } from '../i18n/LanguageContext';
import { ThemeColors } from '../theme/tokens';
import { useTheme } from '../theme/ThemeContext';

/** Short, locale-appropriate date — "29 Oct" / "29 thg 10". */
export function formatEarningsDate(iso: string | null | undefined, vi: boolean): string | null {
  if (!iso) return null;
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString(vi ? 'vi-VN' : 'en-GB', { day: 'numeric', month: 'short' });
}

export function verdictColor(colors: ThemeColors, verdict?: string | null) {
  if (verdict === 'beat') return colors.bull;
  if (verdict === 'miss') return colors.bear;
  return colors.neutral;
}

/**
 * "in 3 days" / "tomorrow" / "today" / "2 days ago". Returns null without a date.
 * Yahoo's date can drift into the past before the new one is published, so the
 * past case is handled rather than shown as a negative countdown.
 */
export function useCountdown() {
  const { t } = useI18n();
  return (days: number | null | undefined): string | null => {
    if (days == null) return null;
    if (days === 0) return t('earn.today');
    if (days === 1) return t('earn.tomorrow');
    if (days > 1) return t('earn.inDays', { n: days });
    if (days === -1) return t('earn.yesterday');
    return t('earn.daysAgo', { n: Math.abs(days) });
  };
}

/**
 * One row: when the stock next reports, and — on a clearly separate, labelled
 * line — how the LAST quarter went. The two must never blur together: an EPS
 * figure sitting under an upcoming date reads as a forecast for that date, when
 * it is actually a already-published historical result.
 */
export function EarningsRowView({ row }: { row: EarningsRow }) {
  const { colors } = useTheme();
  const { t, vi } = useI18n();
  const countdown = useCountdown();

  const when = formatEarningsDate(row.nextDate, vi);
  const rel = countdown(row.daysUntil);
  const quarter = formatEarningsDate(row.quarterEnd, vi);
  // Yahoo returns the just-passed report date until it publishes the next
  // estimate, so a negative countdown means this already happened.
  const reported = row.daysUntil != null && row.daysUntil < 0;
  // Yahoo often knows the quarter's EPS but not the exact upcoming date, and
  // vice versa — so the two halves render independently.
  const hasResult = row.epsActual != null && row.epsEstimate != null;

  return (
    <View style={[styles.row, { borderBottomColor: colors.divider }]}>
      <Text style={[styles.ticker, { color: colors.text }]}>{row.ticker}</Text>

      <View style={styles.mid}>
        {/* Labels are inline spans, not a fixed-width column — a column sized
            for "NEXT" breaks longer labels like "ĐÃ CÔNG BỐ" across two lines. */}
        <Text style={[styles.next, { color: colors.text }]}>
          <Text style={[styles.inlineLabel, { color: colors.faint }]}>
            {(reported ? t('earn.reportedLabel') : t('earn.nextLabel')) + '  '}
          </Text>
          {when ? (
            <>
              {when}
              {rel ? <Text style={{ color: colors.faint }}> · {rel}</Text> : null}
              {!reported && row.nextIsEstimate ? (
                <Text style={{ color: colors.faint }}> · {t('earn.estimated')}</Text>
              ) : null}
            </>
          ) : (
            <Text style={{ color: colors.faint }}>{t('earn.noDate')}</Text>
          )}
        </Text>

        {hasResult ? (
          <View style={styles.line}>
            <Text style={[styles.eps, { color: colors.muted }]}>
              <Text style={[styles.inlineLabel, { color: colors.faint }]}>
                {t('earn.lastLabel') + '  '}
              </Text>
              {quarter ? `${t('earn.qEnded', { d: quarter })} · ` : ''}
              {t('earn.eps')} {row.epsActual?.toFixed(2)} {t('earn.vs')}{' '}
              {row.epsEstimate?.toFixed(2)} {t('earn.est')}
            </Text>
            {row.verdict ? (
              <View
                style={[
                  styles.badge,
                  { backgroundColor: verdictColor(colors, row.verdict) + '22' },
                ]}
              >
                <Text style={[styles.badgeText, { color: verdictColor(colors, row.verdict) }]}>
                  {t(`earn.${row.verdict}`)}
                  {row.surprisePct != null
                    ? ` ${row.surprisePct > 0 ? '+' : ''}${row.surprisePct}%`
                    : ''}
                </Text>
              </View>
            ) : null}
          </View>
        ) : null}
      </View>
    </View>
  );
}

/** Compact one-line form for the Predict screen. */
export function NextEarningsChip({ row }: { row: EarningsRow }) {
  const { colors } = useTheme();
  const { t, vi } = useI18n();
  const countdown = useCountdown();

  const when = formatEarningsDate(row.nextDate, vi);
  if (!when) return null;
  const rel = countdown(row.daysUntil);
  const reported = row.daysUntil != null && row.daysUntil < 0;
  // Inside a week the report dominates any short-horizon read — flag it. A
  // report already behind us is context, not a warning, so it stays neutral.
  const soon = !reported && row.daysUntil != null && row.daysUntil >= 0 && row.daysUntil <= 7;

  return (
    <View
      style={[
        styles.chip,
        { borderColor: soon ? colors.accent : colors.dividerStrong },
      ]}
    >
      <Text style={[styles.chipLabel, { color: colors.faint }]}>
        {reported ? t('earn.reportedLabel') : t('earn.next')}
      </Text>
      <Text style={[styles.chipValue, { color: soon ? colors.accent : colors.text }]}>
        {when}
        {rel ? ` · ${rel}` : ''}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', gap: 10, paddingVertical: 10, borderBottomWidth: 1 },
  ticker: { fontSize: 12.5, fontWeight: '800', width: 46, paddingTop: 1 },
  mid: { flex: 1, gap: 4 },
  line: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  inlineLabel: { fontSize: 8.5, fontWeight: '900', letterSpacing: 0.7 },
  next: { fontSize: 12, fontWeight: '700' },
  // flexShrink keeps the verdict badge on this line instead of bumping it down
  // whenever the EPS text runs long.
  eps: { fontSize: 10.5, flexShrink: 1 },
  badge: { paddingHorizontal: 7, paddingVertical: 3 },
  badgeText: { fontSize: 9.5, fontWeight: '900', letterSpacing: 0.3 },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    borderWidth: 1,
    paddingHorizontal: 9,
    paddingVertical: 5,
    alignSelf: 'flex-start',
  },
  chipLabel: { fontSize: 9, fontWeight: '900', letterSpacing: 0.8 },
  chipValue: { fontSize: 11.5, fontWeight: '800' },
});
