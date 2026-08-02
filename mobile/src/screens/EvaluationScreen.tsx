import { Feather } from '@expo/vector-icons';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import React, { useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { SentimentPill } from '../components/SentimentPill';
import { EvalReport, EvalStat, fetchEvaluation } from '../data/api';
import { RootStackParamList } from '../navigation/types';
import { useTheme } from '../theme/ThemeContext';

type Props = NativeStackScreenProps<RootStackParamList, 'Evaluation'>;

function pct(v: number | null) {
  return v == null ? '—' : `${Math.round(v)}%`;
}

function Bar({ label, stat, color }: { label: string; stat: EvalStat; color: string }) {
  const { colors } = useTheme();
  const width = stat.accuracyPct == null ? 0 : Math.max(2, Math.min(100, stat.accuracyPct));
  return (
    <View style={styles.barRow}>
      <Text style={[styles.barLabel, { color: colors.text }]}>{label}</Text>
      <View style={[styles.barTrack, { backgroundColor: colors.neutralBg }]}>
        <View style={[styles.barFill, { width: `${width}%`, backgroundColor: color }]} />
      </View>
      <Text style={[styles.barPct, { color: colors.text }]}>{pct(stat.accuracyPct)}</Text>
    </View>
  );
}

export function EvaluationScreen({ navigation }: Props) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const [report, setReport] = useState<EvalReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchEvaluation()
      .then((r) => {
        setReport(r);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Couldn’t load accuracy.'))
      .finally(() => setLoading(false));
  }, []);

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <View style={[styles.topbar, { borderBottomColor: colors.dividerStrong }]}>
        <Feather name="arrow-left" size={22} color={colors.text} onPress={() => navigation.goBack()} />
        <Text style={[styles.topbarTitle, { color: colors.text }]}>AI accuracy</Text>
      </View>

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator color={colors.accent} />
        </View>
      ) : error ? (
        <View style={styles.center}>
          <Feather name="alert-triangle" size={30} color={colors.accent} />
          <Text style={[styles.centerBody, { color: colors.muted }]}>{error}</Text>
        </View>
      ) : !report || report.totalEvaluated === 0 ? (
        <View style={styles.center}>
          <Feather name="bar-chart-2" size={30} color={colors.muted} />
          <Text style={[styles.centerTitle, { color: colors.text }]}>Not enough data yet</Text>
          <Text style={[styles.centerBody, { color: colors.muted }]}>
            Accuracy shows once the AI’s calls have had time to play out.
          </Text>
        </View>
      ) : (
        <ScrollView contentContainerStyle={{ paddingBottom: insets.bottom + 28 }} showsVerticalScrollIndicator={false}>
          {/* headline */}
          <View style={[styles.headline, { borderBottomColor: colors.divider }]}>
            <Text style={[styles.hLabel, { color: colors.muted }]}>DIRECTIONAL ACCURACY</Text>
            <View style={styles.hRow}>
              <Text style={[styles.hBig, { color: colors.text }]}>{pct(report.accuracyPct)}</Text>
              <Text style={[styles.hSub, { color: colors.muted }]}>
                of {report.totalEvaluated} calls{'\n'}scored against real moves
              </Text>
              <View style={{ marginLeft: 'auto', alignItems: 'flex-end' }}>
                <Text style={[styles.hPending, { color: colors.accentInk }]}>{report.pending}</Text>
                <Text style={[styles.hPendingLabel, { color: colors.muted }]}>PENDING</Text>
              </View>
            </View>
          </View>

          {/* per-sentiment bars */}
          <View style={[styles.bars, { borderBottomColor: colors.divider }]}>
            <Bar label="▲ BULLISH" stat={report.bullish} color={colors.bull} />
            <Bar label="▼ BEARISH" stat={report.bearish} color={colors.bear} />
          </View>

          {/* recent calls */}
          <Text style={[styles.recentLabel, { color: colors.muted }]}>RECENT CALLS</Text>
          {report.recent.map((e, i) => {
            const good = e.outcome === 'HIT';
            const bad = e.outcome === 'MISS';
            const mark = good ? '✓' : bad ? '✗' : '→';
            const markColor = good ? colors.bull : bad ? colors.bear : colors.neutral;
            return (
              <View key={`${e.ticker}-${i}`} style={[styles.recentRow, { borderTopColor: colors.divider }]}>
                <Text style={[styles.rTicker, { color: colors.text }]}>{e.ticker}</Text>
                <SentimentPill value={e.sentiment} />
                <Text style={[styles.rWhen, { color: colors.faint }]}>{e.horizon}</Text>
                <Text style={[styles.rRet, { color: markColor }]}>
                  {e.returnPct == null ? '—' : `${e.returnPct >= 0 ? '+' : ''}${e.returnPct.toFixed(1)}%`}
                </Text>
                <Text style={[styles.rMark, { color: markColor }]}>{mark}</Text>
              </View>
            );
          })}

          <Text style={[styles.footnote, { color: colors.faint }]}>
            Small sample — for reference only. Not investment advice.
          </Text>
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 14, paddingTop: 6, paddingBottom: 12, borderBottomWidth: 2 },
  topbarTitle: { fontSize: 14, fontWeight: '800' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12, padding: 32 },
  centerTitle: { fontSize: 18, fontWeight: '900' },
  centerBody: { fontSize: 13, textAlign: 'center', lineHeight: 19, maxWidth: 250 },
  headline: { padding: 16, borderBottomWidth: 2 },
  hLabel: { fontSize: 10, fontWeight: '900', letterSpacing: 1 },
  hRow: { flexDirection: 'row', alignItems: 'flex-end', gap: 12, marginTop: 8 },
  hBig: { fontSize: 56, fontWeight: '900', letterSpacing: -2, lineHeight: 56 },
  hSub: { fontSize: 12, fontWeight: '700', lineHeight: 16 },
  hPending: { fontSize: 22, fontWeight: '900' },
  hPendingLabel: { fontSize: 9, fontWeight: '800', letterSpacing: 0.5 },
  bars: { padding: 16, gap: 12, borderBottomWidth: 2 },
  barRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  barLabel: { fontSize: 10, fontWeight: '800', letterSpacing: 0.4, width: 68 },
  barTrack: { flex: 1, height: 12 },
  barFill: { height: 12 },
  barPct: { fontSize: 11, fontWeight: '800', width: 34, textAlign: 'right' },
  recentLabel: { fontSize: 10, fontWeight: '900', letterSpacing: 1, paddingHorizontal: 16, paddingTop: 14, paddingBottom: 6 },
  recentRow: { flexDirection: 'row', alignItems: 'center', gap: 9, paddingHorizontal: 16, paddingVertical: 11, borderTopWidth: 1 },
  rTicker: { fontSize: 12.5, fontWeight: '900', width: 46 },
  rWhen: { fontSize: 10, fontWeight: '700' },
  rRet: { marginLeft: 'auto', fontSize: 11, fontWeight: '800', fontVariant: ['tabular-nums'] },
  rMark: { fontSize: 13, fontWeight: '900', width: 16, textAlign: 'center' },
  footnote: { fontSize: 10, fontWeight: '600', paddingHorizontal: 16, paddingTop: 16 },
});
