import { Feather } from '@expo/vector-icons';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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

import { HackerLoader, LoaderPhase } from '../components/HackerLoader';
import { MiniBars } from '../components/MiniBars';
import { PriceChart } from '../components/PriceChart';
import { ScreenHeader } from '../components/ScreenHeader';
import { Segmented } from '../components/Segmented';
import { WatchlistPicker } from '../components/WatchlistPicker';
import { fetchPrediction, isAborted, Lean, Prediction, PredictionHorizon } from '../data/api';
import { guessTicker, useWatchlist } from '../data/useWatchlist';
import { useI18n } from '../i18n/LanguageContext';
import { ThemeColors } from '../theme/tokens';
import { useTheme } from '../theme/ThemeContext';

const RANGES: Record<string, number> = { '1W': 5, '1M': 21, '3M': 63, '6M': 130 };

function leanMeta(c: ThemeColors, lean: Lean) {
  if (lean === 'bounce') return { fg: c.bull, bg: c.bullBg, glyph: '▲' };
  if (lean === 'dip') return { fg: c.bear, bg: c.bearBg, glyph: '▼' };
  return { fg: c.neutral, bg: c.neutralBg, glyph: '→' };
}

function signalColor(c: ThemeColors, kind: 'cheap' | 'rich' | 'fair' | 'up' | 'down' | 'sideways') {
  if (kind === 'cheap' || kind === 'up') return c.bull;
  if (kind === 'rich' || kind === 'down') return c.bear;
  return c.neutral;
}

function entryColor(c: ThemeColors, a: 'good' | 'fair' | 'wait') {
  if (a === 'good') return c.bull;
  if (a === 'wait') return c.bear;
  return c.neutral;
}

/** Prefer the full list; fall back to the single level older payloads carry. */
function supportList(levels?: number[], single?: number | null): number[] {
  if (levels?.length) return levels;
  return single != null ? [single] : [];
}

function SupportRow({ label, levels }: { label: string; levels: number[] }) {
  const { colors } = useTheme();
  if (!levels.length) return null;
  return (
    <View style={styles.supportRow}>
      <Text style={[styles.supportKind, { color: colors.faint }]}>{label}</Text>
      {levels.map((level, i) => (
        <View
          key={`${level}-${i}`}
          style={[
            styles.supportChip,
            // The closest floor is the one that matters most — lead with it.
            { borderColor: i === 0 ? colors.dividerStrong : colors.divider },
          ]}
        >
          <Text
            style={[styles.supportVal, { color: i === 0 ? colors.text : colors.muted }]}
          >
            ${level.toFixed(2)}
          </Text>
        </View>
      ))}
    </View>
  );
}

function overallLean(horizons?: PredictionHorizon[]): Lean {
  if (!horizons?.length) return 'hold';
  const w = { low: 1, medium: 2, high: 3 } as const;
  const score: Record<Lean, number> = { bounce: 0, dip: 0, hold: 0 };
  for (const h of horizons) score[h.lean] += w[h.confidence] ?? 1;
  return (['bounce', 'dip', 'hold'] as Lean[]).reduce((a, b) => (score[b] > score[a] ? b : a), 'hold');
}

export function PredictScreen() {
  const { colors } = useTheme();
  const { t, language } = useI18n();
  const insets = useSafeAreaInsets();
  const [query, setQuery] = useState('');
  const [pred, setPred] = useState<Prediction | null>(null);
  const [phase, setPhase] = useState<LoaderPhase>('idle');
  const [error, setError] = useState<string | null>(null);
  const loading = phase !== 'idle';
  const [modal, setModal] = useState(false);
  const [range, setRange] = useState('3M');
  // Last query that produced a read, so a language switch can re-ask the backend.
  const lastQuery = useRef<string | null>(null);

  const abort = useRef<AbortController | null>(null);

  const run = useCallback(
    /** `silent` refreshes in the background — no takeover loader. Used by the
     *  language switch, which the user didn't ask to wait for. */
    async (q?: string, { silent = false }: { silent?: boolean } = {}) => {
      const term = (q ?? query).trim();
      if (!term) return;
      abort.current?.abort(); // a new ticker replaces the in-flight run
      const ctrl = new AbortController();
      abort.current = ctrl;
      if (!silent) setPhase('running');
      setError(null);
      try {
        const p = await fetchPrediction(term, ctrl.signal);
        const mine = abort.current === ctrl;
        if (p.ok) {
          setPred(p);
          lastQuery.current = term;
          // Only a visible run gets the 100% beat; a silent refresh never showed.
          if (mine && !silent) setPhase('done');
        } else {
          setPred(null);
          setError(p.reason ?? t('predict.genErr'));
          if (mine && !silent) setPhase('idle');
        }
      } catch (e) {
        if (isAborted(e)) return; // cancelled on purpose — keep the current read
        setError(e instanceof Error ? e.message : t('predict.genErr'));
        if (abort.current === ctrl && !silent) setPhase('idle'); // no fanfare on failure
      } finally {
        if (abort.current === ctrl) abort.current = null;
      }
    },
    [query, t],
  );

  // See ReportScreen: guess from the watchlist while in flight, then show the
  // ticker the server actually resolved rather than echoing the user's typo.
  const watchlist = useWatchlist();
  const loaderHeadline = useMemo(() => {
    const resolved = phase === 'done' ? pred?.ticker : null;
    return resolved ?? guessTicker(watchlist, query) ?? t('loader.predict.headline');
  }, [phase, pred, watchlist, query, t]);

  const loaderSteps = useMemo(() => [1, 2, 3, 4].map((n) => t(`loader.predict.step${n}`)), [t]);
  const loaderLogs = useMemo(
    () => [1, 2, 3, 4, 5, 6, 7, 8].map((n) => t(`loader.predict.log${n}`)),
    [t],
  );

  // Up to three levels each; older payloads only carry the single near/long.
  const nearSupport = supportList(pred?.support?.nearLevels, pred?.support?.near);
  const longSupport = supportList(pred?.support?.longLevels, pred?.support?.long);

  // Chrome re-renders instantly via t(), but the narrative (entry note, rationales,
  // drivers, disclaimer) is written server-side — re-ask so it catches up too.
  const fetchedLang = useRef(language);
  useEffect(() => {
    if (fetchedLang.current === language) return;
    fetchedLang.current = language;
    if (lastQuery.current) run(lastQuery.current, { silent: true });
  }, [language, run]);

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <ScreenHeader kicker={t('predict.kicker')} title={t('predict.title')} />

      <View style={styles.inputRow}>
        <TextInput
          value={query}
          onChangeText={setQuery}
          placeholder={t('predict.placeholder')}
          placeholderTextColor={colors.faint}
          autoCapitalize="characters"
          autoCorrect={false}
          onSubmitEditing={() => run()}
          style={[styles.input, { color: colors.text, backgroundColor: colors.surface, borderColor: colors.dividerStrong }]}
        />
        <Pressable
          onPress={() => run()}
          disabled={loading || !query.trim()}
          style={[styles.go, { backgroundColor: colors.accent, opacity: loading || !query.trim() ? 0.4 : 1 }]}
        >
          {loading ? (
            <ActivityIndicator size="small" color={colors.onAccent} />
          ) : (
            <Text style={[styles.goText, { color: colors.onAccent }]}>{t('predict.go')}</Text>
          )}
        </Pressable>
      </View>

      <View style={styles.picker}>
        <WatchlistPicker
          selected={query}
          onPick={(tk) => {
            // Tapping a ticker you already track should just go — filling the
            // box and making you press Predict again is a pointless second step.
            setQuery(tk);
            run(tk);
          }}
        />
      </View>

      {error ? (
        <View style={styles.center}>
          <Feather name="alert-triangle" size={30} color={colors.accent} />
          <Text style={[styles.centerBody, { color: colors.muted }]}>{error}</Text>
        </View>
      ) : !pred ? (
        <View style={styles.center}>
          <Feather name="compass" size={34} color={colors.muted} />
          <Text style={[styles.centerTitle, { color: colors.text }]}>{t('predict.emptyTitle')}</Text>
          <Text style={[styles.centerBody, { color: colors.muted }]}>{t('predict.emptyBody')}</Text>
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
            const lean = overallLean(pred.horizons);
            const m = leanMeta(colors, lean);
            return (
              <View style={[styles.headline, { backgroundColor: m.bg }]}>
                <Text style={[styles.headlineKicker, { color: m.fg }]}>{t('predict.headline')}</Text>
                <View style={styles.headlineRow}>
                  <Text style={[styles.headlineGlyph, { color: m.fg }]}>{m.glyph}</Text>
                  <Text style={[styles.headlineLean, { color: m.fg }]}>{t(`predict.lean.${lean}`)}</Text>
                </View>
              </View>
            );
          })()}

          {/* entry advice */}
          {pred.entry ? (
            <View style={[styles.entry, { borderColor: colors.divider }]}>
              <View style={styles.entryTop}>
                <Text style={[styles.entryLabel, { color: colors.muted }]}>{t('predict.entryQ')}</Text>
                <View style={[styles.entryBadge, { backgroundColor: entryColor(colors, pred.entry.assessment) + '22' }]}>
                  <Text style={[styles.entryBadgeText, { color: entryColor(colors, pred.entry.assessment) }]}>
                    {t(`predict.entry.${pred.entry.assessment}`)}
                  </Text>
                </View>
              </View>
              <Text style={[styles.entryNote, { color: colors.text }]}>{pred.entry.note}</Text>
              {nearSupport.length || longSupport.length ? (
                <View style={styles.supportBlock}>
                  <Text style={[styles.supportLabel, { color: colors.muted }]}>{t('predict.support')}</Text>
                  <SupportRow label={t('predict.supportNear')} levels={nearSupport} />
                  <SupportRow label={t('predict.supportLong')} levels={longSupport} />
                </View>
              ) : null}
            </View>
          ) : null}

          {/* charts with range selector */}
          {pred.series?.closes?.length ? (
            <View style={styles.chartBlock}>
              <View style={styles.chartHead}>
                <Text style={[styles.chartLabel, { color: colors.muted }]}>
                  {t('predict.price')} {pred.price ? `· $${pred.price}` : ''}
                </Text>
                <Segmented options={['1W', '1M', '3M', '6M']} value={range} onChange={setRange} />
              </View>
              <PriceChart
                values={pred.series.closes.slice(-RANGES[range])}
                dates={pred.series.dates?.slice(-RANGES[range])}
                height={128}
              />
              <Text style={[styles.chartHint, { color: colors.faint }]}>{t('predict.chartHint')}</Text>
              <Text style={[styles.chartLabel, { color: colors.muted, marginTop: 10 }]}>{t('predict.volume')}</Text>
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
                  {t('predict.trend')} {pred.trend.toUpperCase()}
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
                    <Text style={[styles.leanText, { color: m.fg }]}>{t(`predict.lean.${h.lean}`)}</Text>
                  </View>
                  <Text style={[styles.conf, { color: colors.faint }]}>{t(`predict.conf.${h.confidence}`)}</Text>
                  <Text style={[styles.rationale, { color: colors.muted }]}>{h.rationale}</Text>
                </View>
              );
            })}
          </View>

          {/* drivers */}
          {pred.drivers?.length ? (
            <>
              <Text style={[styles.sectionLabel, { color: colors.muted }]}>{t('predict.drivers')}</Text>
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
                {t('predict.howReads')} · {pred.strategy.name}
              </Text>
            </Pressable>
          ) : null}
          <Text style={[styles.disclaimer, { color: colors.faint }]}>{pred.disclaimer}</Text>
        </ScrollView>
      )}

      <HackerLoader
        phase={phase}
        onDone={() => setPhase('idle')}
        kicker={t('loader.predict.kicker')}
        scrambleWord={t('loader.predict.scramble')}
        headline={loaderHeadline}
        steps={loaderSteps}
        logLines={loaderLogs}
        onCancel={() => {
          abort.current?.abort();
          abort.current = null;
          setPhase('idle');
        }}
      />

      {/* strategy modal */}
      <Modal visible={modal} transparent animationType="fade" onRequestClose={() => setModal(false)}>
        <Pressable style={styles.backdrop} onPress={() => setModal(false)}>
          <Pressable style={[styles.sheet, { backgroundColor: colors.elevated }]} onPress={() => {}}>
            <Text style={[styles.sheetKicker, { color: colors.accent }]}>{t('predict.strategy')}</Text>
            <Text style={[styles.sheetTitle, { color: colors.text }]}>{pred?.strategy?.name}</Text>
            <Text style={[styles.sheetBody, { color: colors.muted }]}>{pred?.strategy?.body}</Text>
            <Text style={[styles.sheetNote, { color: colors.faint }]}>{t('predict.strategyNote')}</Text>
            <Pressable onPress={() => setModal(false)} style={[styles.sheetBtn, { backgroundColor: colors.accent }]}>
              <Text style={[styles.sheetBtnText, { color: colors.onAccent }]}>{t('common.gotIt')}</Text>
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
  inputRow: { flexDirection: 'row', gap: 8, paddingHorizontal: 16, paddingTop: 12, paddingBottom: 8 },
  picker: { paddingLeft: 16, paddingBottom: 10 },
  input: { flex: 1, borderWidth: 1, paddingHorizontal: 12, paddingVertical: 10, fontSize: 14, fontWeight: '600' },
  go: { paddingHorizontal: 18, alignItems: 'center', justifyContent: 'center', minWidth: 84 },
  goText: { fontSize: 14, fontWeight: '800' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12, padding: 32 },
  centerTitle: { fontSize: 18, fontWeight: '900' },
  centerBody: { fontSize: 13, textAlign: 'center', lineHeight: 19, maxWidth: 290 },
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
  entryTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  entryLabel: { flex: 1, fontSize: 10, fontWeight: '900', letterSpacing: 1 },
  entryBadge: { paddingHorizontal: 10, paddingVertical: 4 },
  entryBadgeText: { fontSize: 11, fontWeight: '900', letterSpacing: 0.5 },
  entryNote: { fontSize: 14, lineHeight: 21, fontWeight: '600' },
  supportBlock: { gap: 6, marginTop: 2 },
  supportRow: { flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' },
  supportLabel: { fontSize: 9, fontWeight: '900', letterSpacing: 0.8 },
  supportChip: { flexDirection: 'row', alignItems: 'center', gap: 5, borderWidth: 1, paddingHorizontal: 8, paddingVertical: 3 },
  supportKind: { fontSize: 9, fontWeight: '800', letterSpacing: 0.3, width: 52 },
  supportVal: { fontSize: 11, fontWeight: '800', fontVariant: ['tabular-nums'] },
  chartBlock: { marginBottom: 16 },
  chartHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, gap: 8, flexWrap: 'wrap' },
  chartLabel: { fontSize: 10, fontWeight: '900', letterSpacing: 1 },
  chartHint: { fontSize: 9, fontWeight: '700', marginTop: 4, textAlign: 'center' },
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
