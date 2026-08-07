/**
 * The working behind the entry advice.
 *
 * Everything here except `risks` is arithmetic over the same real price data the
 * charts use — no AI. The point is to let the reader audit the call rather than
 * take it on faith, so each block states a number and where it came from.
 *
 * The backend sends values, not sentences, so the phrasing below is localized.
 */
import { Feather } from '@expo/vector-icons';
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { Prediction } from '../data/api';
import { useI18n } from '../i18n/LanguageContext';
import { useTheme } from '../theme/ThemeContext';

const signed = (v: number) => `${v > 0 ? '+' : ''}${v.toFixed(1)}%`;

/** Distance to support vs distance to the range high, and what breaks the read. */
export function RiskReward({ evidence }: { evidence: NonNullable<Prediction['evidence']> }) {
  const { colors } = useTheme();
  const { t } = useI18n();
  const { supportPct, targetPct, rewardRisk, nearestSupport, resistance, invalidation } =
    evidence;

  if (supportPct == null && targetPct == null) return null;

  return (
    <View style={[styles.block, { borderTopColor: colors.divider }]}>
      <Text style={[styles.label, { color: colors.muted }]}>{t('ev.riskReward')}</Text>

      {nearestSupport != null && supportPct != null ? (
        <View style={styles.row}>
          <Feather name="arrow-down" size={12} color={colors.bear} />
          <Text style={[styles.rowLabel, { color: colors.muted }]}>{t('ev.toSupport')}</Text>
          <Text style={[styles.rowValue, { color: colors.text }]}>
            ${nearestSupport.toFixed(2)}
          </Text>
          <Text style={[styles.rowPct, { color: colors.bear }]}>{signed(supportPct)}</Text>
        </View>
      ) : null}

      {resistance != null && targetPct != null ? (
        <View style={styles.row}>
          <Feather name="arrow-up" size={12} color={colors.bull} />
          <Text style={[styles.rowLabel, { color: colors.muted }]}>{t('ev.toResistance')}</Text>
          <Text style={[styles.rowValue, { color: colors.text }]}>${resistance.toFixed(2)}</Text>
          <Text style={[styles.rowPct, { color: colors.bull }]}>{signed(targetPct)}</Text>
        </View>
      ) : null}

      {rewardRisk != null ? (
        <View style={[styles.ratioRow, { backgroundColor: colors.accentBg }]}>
          <Text style={[styles.ratioLabel, { color: colors.accentInk }]}>{t('ev.ratio')}</Text>
          <Text style={[styles.ratioValue, { color: colors.accentInk }]}>
            {rewardRisk.toFixed(1)} : 1
          </Text>
        </View>
      ) : null}

      {invalidation != null ? (
        <Text style={[styles.invalidation, { color: colors.faint }]}>
          {t('ev.invalidation', { level: `$${invalidation.toFixed(2)}` })}
        </Text>
      ) : null}
    </View>
  );
}

/** The deterministic inputs the read rests on, as scannable bullets. */
export function WhyThisCall({ evidence }: { evidence: NonNullable<Prediction['evidence']> }) {
  const { colors } = useTheme();
  const { t } = useI18n();

  const points: string[] = [];
  if (evidence.enoughHistory) {
    points.push(t(`ev.range.${evidence.discountLevel}`));
    points.push(t(`ev.trend.${evidence.trend}`));
  } else {
    points.push(t('ev.thinHistory'));
  }
  if (evidence.supportPct != null) {
    points.push(t('ev.aboveSupport', { pct: Math.abs(evidence.supportPct).toFixed(1) }));
  }
  if (evidence.earningsInDays != null && evidence.earningsInDays >= 0) {
    points.push(t('ev.earningsIn', { n: evidence.earningsInDays }));
  }
  points.push(
    evidence.newsCount > 0
      ? t('ev.headlines', { n: evidence.newsCount })
      : t('ev.noHeadlines'),
  );

  return (
    <View style={[styles.block, { borderTopColor: colors.divider }]}>
      <Text style={[styles.label, { color: colors.muted }]}>{t('ev.basedOn')}</Text>
      {points.map((p, i) => (
        <View key={i} style={styles.bulletRow}>
          <Text style={[styles.bullet, { color: colors.faint }]}>●</Text>
          <Text style={[styles.bulletText, { color: colors.muted }]}>{p}</Text>
        </View>
      ))}
    </View>
  );
}

/** Why the confidence is what it is, plus any stock-specific risks. */
export function ConfidenceBasis({
  confidence,
  risks,
}: {
  confidence: NonNullable<Prediction['confidence']>;
  risks?: string[];
}) {
  const { colors } = useTheme();
  const { t } = useI18n();

  const points: string[] = [];
  if (confidence.total > 0 && confidence.lean) {
    points.push(
      confidence.agree === confidence.total
        ? t('ev.allAgree', { n: confidence.total, lean: t(`predict.lean.${confidence.lean}`) })
        : t('ev.someAgree', {
            n: confidence.agree,
            total: confidence.total,
            lean: t(`predict.lean.${confidence.lean}`),
          }),
    );
  }
  if (confidence.signalsConflict) points.push(t('ev.conflict'));

  if (!points.length && !risks?.length) return null;

  return (
    <View style={[styles.block, { borderTopColor: colors.divider }]}>
      <Text style={[styles.label, { color: colors.muted }]}>{t('ev.confidence')}</Text>
      {points.map((p, i) => (
        <View key={i} style={styles.bulletRow}>
          <Text style={[styles.bullet, { color: colors.faint }]}>○</Text>
          <Text style={[styles.bulletText, { color: colors.muted }]}>{p}</Text>
        </View>
      ))}
      {risks?.length ? (
        <>
          <Text style={[styles.label, styles.riskLabel, { color: colors.muted }]}>
            {t('ev.risks')}
          </Text>
          {risks.map((r, i) => (
            <View key={i} style={styles.bulletRow}>
              <Feather name="alert-triangle" size={10} color={colors.bear} />
              <Text style={[styles.bulletText, { color: colors.muted }]}>{r}</Text>
            </View>
          ))}
        </>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  block: { borderTopWidth: 1, paddingTop: 10, marginTop: 10, gap: 5 },
  label: { fontSize: 9, fontWeight: '900', letterSpacing: 1 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  rowLabel: { fontSize: 11, flex: 1 },
  rowValue: { fontSize: 12, fontWeight: '800', fontVariant: ['tabular-nums'] },
  rowPct: { fontSize: 12, fontWeight: '800', width: 58, textAlign: 'right', fontVariant: ['tabular-nums'] },
  ratioRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 9,
    paddingVertical: 6,
    marginTop: 3,
  },
  ratioLabel: { fontSize: 9.5, fontWeight: '900', letterSpacing: 0.8 },
  ratioValue: { fontSize: 14, fontWeight: '900', fontVariant: ['tabular-nums'] },
  invalidation: { fontSize: 10, lineHeight: 15, marginTop: 3 },
  bulletRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 7 },
  bullet: { fontSize: 7, lineHeight: 16 },
  bulletText: { flex: 1, fontSize: 11.5, lineHeight: 16 },
  riskLabel: { marginTop: 8 },
});
