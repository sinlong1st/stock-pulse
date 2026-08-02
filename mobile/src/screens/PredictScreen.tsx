import { Feather } from '@expo/vector-icons';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import React, { useState } from 'react';
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { MiniBars } from '../components/MiniBars';
import { Segmented } from '../components/Segmented';
import { fetchPrediction, Lean, Prediction, PredictionHorizon } from '../data/api';
import { RootStackParamList } from '../navigation/types';
import { ThemeColors } from '../theme/tokens';
import { useTheme } from '../theme/ThemeContext';

const RANGES: Record<string, number> = { '1W': 5, '1M': 21, '3M': 63, '6M': 130 };
const ENTRY_LABEL = { good: 'GOOD ENTRY', fair: 'FAIR', wait: 'WAIT' } as const;

function entryColor(c: ThemeColors, a: 'good' | 'fair' | 'wait') {
  if (a === 'good') return c.bull;
  if (a === 'wait') return c.bear;
  return c.neutral;
}

type Props = NativeStackScreenProps<RootStackParamList, 'Predict'>;

function leanMeta(c: ThemeColors, lean: Lean) {
  if (lean === 'bounce') return { fg: c.bull, bg: c.bullBg, glyph: '▲', label: 'BOUNCE' };
  if (lean === 'dip') return { fg: c.bear, bg: c.bearBg, glyph: '▼', label: 'DIP' };
  return { fg: c.neutral, bg: c.neutralBg, glyph: '→', label: 'HOLD' };
}

function signalColor(c: ThemeColors, kind: 'cheap' | 'rich' | 'fair' | 'up' | 'down' | 'sideways') {
  if (kind === 'cheap' || kind === 'up') return c.bull;
  if (kind === 'rich' || kind === 'down') return c.bear;
  return c.neutral;
}

/** Confidence-weighted vote across the horizons → one headline lean. */
function overallLean(horizons?: PredictionHorizon[]): Lean {
  if (!horizons?.length) return 'hold';
  const w = { low: 1, medium: 2, high: 3 } as const;
  const score: Record<Lean, number> = { bounce: 0, dip: 0, hold: 0 };
  for (const h of horizons) score[h.lean] += w[h.confidence] ?? 1;
  return (['bounce', 'dip', 'hold'] as Lean[]).reduce((a, b) => (score[b] > score[a] ? b : a), 'hold');
}

export function PredictScreen({ navigation }: Props) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const [query, setQuery] = useState('');
  const [pred, setPred] = useState<Prediction | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modal, setModal] = useState(false);
  const [range, setRange] = useState('3M');

  const run = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const p = await fetchPrediction(query);
      if (p.ok) setPred(p);
      else {
        setPred(null);
        setError(p.reason ?? 'Couldn’t generate a read.');
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Couldn’t generate a read.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <View style={[styles.topbar, { borderBottomColor: colors.dividerStrong }]}>
        <Feather name="arrow-left" size={22} color={colors.text} onPress={() => navigation.goBack()} />
        <Text style={[styles.topbarTitle, { color: colors.text }]}>Predict</Text>
      </View>

      {/* input */}
      <View style={styles.inputRow}>
        <TextInput
          value={query}
          onChangeText={setQuery}
          placeholder="Ticker or company, e.g. WDC"
          placeholderTextColor={colors.faint}
          autoCapitalize="characters"
          autoCorrect={false}
          onSubmitEditing={run}
          style={[styles.input, { color: colors.text, backgroundColor: colors.surface, borderColor: colors.dividerStrong }]}
        />
        <Pressable
          onPress={run}
          disabled={loading || !query.trim()}
          style={[styles.go, { backgroundColor: colors.accent, opacity: loading || !query.trim() ? 0.4 : 1 }]}
        >
          {loading ? (
            <ActivityIndicator size="small" color={colors.onAccent} />
          ) : (
            <Text style={[styles.goText, { color: colors.onAccent }]}>Predict</Text>
          )}
        </Pressable>
      </View>

      {error ? (
        <View style={styles.center}>
          <Feather name="alert-triangle" size={30} color={colors.accent} />
          <Text style={[styles.centerBody, { color: colors.muted }]}>{error}</Text>
        </View>
      ) : !pred ? (
        <View style={styles.center}>
          <Feather name="compass" size={34} color={colors.muted} />
          <Text style={[styles.centerTitle, { color: colors.text }]}>Forward-looking read</Text>
          <Text style={[styles.centerBody, { color: colors.muted }]}>
            Enter a stock and the AI gives a 1-week / 1-month / 3-month lean, grounded in real price
            signals + news. Speculative — not investment advice.
          </Text>
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={[styles.body, { paddingBottom: insets.bottom + 28 }]}
          showsVerticalScrollIndicator={false}
        >
          {/* header */}
          <View style={styles.head}>
            <Text style={[styles.ticker, { color: colors.text }]}>{pred.ticker}</Text>
            <Text style={[styles.name, { color: colors.muted }]}>{pred.name}</Text>
            {pred.price ? (
              <Text style={[styles.price, { color: colors.text }]}>
                ${pred.price} <Text style={{ color: colors.faint, fontSize: 10 }}>{pred.priceFresh}</Text>
              </Text>
            ) : null}
          </View>

          {/* big headline read */}
          {(() => {
            const m = leanMeta(colors, overallLean(pred.horizons));
            return (
              <View style={[styles.headline, { backgroundColor: m.bg }]}>
                <Text style={[styles.headlineKicker, { color: m.fg }]}>AI READ · NEXT 1–3 MONTHS</Text>
                <View style={styles.headlineRow}>
                  <Text style={[styles.headlineGlyph, { color: m.fg }]}>{m.glyph}</Text>
                  <Text style={[styles.headlineLean, { color: m.fg }]}>{m.label}</Text>
                </View>
              </View>
            );
          })()}

          {/* entry advice */}
          {pred.entry ? (
            <View style={[styles.entry, { borderColor: colors.divider }]}>
              <View style={styles.entryTop}>
                <Text style={[styles.entryLabel, { color: colors.muted }]}>IS THIS A GOOD ENTRY?</Text>
                <View style={[styles.entryBadge, { backgroundColor: entryColor(colors, pred.entry.assessment) + '22' }]}>
                  <Text style={[styles.entryBadgeText, { color: entryColor(colors, pred.entry.assessment) }]}>
                    {ENTRY_LABEL[pred.entry.assessment]}
                  </Text>
                </View>
              </View>
              <Text style={[styles.entryNote, { color: colors.text }]}>{pred.entry.note}</Text>
              {pred.supportZones?.length ? (
                <View style={styles.supportRow}>
                  <Text style={[styles.supportLabel, { color: colors.muted }]}>SUPPORT</Text>
                  {pred.supportZones.map((s) => (
                    <View key={s} style={[styles.supportChip, { borderColor: colors.dividerStrong }]}>
                      <Text style={[styles.supportChipText, { color: colors.text }]}>${s.toFixed(2)}</Text>
                    </View>
                  ))}
                </View>
              ) : null}
            </View>
          ) : null}

          {/* charts with range selector */}
          {pred.series?.closes?.length ? (
            <View style={styles.chartBlock}>
              <View style={styles.chartHead}>
                <Text style={[styles.chartLabel, { color: colors.muted }]}>
                  PRICE {pred.price ? `· $${pred.price}` : ''}
                </Text>
                <Segmented
                  options={['1W', '1M', '3M', '6M']}
                  value={range}
                  onChange={setRange}
                />
              </View>
              <MiniBars
                values={pred.series.closes.slice(-RANGES[range])}
                color={colors.accent}
                lastColor={colors.accentInk}
                height={64}
              />
              <Text style={[styles.chartLabel, { color: colors.muted, marginTop: 14 }]}>VOLUME</Text>
              <MiniBars values={pred.series.volumes.slice(-RANGES[range])} color={colors.faint} height={36} />
            </View>
          ) : null}

          {/* discount + trend chips */}
          <View style={styles.chips}>
            {pred.discount ? (
              <View style={[styles.chip, { backgroundColor: signalColor(colors, pred.discount.level) + '22' }]}>
                <Text style={[styles.chipText, { color: signalColor(colors, pred.discount.level) }]}>
                  {pred.discount.level.toUpperCase()}
                </Text>
              </View>
            ) : null}
            {pred.trend ? (
              <View style={[styles.chip, { backgroundColor: signalColor(colors, pred.trend) + '22' }]}>
                <Text style={[styles.chipText, { color: signalColor(colors, pred.trend) }]}>
                  TREND {pred.trend.toUpperCase()}
                </Text>
              </View>
            ) : null}
          </View>
          {pred.discount?.vsRangeNote ? (
            <Text style={[styles.rangeNote, { color: colors.muted }]}>
              {pred.discount.note} {pred.discount.vsRangeNote}.
            </Text>
          ) : null}

          {/* horizons */}
          <View style={styles.horizons}>
            {pred.horizons?.map((h) => {
              const m = leanMeta(colors, h.lean);
              return (
                <View key={h.horizon} style={[styles.hRow, { borderTopColor: colors.divider }]}>
                  <Text style={[styles.hLabel, { color: colors.text }]}>{h.horizon}</Text>
                  <View style={[styles.leanPill, { backgroundColor: m.bg }]}>
                    <Text style={[styles.leanGlyph, { color: m.fg }]}>{m.glyph}</Text>
                    <Text style={[styles.leanText, { color: m.fg }]}>{m.label}</Text>
                  </View>
                  <Text style={[styles.conf, { color: colors.faint }]}>{h.confidence}</Text>
                  <Text style={[styles.rationale, { color: colors.muted }]}>{h.rationale}</Text>
                </View>
              );
            })}
          </View>

          {/* drivers */}
          {pred.drivers?.length ? (
            <>
              <Text style={[styles.sectionLabel, { color: colors.muted }]}>DRIVERS</Text>
              {pred.drivers.map((d, i) => (
                <Text key={i} style={[styles.driver, { color: colors.text }]}>
                  • {d}
                </Text>
              ))}
            </>
          ) : null}

          {/* strategy + disclaimer */}
          {pred.strategy ? (
            <Pressable onPress={() => setModal(true)} style={styles.stratRow}>
              <Feather name="info" size={13} color={colors.accentInk} />
              <Text style={[styles.stratText, { color: colors.accentInk }]}>
                How this reads the stock · {pred.strategy.name}
              </Text>
            </Pressable>
          ) : null}
          <Text style={[styles.disclaimer, { color: colors.faint }]}>{pred.disclaimer}</Text>
        </ScrollView>
      )}

      {/* strategy modal */}
      <Modal visible={modal} transparent animationType="fade" onRequestClose={() => setModal(false)}>
        <Pressable style={styles.backdrop} onPress={() => setModal(false)}>
          <Pressable style={[styles.sheet, { backgroundColor: colors.elevated }]} onPress={() => {}}>
            <Text style={[styles.sheetKicker, { color: colors.accent }]}>STRATEGY</Text>
            <Text style={[styles.sheetTitle, { color: colors.text }]}>{pred?.strategy?.name}</Text>
            <Text style={[styles.sheetBody, { color: colors.muted }]}>{pred?.strategy?.body}</Text>
            <Text style={[styles.sheetNote, { color: colors.faint }]}>
              This framework shapes how the AI weighs the evidence. The real numbers (price, discount,
              trend) are computed from market data — the strategy never changes them.
            </Text>
            <Pressable onPress={() => setModal(false)} style={[styles.sheetBtn, { backgroundColor: colors.accent }]}>
              <Text style={[styles.sheetBtnText, { color: colors.onAccent }]}>Got it</Text>
            </Pressable>
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 14, paddingTop: 6, paddingBottom: 12, borderBottomWidth: 2 },
  topbarTitle: { fontSize: 14, fontWeight: '800' },
  inputRow: { flexDirection: 'row', gap: 8, paddingHorizontal: 16, paddingVertical: 12 },
  input: { flex: 1, borderWidth: 1, paddingHorizontal: 12, paddingVertical: 10, fontSize: 14, fontWeight: '600' },
  go: { paddingHorizontal: 18, alignItems: 'center', justifyContent: 'center', minWidth: 84 },
  goText: { fontSize: 14, fontWeight: '800' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12, padding: 32 },
  centerTitle: { fontSize: 18, fontWeight: '900' },
  centerBody: { fontSize: 13, textAlign: 'center', lineHeight: 19, maxWidth: 280 },
  body: { padding: 16 },
  head: { marginBottom: 12 },
  ticker: { fontSize: 26, fontWeight: '900', letterSpacing: -0.5 },
  name: { fontSize: 12, marginTop: 1 },
  price: { fontSize: 15, fontWeight: '800', marginTop: 6, fontVariant: ['tabular-nums'] },
  headline: { paddingVertical: 14, paddingHorizontal: 16, marginBottom: 14 },
  headlineKicker: { fontSize: 10, fontWeight: '900', letterSpacing: 1 },
  headlineRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 4 },
  headlineGlyph: { fontSize: 30, fontWeight: '900' },
  headlineLean: { fontSize: 34, fontWeight: '900', letterSpacing: -1 },
  entry: { borderWidth: 1, padding: 14, marginBottom: 16, gap: 8 },
  entryTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  entryLabel: { fontSize: 10, fontWeight: '900', letterSpacing: 1 },
  entryBadge: { paddingHorizontal: 10, paddingVertical: 4 },
  entryBadgeText: { fontSize: 11, fontWeight: '900', letterSpacing: 0.5 },
  entryNote: { fontSize: 14, lineHeight: 20, fontWeight: '600' },
  supportRow: { flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginTop: 2 },
  supportLabel: { fontSize: 9, fontWeight: '900', letterSpacing: 0.8 },
  supportChip: { borderWidth: 1, paddingHorizontal: 8, paddingVertical: 3 },
  supportChipText: { fontSize: 11, fontWeight: '800', fontVariant: ['tabular-nums'] },
  chartBlock: { marginBottom: 16 },
  chartHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, gap: 8, flexWrap: 'wrap' },
  chartLabel: { fontSize: 10, fontWeight: '900', letterSpacing: 1 },
  chartVal: { fontSize: 13, fontWeight: '800', fontVariant: ['tabular-nums'] },
  chips: { flexDirection: 'row', gap: 8 },
  chip: { paddingHorizontal: 9, paddingVertical: 4 },
  chipText: { fontSize: 10, fontWeight: '900', letterSpacing: 0.5 },
  rangeNote: { fontSize: 12, marginTop: 8, lineHeight: 17 },
  horizons: { marginTop: 16 },
  hRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 11, borderTopWidth: 1, flexWrap: 'wrap' },
  hLabel: { fontSize: 13, fontWeight: '900', width: 34 },
  leanPill: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 8, paddingVertical: 3 },
  leanGlyph: { fontSize: 11, fontWeight: '900' },
  leanText: { fontSize: 9, fontWeight: '800', letterSpacing: 0.4 },
  conf: { fontSize: 10, fontWeight: '700' },
  rationale: { flexBasis: '100%', fontSize: 12, lineHeight: 17, marginTop: 2 },
  sectionLabel: { fontSize: 10, fontWeight: '900', letterSpacing: 1, marginTop: 18, marginBottom: 6 },
  driver: { fontSize: 13, lineHeight: 20 },
  stratRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 18 },
  stratText: { fontSize: 12, fontWeight: '800' },
  disclaimer: { fontSize: 10, fontWeight: '600', marginTop: 12 },
  backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.45)', justifyContent: 'center', padding: 24 },
  sheet: { padding: 20, gap: 8 },
  sheetKicker: { fontSize: 10, fontWeight: '900', letterSpacing: 1 },
  sheetTitle: { fontSize: 20, fontWeight: '900' },
  sheetBody: { fontSize: 13.5, lineHeight: 20 },
  sheetNote: { fontSize: 11, lineHeight: 16, marginTop: 4 },
  sheetBtn: { marginTop: 10, paddingVertical: 12, alignItems: 'center' },
  sheetBtnText: { fontSize: 14, fontWeight: '800' },
});
