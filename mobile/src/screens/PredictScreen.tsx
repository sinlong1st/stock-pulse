import { Feather } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
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

import { NextEarningsChip } from '../components/Earnings';
import {
  ConfidenceBasis,
  RiskReward,
  RuleOverride,
  SecondOpinion,
  WhyThisCall,
} from '../components/EntryEvidence';
import { ExitAdviceView } from '../components/ExitAdvice';
import { HackerLoader, LoaderPhase } from '../components/HackerLoader';
import { MiniBars } from '../components/MiniBars';
import { PriceChart } from '../components/PriceChart';
import { ScreenHeader } from '../components/ScreenHeader';
import { SavedPositions } from '../components/SavedPositions';
import { Segmented } from '../components/Segmented';
import { WatchlistPicker } from '../components/WatchlistPicker';
import {
  AnalysisMode,
  ExitAdvice,
  EXIT_STAGES,
  fetchMode,
  fetchPositions,
  Lean,
  ModeInfo,
  Prediction,
  PredictionHorizon,
  PREDICT_STAGES,
  SavedPosition,
  saveMode,
  savePosition,
  removePosition,
  streamExitAdvice,
  streamPrediction,
  StreamHandle,
} from '../data/api';
import { onActiveStrategyChange } from '../data/activeStrategy';
import { guessTicker, useWatchlist } from '../data/useWatchlist';
import { useI18n } from '../i18n/LanguageContext';
import { RootStackParamList } from '../navigation/types';
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
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const insets = useSafeAreaInsets();
  const [query, setQuery] = useState('');
  const [pred, setPred] = useState<Prediction | null>(null);
  const [phase, setPhase] = useState<LoaderPhase>('idle');
  const [error, setError] = useState<string | null>(null);
  const loading = phase !== 'idle';
  const [modal, setModal] = useState(false);
  const [range, setRange] = useState('3M');
  // Which model(s) to ask. Loaded from the server so the choice survives a
  // reinstall and stays in step with which keys are actually configured.
  const [modeInfo, setModeInfo] = useState<ModeInfo | null>(null);
  const mode = modeInfo?.mode;
  // Last query that produced a read, so a language switch can re-ask the backend.
  const lastQuery = useRef<string | null>(null);

  const stream = useRef<StreamHandle | null>(null);
  const [stageIndex, setStageIndex] = useState<number | null>(null);

  // Now that the form scrolls with the page, a finished analysis would leave
  // you looking at the inputs with the verdict below the fold. Set when a
  // result lands; consumed by the results block's onLayout, because the block
  // has to exist and be measured before there is anywhere to scroll to.
  const scroller = useRef<ScrollView>(null);
  const wantScroll = useRef(false);
  const revealResults = (y: number) => {
    if (!wantScroll.current) return;
    wantScroll.current = false;
    scroller.current?.scrollTo({ y: Math.max(0, y - 8), animated: true });
  };

  // Which question is being asked. Two very different questions about the same
  // ticker, so the ticker box is shared and everything below it swaps.
  const [tab, setTab] = useState<'buy' | 'own'>('buy');
  const [shares, setShares] = useState('');
  const [avgCost, setAvgCost] = useState('');
  const [exit, setExit] = useState<ExitAdvice | null>(null);
  const exitStream = useRef<StreamHandle | null>(null);
  // Set once the user has actually tried to run, so empty fields don't turn red
  // the instant the tab opens — that reads as being told off for nothing.
  const [attempted, setAttempted] = useState(false);
  const [positions, setPositions] = useState<SavedPosition[]>([]);
  const [activePosition, setActivePosition] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Best-effort: a backend without the feature (or without the flag) just
  // leaves the list empty, and typing a position by hand still works.
  const loadPositions = useCallback(() => {
    fetchPositions()
      .then((info) => setPositions(info.positions))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (tab === 'own') loadPositions();
  }, [tab, loadPositions]);

  // A field is wrong if it holds something that isn't a positive number, or if
  // it's empty and the user has already pressed the button.
  const sharesNum = Number(shares);
  const costNum = Number(avgCost);
  const sharesBad = shares.trim() ? !(sharesNum > 0) : attempted;
  const costBad = avgCost.trim() ? !(costNum > 0) : attempted;
  const ownReady = !!query.trim() && sharesNum > 0 && costNum > 0;

  const runExit = useCallback(
    /** `silent` refreshes in the background, for the language switch — the user
     *  didn't ask to wait for that one.
     *
     *  `tickerOverride` exists for the same reason `modeOverride` does on the
     *  buy path: tapping a watchlist chip calls `setQuery` and runs in the same
     *  tick, and React hasn't applied the state yet — reading `query` here
     *  would analyse the *previously* selected ticker. */
    ({
      silent = false,
      tickerOverride,
      positionId,
    }: { silent?: boolean; tickerOverride?: string; positionId?: string } = {}) => {
      const ticker = (tickerOverride ?? query).trim();
      const n = Number(shares);
      const cost = Number(avgCost);
      // Nothing leaves the device until all three are real. An incomplete
      // position can't be analysed anyway, and a round trip that was always
      // going to fail still costs a model call. A saved position is already
      // validated, so it skips this.
      if (!positionId && (!ticker || !(n > 0) || !(cost > 0))) {
        setAttempted(true);
        return;
      }
      setAttempted(false);
      exitStream.current?.cancel();
      setError(null);
      if (!silent) {
        setPhase('running');
        setStageIndex(null);
      }
      exitStream.current = streamExitAdvice(
        // By id when it's a saved holding: the server then also applies the
        // stop and target stored with it, which the typed fields don't carry.
        positionId ? { positionId } : { ticker, shares: n, averageCost: cost },
        (stage) => !silent && setStageIndex(EXIT_STAGES.indexOf(stage)),
        (result) => {
          exitStream.current = null;
          if (result.ok) {
            setExit(result);
            lastQuery.current = ticker;
            if (!silent) {
              wantScroll.current = true;
              setPhase('done');
            }
          } else {
            setExit(null);
            setError(result.reason ?? t('predict.genErr'));
            if (!silent) setPhase('idle');
          }
        },
        (e) => {
          exitStream.current = null;
          setError(e.message || t('predict.genErr'));
          if (!silent) setPhase('idle');
        },
      );
    },
    [query, shares, avgCost, t],
  );

  const run = useCallback(
    /** `silent` refreshes in the background — no takeover loader. Used by the
     *  language switch, which the user didn't ask to wait for.
     *
     *  `modeOverride` exists because React state hasn't applied yet when the
     *  picker re-runs — reading `mode` here would use the model you just
     *  switched *away* from. */
    (
      q?: string,
      { silent = false, modeOverride }: { silent?: boolean; modeOverride?: AnalysisMode } = {},
    ) => {
      const term = (q ?? query).trim();
      if (!term) return;
      stream.current?.cancel(); // a new ticker replaces the in-flight run
      if (!silent) {
        setPhase('running');
        setStageIndex(null);
      }
      setError(null);
      stream.current = streamPrediction(
        term,
        (stage) => !silent && setStageIndex(PREDICT_STAGES.indexOf(stage)),
        (p) => {
          stream.current = null;
          if (p.ok) {
            setPred(p);
            lastQuery.current = term;
            // Only a visible run gets the 100% beat; a silent refresh never showed.
            if (!silent) {
              wantScroll.current = true;
              setPhase('done');
            }
          } else {
            setPred(null);
            setError(p.reason ?? t('predict.genErr'));
            if (!silent) setPhase('idle');
          }
        },
        (e) => {
          stream.current = null;
          setError(e.message || t('predict.genErr'));
          if (!silent) setPhase('idle'); // no fanfare on failure
        },
        {
          mode: modeOverride ?? mode,
          // Arrives ~12s after the main read in `both` mode, so the card fills
          // itself in rather than holding the whole screen back.
          onSecond: ({ secondOpinion }) =>
            setPred((prev) => (prev ? { ...prev, secondOpinion } : prev)),
        },
      );
    },
    [query, t, mode],
  );

  const cancel = () => {
    stream.current?.cancel();
    stream.current = null;
    exitStream.current?.cancel();
    exitStream.current = null;
    setPhase('idle');
  };

  /** Whichever question the current tab asks. */
  const go = useCallback(() => {
    if (tab === 'buy') return run();
    // A typed position is a different position from the saved one that was on
    // screen, so stop showing that row as selected.
    setActivePosition(null);
    runExit();
  }, [tab, runExit, run]);

  const pickPosition = useCallback(
    (position: SavedPosition) => {
      // Mirror the row into the fields so the screen shows what's being asked
      // about, and an edit-then-Analyse starts from the saved numbers.
      setQuery(position.ticker);
      setShares(String(position.shares));
      setAvgCost(String(position.averageCost));
      setActivePosition(position.id);
      runExit({ positionId: position.id });
    },
    [runExit],
  );

  const saveCurrent = useCallback(() => {
    setSaving(true);
    savePosition({ ticker: query.trim(), shares: sharesNum, averageCost: costNum })
      .then((info) => {
        setPositions(info.positions);
        // Select whichever row is this ticker at this cost, so it reads as saved.
        const match = info.positions.find(
          (p) => p.ticker === query.trim().toUpperCase() && p.averageCost === costNum,
        );
        setActivePosition(match?.id ?? null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : t('exit.saveErr')))
      .finally(() => setSaving(false));
  }, [query, sharesNum, costNum, t]);

  const removeSaved = useCallback(
    (position: SavedPosition) => {
      removePosition(position.id)
        .then((info) => setPositions(info.positions))
        .catch(() => {});
      if (activePosition === position.id) setActivePosition(null);
    },
    [activePosition],
  );

  /** Already in the list, so offering to save it again would be noise. */
  const alreadySaved = positions.some(
    (p) => p.ticker === query.trim().toUpperCase() && p.averageCost === costNum,
  );

  // Chrome re-renders instantly via t(), but the exit thesis and reasons are
  // written server-side in the user's language — re-ask so they catch up too.
  const fetchedExitLang = useRef(language);
  useEffect(() => {
    if (fetchedExitLang.current === language) return;
    fetchedExitLang.current = language;
    if (tab === 'own' && exit) runExit({ silent: true });
  }, [language, tab, exit, runExit]);

  // Best-effort: if this fails the picker just stays hidden and predictions run
  // on the server's default, which is exactly the old behaviour.
  useEffect(() => {
    let alive = true;
    fetchMode()
      .then((info) => alive && setModeInfo(info))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  const pickMode = useCallback(
    (next: AnalysisMode) => {
      if (next === mode) return;
      setModeInfo((prev) => (prev ? { ...prev, mode: next } : prev)); // optimistic
      saveMode(next)
        .then((info) => setModeInfo(info))
        .catch(() => setModeInfo((prev) => (prev ? { ...prev, mode: mode! } : prev)));
      // Re-ask with the new model rather than leaving a stale read on screen
      // under a picker that now says something else.
      if (lastQuery.current) run(lastQuery.current, { modeOverride: next });
    },
    [mode, run],
  );

  // See ReportScreen: guess from the watchlist while in flight, then show the
  // ticker the server actually resolved rather than echoing the user's typo.
  const watchlist = useWatchlist();
  const loaderHeadline = useMemo(() => {
    const resolved = phase === 'done' ? (tab === 'own' ? exit?.ticker : pred?.ticker) : null;
    return (
      resolved ??
      guessTicker(watchlist, query) ??
      t(tab === 'own' ? 'loader.exit.headline' : 'loader.predict.headline')
    );
  }, [phase, pred, exit, tab, watchlist, query, t]);

  const loaderSteps = useMemo(
    () =>
      tab === 'own'
        ? [1, 2, 3, 4, 5].map((n) => t(`loader.exit.step${n}`))
        : [1, 2, 3, 4].map((n) => t(`loader.predict.step${n}`)),
    [t, tab],
  );
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

  // Switching strategy elsewhere leaves this read (and its modal) attributed to
  // the old lens — re-ask so what's on screen matches what's now active.
  useEffect(
    () =>
      onActiveStrategyChange(() => {
        if (lastQuery.current) run(lastQuery.current, { silent: true });
      }),
    [run],
  );

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <ScreenHeader kicker={t('predict.kicker')} title={t('predict.title')} />

      {/* One scroll for the whole screen — controls included.
          They used to be pinned above a separate results ScrollView, which was
          fine for Predict's single input row but not once the sell tab added
          share count, average cost, saved positions and the picker: the form
          took ~40% of the phone permanently and the answer read through a slot
          underneath it. Scrolling the form away is what you want the moment a
          result exists, and scrolling back up is how you change it. */}
      <ScrollView
        ref={scroller}
        contentContainerStyle={{ flexGrow: 1, paddingBottom: insets.bottom + 28 }}
        showsVerticalScrollIndicator={false}
        // Otherwise the first tap on Analyse only dismisses the keyboard.
        keyboardShouldPersistTaps="handled"
      >
      {/* Two questions about the same stock: should I buy it, and — the other
          half — I already own it, now what? Sharing the ticker box is the point;
          switching tabs keeps whatever you typed. */}
      <View style={styles.tabRow}>
        <Segmented
          options={['buy', 'own']}
          value={tab}
          onChange={(v) => {
            setTab(v as 'buy' | 'own');
            setError(null);
            setAttempted(false); // a fresh tab shouldn't open already scolding
          }}
          renderLabel={(v) => t(`exit.tab.${v}`)}
        />
      </View>

      <View style={styles.inputRow}>
        <TextInput
          value={query}
          onChangeText={setQuery}
          placeholder={t('predict.placeholder')}
          placeholderTextColor={colors.faint}
          autoCapitalize="characters"
          autoCorrect={false}
          onSubmitEditing={go}
          style={[styles.input, { color: colors.text, backgroundColor: colors.surface, borderColor: colors.dividerStrong }]}
        />
        <Pressable
          onPress={go}
          disabled={loading || !query.trim()}
          style={[
            styles.go,
            {
              backgroundColor: colors.accent,
              // Dimmed while the position is incomplete, but still pressable —
              // pressing is how you find out which field is missing.
              opacity:
                loading || !query.trim() || (tab === 'own' && !ownReady) ? 0.4 : 1,
            },
          ]}
        >
          {loading ? (
            <ActivityIndicator size="small" color={colors.onAccent} />
          ) : (
            <Text style={[styles.goText, { color: colors.onAccent }]}>
              {t(tab === 'own' ? 'exit.go' : 'predict.go')}
            </Text>
          )}
        </Pressable>
      </View>

      {/* What you hold. Only these two are required — everything else the
          advisor needs comes from real market data. */}
      {tab === 'own' ? (
        <View style={styles.ownRow}>
          <View style={styles.ownField}>
            <Text style={[styles.ownLabel, { color: colors.faint }]}>{t('exit.shares')}</Text>
            <TextInput
              value={shares}
              onChangeText={setShares}
              placeholder={t('exit.sharesHint')}
              placeholderTextColor={colors.faint}
              keyboardType="decimal-pad"
              onSubmitEditing={go}
              style={[
                styles.ownInput,
                {
                  color: colors.text,
                  backgroundColor: colors.surface,
                  borderColor: sharesBad ? colors.bear : colors.dividerStrong,
                },
              ]}
            />
            {sharesBad ? (
              <Text style={[styles.fieldErr, { color: colors.bear }]}>{t('exit.needShares')}</Text>
            ) : null}
          </View>
          <View style={styles.ownField}>
            <Text style={[styles.ownLabel, { color: colors.faint }]}>{t('exit.avgCost')}</Text>
            <TextInput
              value={avgCost}
              onChangeText={setAvgCost}
              placeholder={t('exit.costHint')}
              placeholderTextColor={colors.faint}
              keyboardType="decimal-pad"
              onSubmitEditing={go}
              style={[
                styles.ownInput,
                {
                  color: colors.text,
                  backgroundColor: colors.surface,
                  borderColor: costBad ? colors.bear : colors.dividerStrong,
                },
              ]}
            />
            {costBad ? (
              <Text style={[styles.fieldErr, { color: colors.bear }]}>{t('exit.needCost')}</Text>
            ) : null}
          </View>
        </View>
      ) : null}

      {/* Offered only once the position is real and isn't already stored —
          otherwise it's a button that either fails or does nothing. */}
      {tab === 'own' && ownReady && !alreadySaved ? (
        <Pressable
          onPress={saveCurrent}
          disabled={saving}
          style={[styles.saveRow, { borderColor: colors.dividerStrong, opacity: saving ? 0.5 : 1 }]}
        >
          <Feather name="bookmark" size={13} color={colors.accentInk} />
          <Text style={[styles.saveText, { color: colors.accentInk }]}>{t('exit.save')}</Text>
        </Pressable>
      ) : null}

      {tab === 'own' ? (
        <SavedPositions
          positions={positions}
          activeId={activePosition}
          onPick={pickPosition}
          onRemove={removeSaved}
        />
      ) : null}

      <View style={styles.picker}>
        <WatchlistPicker
          selected={query}
          onPick={(tk) => {
            setQuery(tk);
            // Tapping a ticker you already track should just go — filling the
            // box and making you press Predict again is a pointless second step.
            //
            // In the SELL tab it can't: a position needs shares and average
            // cost too. Tapping used to call `run` regardless, which ran a
            // *prediction* from the sell tab and skipped validation entirely.
            if (tab === 'buy') run(tk);
            else if (sharesNum > 0 && costNum > 0) runExit({ tickerOverride: tk });
          }}
        />
      </View>

      {/* Model choice. Hidden unless there is a real choice to make — with one
          key configured this is a control with one option, which is just noise.

          A segmented control, not chips: the tickers above are chips, and two
          controls that look alike read as one list. This is a mode switch, so it
          borrows the same joined bar the chart range uses. */}
      {modeInfo && modeInfo.available.length > 1 && tab === 'buy' ? (
        <View style={styles.modeRow}>
          <Text style={[styles.modeLabel, { color: colors.faint }]}>{t('predict.modeLabel')}</Text>
          <View
            style={{ opacity: loading ? 0.4 : 1 }}
            pointerEvents={loading ? 'none' : 'auto'}
          >
            <Segmented
              options={modeInfo.available}
              value={mode ?? ''}
              onChange={(v) => pickMode(v as AnalysisMode)}
              renderLabel={(v) => t(`predict.mode.${v}`)}
            />
          </View>
        </View>
      ) : null}

      {error ? (
        <View style={styles.center}>
          <Feather name="alert-triangle" size={30} color={colors.accent} />
          <Text style={[styles.centerBody, { color: colors.muted }]}>{error}</Text>
        </View>
      ) : tab === 'own' ? (
        exit ? (
          <View
            style={styles.body}
            onLayout={(e) => revealResults(e.nativeEvent.layout.y)}
          >
            <ExitAdviceView data={exit} />
          </View>
        ) : (
          <View style={styles.center}>
            <Feather name="briefcase" size={34} color={colors.muted} />
            <Text style={[styles.centerTitle, { color: colors.text }]}>{t('exit.emptyTitle')}</Text>
            <Text style={[styles.centerBody, { color: colors.muted }]}>{t('exit.emptyBody')}</Text>
          </View>
        )
      ) : !pred ? (
        <View style={styles.center}>
          <Feather name="compass" size={34} color={colors.muted} />
          <Text style={[styles.centerTitle, { color: colors.text }]}>{t('predict.emptyTitle')}</Text>
          <Text style={[styles.centerBody, { color: colors.muted }]}>{t('predict.emptyBody')}</Text>
        </View>
      ) : (
        <View style={styles.body} onLayout={(e) => revealResults(e.nativeEvent.layout.y)}>
          {/* header */}
          <View style={styles.head}>
            <Text style={[styles.ticker, { color: colors.text }]}>{pred.ticker}</Text>
            <Text style={[styles.name, { color: colors.muted }]}>{pred.name}</Text>
            {pred.price ? (
              <Text style={[styles.price, { color: colors.text }]}>
                ${pred.price} <Text style={{ color: colors.faint, fontSize: 10 }}>{pred.priceFresh}</Text>
              </Text>
            ) : null}
            {pred.earnings ? (
              <View style={styles.earnRow}>
                <NextEarningsChip row={pred.earnings} />
              </View>
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

              {/* An override changes the verdict above, so it goes first. */}
              {pred.rules ? <RuleOverride rules={pred.rules} /> : null}
              {pred.secondOpinion ? (
                <SecondOpinion second={pred.secondOpinion} />
              ) : pred.analysis?.second ? (
                // The second model is still running — it lands ~12s after this
                // read. Saying so beats a card that silently pops in later.
                <View style={[styles.secondPending, { borderColor: colors.divider }]}>
                  <ActivityIndicator size="small" color={colors.muted} />
                  <Text style={[styles.secondPendingText, { color: colors.muted }]}>
                    {t('second.pending', { model: pred.analysis.second })}
                  </Text>
                </View>
              ) : null}
              {/* Asked for a model we have no key for — say so rather than
                  quietly returning a different one. */}
              {pred.analysis?.downgraded ? (
                <Text style={[styles.modeNote, { color: colors.faint }]}>
                  {t('predict.mode.downgraded', {
                    asked: t(`predict.mode.${pred.analysis.requested}`),
                    used: t(`predict.mode.${pred.analysis.effective}`),
                  })}
                </Text>
              ) : null}

              {/* The working behind the call, so it can be audited rather than
                  taken on trust. Absent on older backends. */}
              {pred.evidence ? <RiskReward evidence={pred.evidence} /> : null}
              {pred.evidence ? <WhyThisCall evidence={pred.evidence} /> : null}
              {pred.confidence ? (
                <ConfidenceBasis confidence={pred.confidence} risks={pred.entry.risks} />
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
        </View>
      )}
      </ScrollView>

      <HackerLoader
        phase={phase}
        onDone={() => setPhase('idle')}
        kicker={t(tab === 'own' ? 'loader.exit.kicker' : 'loader.predict.kicker')}
        scrambleWord={t(tab === 'own' ? 'loader.exit.scramble' : 'loader.predict.scramble')}
        headline={loaderHeadline}
        steps={loaderSteps}
        stageIndex={stageIndex}
        logLines={loaderLogs}
        onCancel={cancel}
      />

      {/* strategy modal */}
      <Modal visible={modal} transparent animationType="fade" onRequestClose={() => setModal(false)}>
        <Pressable style={styles.backdrop} onPress={() => setModal(false)}>
          <Pressable style={[styles.sheet, { backgroundColor: colors.elevated }]} onPress={() => {}}>
            <Text style={[styles.sheetKicker, { color: colors.accent }]}>{t('predict.strategy')}</Text>
            <Text style={[styles.sheetTitle, { color: colors.text }]}>{pred?.strategy?.name}</Text>
            {/* A long custom strategy would push the buttons off-screen, so the
                prose scrolls inside a bounded area and the actions stay put. */}
            <ScrollView
              style={styles.sheetScroll}
              contentContainerStyle={styles.sheetScrollBody}
              showsVerticalScrollIndicator
            >
              <Text style={[styles.sheetBody, { color: colors.muted }]}>{pred?.strategy?.body}</Text>
              <Text style={[styles.sheetNote, { color: colors.faint }]}>
                {t('predict.strategyNote')}
              </Text>
            </ScrollView>
            <Pressable
              onPress={() => {
                setModal(false);
                navigation.navigate('Strategies');
              }}
              style={[styles.sheetLink, { borderColor: colors.dividerStrong }]}
            >
              <Feather name="sliders" size={13} color={colors.accentInk} />
              <Text style={[styles.sheetLinkText, { color: colors.accentInk }]}>
                {t('strat.manage')}
              </Text>
            </Pressable>
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
  tabRow: { paddingHorizontal: 16, paddingTop: 12 },
  ownRow: { flexDirection: 'row', gap: 10, paddingHorizontal: 16, paddingBottom: 10 },
  ownField: { flex: 1, gap: 4 },
  ownLabel: { fontSize: 9, fontWeight: '900', letterSpacing: 0.8 },
  // Deliberately NOT `styles.input`: that carries `flex: 1` for the ticker row,
  // and inside this column it collapses the height — which clipped the text to
  // invisibility and made the boxes look tiny. Height is stated here instead.
  ownInput: {
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 12,
    minHeight: 48,
    fontSize: 16,
    fontWeight: '700',
    fontVariant: ['tabular-nums'],
  },
  fieldErr: { fontSize: 10, fontWeight: '700', lineHeight: 14 },
  saveRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    borderWidth: 1,
    borderStyle: 'dashed',
    paddingVertical: 9,
    marginHorizontal: 16,
    marginBottom: 10,
  },
  saveText: { fontSize: 12, fontWeight: '800' },
  // Right padding matters: the ticker chips wrap, and with none the last chip in
  // a row sat flush against the screen edge while the first lined up at 16.
  picker: { paddingHorizontal: 16, paddingBottom: 10 },
  modeRow: { gap: 5, paddingHorizontal: 16, paddingBottom: 12 },
  // Same treatment as the watchlist picker's label, so the two controls read as
  // a pair of labelled groups rather than two loose rows of buttons.
  modeLabel: { fontSize: 9, fontWeight: '900', letterSpacing: 0.8 },
  modeNote: { fontSize: 10, marginTop: 8, lineHeight: 15 },
  secondPending: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderWidth: 1,
    borderStyle: 'dashed',
    padding: 10,
    marginTop: 10,
  },
  secondPendingText: { fontSize: 11, fontWeight: '600' },
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
  earnRow: { marginTop: 8 },
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
  sheet: { padding: 20, gap: 8, maxHeight: '80%' },
  sheetScroll: { flexShrink: 1 },
  sheetScrollBody: { gap: 8, paddingBottom: 2 },
  sheetKicker: { fontSize: 10, fontWeight: '900', letterSpacing: 1 },
  sheetTitle: { fontSize: 20, fontWeight: '900' },
  sheetBody: { fontSize: 13.5, lineHeight: 20 },
  sheetNote: { fontSize: 11, lineHeight: 16, marginTop: 4 },
  sheetLink: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    borderWidth: 1,
    paddingVertical: 11,
    marginTop: 10,
  },
  sheetLinkText: { fontSize: 12.5, fontWeight: '800' },
  sheetBtn: { marginTop: 8, paddingVertical: 12, alignItems: 'center' },
  sheetBtnText: { fontSize: 14, fontWeight: '800' },
});
