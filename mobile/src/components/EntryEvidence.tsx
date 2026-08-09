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

/**
 * Whole-number reward : risk. A raw ratio reads badly below 1 — "0.1 : 1" is
 * hard to parse — so the smaller side is normalised to 1 and the label stays
 * "reward : risk" either way. 2.1 -> "2 : 1"; 0.1 -> "1 : 10".
 *
 * The tone is derived from the *rendered* pair, not the raw ratio, so a 0.9 that
 * displays as "1 : 1" isn't also painted red as though it were lopsided.
 */
export function formatRatio(ratio: number): { text: string; reward: number; risk: number } {
  const [reward, risk] =
    ratio >= 1
      ? [Math.max(1, Math.round(ratio)), 1]
      : [1, Math.max(1, Math.round(1 / ratio))];
  return { text: `${reward} : ${risk}`, reward, risk };
}

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

      {rewardRisk != null ? (() => {
        const { text, reward, risk } = formatRatio(rewardRisk);
        const lopsided = risk > reward; // shows as 1 : 2 or worse
        const tone = reward >= 2 ? colors.bull : lopsided ? colors.bear : colors.accentInk;
        return (
          <View style={[styles.ratioRow, { backgroundColor: colors.accentBg }]}>
            <Text style={[styles.ratioLabel, { color: colors.accentInk }]}>{t('ev.ratio')}</Text>
            <View style={styles.ratioRight}>
              <Text style={[styles.ratioValue, { color: tone }]}>{text}</Text>
              {lopsided ? (
                <Text style={[styles.ratioNote, { color: colors.bear }]}>{t('ev.poorRatio')}</Text>
              ) : null}
            </View>
          </View>
        );
      })() : null}

      {invalidation != null ? (
        <Text style={[styles.invalidation, { color: colors.faint }]}>
          {t('ev.invalidation', { level: `$${invalidation.toFixed(2)}` })}
        </Text>
      ) : null}
    </View>
  );
}

/**
 * What the deterministic risk rules found.
 *
 * Rendered whenever any rule fires, not only when one changed the verdict. A rule
 * that merely *agrees* with the AI's caution is still telling you something
 * concrete ("price is 7.6 average days above support") that the prose isn't —
 * hiding it wasted the most checkable part of the analysis.
 *
 * The backend sends codes plus numbers, so the wording is localized here.
 */
export function RuleOverride({ rules }: { rules: NonNullable<Prediction['rules']> }) {
  const { colors } = useTheme();
  const { t } = useI18n();

  if (!rules.findings.length) return null;

  // An override changed the answer and is worth alarming about; a confirmation
  // is context, so it gets a calmer treatment.
  const tone = rules.overridden ? colors.bear : colors.muted;

  return (
    <View style={[styles.block, styles.override, { borderColor: tone }]}>
      <View style={styles.overrideTop}>
        <Feather name="shield" size={12} color={tone} />
        <Text style={[styles.label, { color: tone }]}>
          {rules.overridden ? t('rules.title') : t('rules.titleChecks')}
        </Text>
      </View>
      <Text style={[styles.overrideLead, { color: colors.text }]}>
        {rules.overridden
          ? t('rules.downgraded', {
              from: t(`predict.entry.${rules.original}`),
              to: t(`predict.entry.${rules.final}`),
            })
          : t('rules.confirmed', { verdict: t(`predict.entry.${rules.final}`) })}
      </Text>
      {rules.findings.map((f) => (
        <View key={f.code} style={styles.bulletRow}>
          <Text style={[styles.bullet, { color: colors.faint }]}>●</Text>
          {/* Unknown codes fall back to the key, so a new backend rule shows
              something rather than an empty bullet. */}
          <Text style={[styles.bulletText, { color: colors.muted }]}>
            {t(`rules.${f.code}`, f.params)}
          </Text>
        </View>
      ))}
    </View>
  );
}

/**
 * A second model's independent read of the same evidence.
 *
 * Shown as its own verdict rather than blended into the main one. Two models
 * agreeing is weak evidence — they train on overlapping data and can be wrong
 * together — but two models *disagreeing* is a genuine signal that the setup is
 * ambiguous, and averaging them away would destroy exactly that.
 */
export function SecondOpinion({
  second,
}: {
  second: NonNullable<Prediction['secondOpinion']>;
}) {
  const { colors } = useTheme();
  const { t } = useI18n();

  // `agreement` is absent when the droplet is still on an older build, so the
  // boolean stays as the fallback. It only ever compared entry grades, which is
  // why it reported a red "disagrees" for reads that pointed the same way.
  const level = second.agreement?.actionAgreement ?? (second.agrees ? 'strong' : 'conflict');
  const tone =
    level === 'strong' ? colors.bull : level === 'conflict' ? colors.bear : colors.muted;

  // Params arrive as backend codes ("fair", "bounce"); localize them here rather
  // than shipping English through a Vietnamese sentence.
  const localize = (code: string, params: Record<string, string | number>) => {
    const out: Record<string, string | number> = { ...params };
    if (code === 'entry-differs') {
      out.primary = t(`predict.entry.${params.primary}`);
      out.second = t(`predict.entry.${params.second}`);
    } else if (code === 'direction-opposed') {
      out.primary = t(`predict.lean.${params.primary}`);
      out.second = t(`predict.lean.${params.second}`);
    }
    return t(`second.${code}`, out);
  };

  return (
    <View style={[styles.block, styles.override, { borderColor: colors.dividerStrong }]}>
      <View style={styles.overrideTop}>
        <Feather name="users" size={12} color={colors.muted} />
        <Text style={[styles.label, { color: colors.muted }]}>
          {t('second.title', { model: second.provider })}
        </Text>
        <Text style={[styles.secondVerdict, { color: tone }]}>
          {t(`predict.entry.${second.entry}`)}
        </Text>
      </View>
      <Text style={[styles.bulletText, { color: colors.muted }]}>{second.note}</Text>
      <Text style={[styles.secondAgree, { color: tone }]}>{t(`second.${level}`)}</Text>
      {/* What specifically differs — the part a reader can actually check. */}
      {second.agreement?.differences.map((d) => (
        <View key={d.code} style={styles.bulletRow}>
          <Text style={[styles.bullet, { color: colors.faint }]}>●</Text>
          <Text style={[styles.bulletText, { color: colors.muted }]}>
            {localize(d.code, d.params)}
          </Text>
        </View>
      ))}
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
  override: { borderTopWidth: 0, borderWidth: 1, padding: 10 },
  overrideTop: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  overrideLead: { fontSize: 12, fontWeight: '700', lineHeight: 17, marginBottom: 2 },
  secondVerdict: { marginLeft: 'auto', fontSize: 11, fontWeight: '900', letterSpacing: 0.4 },
  secondAgree: { fontSize: 10, fontWeight: '800', letterSpacing: 0.3, marginTop: 2 },
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
  ratioLabel: { fontSize: 9.5, fontWeight: '900', letterSpacing: 0.8, flex: 1 },
  ratioRight: { alignItems: 'flex-end' },
  ratioValue: { fontSize: 15, fontWeight: '900', fontVariant: ['tabular-nums'] },
  ratioNote: { fontSize: 8.5, fontWeight: '800', letterSpacing: 0.3, marginTop: 1 },
  invalidation: { fontSize: 10, lineHeight: 15, marginTop: 3 },
  bulletRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 7 },
  bullet: { fontSize: 7, lineHeight: 16 },
  bulletText: { flex: 1, fontSize: 11.5, lineHeight: 16 },
  riskLabel: { marginTop: 8 },
});
