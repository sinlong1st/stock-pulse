/**
 * Full-screen terminal loader for the slow AI calls (Report, Predict).
 *
 * Recreates design/mobile-hacker-loading-screen variant 1A ("blackout terminal")
 * in dark mode and 1B ("paper terminal") in light mode — same layout, animations
 * and rhythm, two palettes. The app accent (#6495ED) drives both.
 *
 * Everything animates from timers; no assets and no native modules, so it ships
 * over the air. The percentage is an easing estimate, not real progress — the
 * backend gives us no progress events — so it deliberately never reaches 100%
 * until the request actually returns.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Animated,
  Easing,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useI18n } from '../i18n/LanguageContext';
import { useTheme } from '../theme/ThemeContext';

const SCRAMBLE_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#%&/<>*+=';
const HEX = '0123456789ABCDEF';
const TICK_MS = 110; // the prototype's cadence
const HEX_ROWS = 7;
const LOG_ROWS = 6;
const MAX_FAKE_PCT = 96; // the last 4% belong to the real response

const rnd = <T,>(a: T[]): T => a[Math.floor(Math.random() * a.length)];

/** 1A blackout vs 1B paper — the two palettes from the prototype. */
function palette(dark: boolean) {
  return dark
    ? {
        bg: '#111010',
        text: '#e6e2df',
        dim: '#8d8784',
        faint: '#5f5a58',
        accent: '#6495ED', // the app's main blue
        accentSoft: '#a9c6f5',
        onAccent: '#0f1b2e',
        rule: 'rgba(255,255,255,0.18)',
        ruleSoft: 'rgba(255,255,255,0.12)',
        trackBg: 'rgba(255,255,255,0.10)',
        barGap: '#111010',
        redactBg: '#3a3634',
        scanline: 'rgba(255,255,255,0.05)',
        beam: 'rgba(100,149,237,0.20)',
      }
    : {
        bg: '#f3f2f2',
        text: '#201e1d',
        dim: '#605d5d',
        faint: '#9b9797',
        accent: '#6495ED',
        accentSoft: '#2f5aa8',
        onAccent: '#ffffff',
        rule: '#201e1d',
        ruleSoft: '#c9c6c5',
        trackBg: '#e0dedd',
        barGap: '#f3f2f2',
        redactBg: '#d2cfce',
        scanline: 'rgba(0,0,0,0.035)',
        beam: 'rgba(100,149,237,0.16)',
      };
}

/** How long the 100% + COMPLETE beat holds before the loader gets out of the way. */
const FINISH_RAMP_MS = 260;
const FINISH_HOLD_MS = 240;

export type LoaderPhase = 'idle' | 'running' | 'done';

export type HackerLoaderProps = {
  /**
   * `running` = estimating; `done` = the response landed, so drive the bar to
   * 100%, tick every step, then call `onDone`. Errors and cancels go straight
   * back to `idle` — they never earn the completion beat.
   */
  phase: LoaderPhase;
  onDone?: () => void;
  /** Word that scrambles into place, e.g. "GENERATING". */
  scrambleWord: string;
  /** Static second line under it, e.g. "YOUR BRIEFING". */
  headline: string;
  /** Small label above the headline, e.g. "BRIEFING · ON DEMAND". */
  kicker: string;
  /** Ordered step labels; the active one advances with the percentage. */
  steps: string[];
  /** Rotating log lines — flavour, but they describe real work. */
  logLines: string[];
  onCancel?: () => void;
};

export function HackerLoader({
  phase,
  onDone,
  scrambleWord,
  headline,
  kicker,
  steps,
  logLines,
  onCancel,
}: HackerLoaderProps) {
  const visible = phase !== 'idle';
  const finishing = phase === 'done';
  const { mode } = useTheme();
  const { t } = useI18n();
  const insets = useSafeAreaInsets();
  const { height } = useWindowDimensions();
  const c = useMemo(() => palette(mode === 'dark'), [mode]);

  const [tick, setTick] = useState(0);
  const [pct, setPct] = useState(0);
  const [logs, setLogs] = useState<{ t: string; x: string; k: number }[]>([]);
  const beam = useRef(new Animated.Value(0)).current;
  const pctRef = useRef(0);
  pctRef.current = pct;
  // Callers pass an inline arrow; keep the finish timers off its identity.
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  // Reset between runs so a second generate doesn't resume the old progress.
  useEffect(() => {
    if (!visible) {
      setTick(0);
      setPct(0);
      setLogs([]);
    }
  }, [visible]);

  useEffect(() => {
    if (!visible || finishing) return;
    const iv = setInterval(() => {
      setTick((s) => s + 1);
      // Ease out: quick at first, crawling near the end — an honest shape for
      // "we don't know how long this takes".
      setPct((p) => (p >= MAX_FAKE_PCT ? p : p + Math.max(0.15, (MAX_FAKE_PCT - p) * 0.012)));
    }, TICK_MS);
    return () => clearInterval(iv);
  }, [visible, finishing]);

  // The response landed: run the bar home to 100, hold a beat, then hand back.
  useEffect(() => {
    if (!finishing) return;
    const startedAt = Date.now();
    const from = pctRef.current;
    const ramp = setInterval(() => {
      const k = Math.min(1, (Date.now() - startedAt) / FINISH_RAMP_MS);
      setPct(from + (100 - from) * k);
      if (k >= 1) clearInterval(ramp);
    }, 16);
    const hand = setTimeout(() => onDoneRef.current?.(), FINISH_RAMP_MS + FINISH_HOLD_MS);
    return () => {
      clearInterval(ramp);
      clearTimeout(hand);
    };
    // `pct` and `onDone` are read through refs so the ramp runs exactly once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [finishing]);

  // Append a log line every ~5 ticks, keeping a fixed-height window.
  useEffect(() => {
    if (!visible || tick % 5 !== 0) return;
    const mm = String(Math.floor(tick / 60) % 60).padStart(2, '0');
    const ss = String(tick % 60).padStart(2, '0');
    setLogs((l) => [...l, { t: `${mm}:${ss}`, x: rnd(logLines), k: tick }].slice(-LOG_ROWS));
  }, [visible, tick, logLines]);

  useEffect(() => {
    if (!visible) return;
    beam.setValue(0);
    const loop = Animated.loop(
      Animated.timing(beam, {
        toValue: 1,
        duration: 4200,
        easing: Easing.linear,
        useNativeDriver: true,
      }),
    );
    loop.start();
    return () => loop.stop();
  }, [visible, beam]);

  const scrambled = useMemo(() => {
    const p = Math.min(1, (tick % 40) / 22);
    const n = Math.floor(scrambleWord.length * p);
    return scrambleWord
      .split('')
      .map((ch, i) => (i < n ? ch : rnd(SCRAMBLE_CHARS.split(''))))
      .join('');
  }, [tick, scrambleWord]);

  // Regenerated each tick — pure visual texture, like the prototype's hex dump.
  const hexRows = useMemo(() => {
    const rows: { x: string; hot: boolean }[] = [];
    for (let r = 0; r < HEX_ROWS; r++) {
      let s = '';
      for (let i = 0; i < 18; i++) {
        s += rnd((Math.random() < 0.5 ? HEX : SCRAMBLE_CHARS).split('')) + (i % 2 ? ' ' : '');
      }
      rows.push({ x: s, hot: r === tick % HEX_ROWS });
    }
    return rows;
  }, [tick]);

  // On finish every step reads as done — activeStep past the end.
  const activeStep = finishing
    ? steps.length
    : Math.min(steps.length - 1, Math.floor((pct / MAX_FAKE_PCT) * steps.length));
  const blinkOn = tick % 9 < 5;
  const elapsed = (tick * TICK_MS) / 1000;
  const stamp = `${String(Math.floor(elapsed / 60)).padStart(2, '0')}:${String(
    Math.floor(elapsed % 60),
  ).padStart(2, '0')}`;

  if (!visible) return null;

  return (
    <Modal visible transparent={false} animationType="fade" onRequestClose={onCancel}>
      <View style={[styles.root, { backgroundColor: c.bg, paddingTop: insets.top }]}>
        {/* CRT scanlines */}
        <View pointerEvents="none" style={[StyleSheet.absoluteFill, styles.overlay]}>
          {Array.from({ length: Math.ceil(height / 3) }).map((_, i) => (
            <View key={i} style={{ height: 1, marginBottom: 2, backgroundColor: c.scanline }} />
          ))}
        </View>

        {/* sweeping scan beam */}
        <Animated.View
          pointerEvents="none"
          style={[
            styles.beam,
            {
              backgroundColor: c.beam,
              transform: [
                {
                  translateY: beam.interpolate({
                    inputRange: [0, 1],
                    outputRange: [-140, height],
                  }),
                },
              ],
            },
          ]}
        />

        {/* channel header */}
        <View style={[styles.channel, { borderBottomColor: c.accent }]}>
          <Text style={[styles.channelText, { color: c.dim }]}>{t('loader.channel')}</Text>
          <Text style={[styles.channelText, { color: c.accent, opacity: blinkOn ? 1 : 0.25 }]}>
            {t('loader.active')}
          </Text>
        </View>

        <View style={styles.body}>
          <Text style={[styles.kicker, { color: c.dim }]}>{kicker}</Text>
          <Text style={[styles.scramble, { color: c.accent }]} numberOfLines={1}>
            {scrambled}
          </Text>
          <Text style={[styles.headline, { color: c.text }]} numberOfLines={2}>
            {headline}
          </Text>

          {/* data panel */}
          <View style={[styles.panel, { borderColor: c.accent }]}>
            <View style={[styles.panelHead, { backgroundColor: c.accent }]}>
              <Text style={[styles.panelHeadText, { color: c.onAccent }]}>{t('loader.stream')}</Text>
              <Text
                style={[styles.panelHeadText, { color: c.onAccent, opacity: blinkOn ? 1 : 0.2 }]}
              >
                {t('loader.rec')}
              </Text>
            </View>

            <View style={styles.steps}>
              {steps.map((label, i) => {
                const done = i < activeStep;
                const on = i === activeStep;
                return (
                  <View key={label} style={[styles.stepRow, { borderBottomColor: c.ruleSoft }]}>
                    <Text
                      style={[styles.stepMark, { color: on ? c.accent : done ? c.dim : c.faint }]}
                    >
                      {done ? '✓' : on ? '▸' : '·'}
                    </Text>
                    <Text
                      style={[
                        styles.stepLabel,
                        {
                          color: on ? c.accentSoft : done ? c.dim : c.faint,
                          fontWeight: on ? '800' : '600',
                        },
                      ]}
                      numberOfLines={1}
                    >
                      {label}
                    </Text>
                  </View>
                );
              })}
            </View>

            <View style={[styles.hexWrap, { borderTopColor: c.ruleSoft }]}>
              {hexRows.map((r, i) => (
                <Text
                  key={i}
                  numberOfLines={1}
                  style={[styles.hex, { color: r.hot ? c.accent : c.faint }]}
                >
                  {r.x}
                </Text>
              ))}
            </View>
          </View>

          {/* log feed */}
          <View style={styles.logs}>
            {logs.map((l, i) => (
              <View key={l.k} style={styles.logRow}>
                <Text style={[styles.logTime, { color: c.faint }]}>{l.t}</Text>
                <Text
                  numberOfLines={1}
                  style={[styles.logText, { color: i === logs.length - 1 ? c.accentSoft : c.dim }]}
                >
                  {l.x}
                </Text>
              </View>
            ))}
          </View>
        </View>

        {/* progress footer */}
        <View
          style={[
            styles.footer,
            { borderTopColor: c.rule, backgroundColor: c.bg, paddingBottom: insets.bottom + 20 },
          ]}
        >
          <View style={styles.footerTop}>
            <Text style={[styles.footerLabel, { color: finishing ? c.accent : c.dim }]}>
              {finishing ? t('loader.complete') : `${t('loader.working')} · ${stamp}`}
            </Text>
            <Text style={[styles.pct, { color: c.accent }]}>
              {String(Math.floor(pct)).padStart(2, '0')}%
            </Text>
          </View>

          <View style={[styles.track, { backgroundColor: c.trackBg }]}>
            <View style={{ height: '100%', width: `${pct}%`, backgroundColor: c.accent }} />
            {/* segmented overlay — the prototype's ticked progress bar */}
            <View style={StyleSheet.absoluteFill} pointerEvents="none">
              <View style={styles.segRow}>
                {Array.from({ length: 40 }).map((_, i) => (
                  <View key={i} style={{ width: 3, backgroundColor: c.barGap, height: '100%' }} />
                ))}
              </View>
            </View>
          </View>

          <Text style={[styles.doNotClose, { color: c.faint }]}>{t('loader.doNotClose')}</Text>

          {/* Nothing left to abort once the response is in. */}
          {onCancel && !finishing ? (
            <Pressable
              onPress={onCancel}
              style={[styles.abort, { borderColor: c.accent }]}
              hitSlop={6}
            >
              <Text style={[styles.abortText, { color: c.accent }]}>{t('loader.abort')}</Text>
            </Pressable>
          ) : null}
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  overlay: { zIndex: 6 },
  beam: { position: 'absolute', left: 0, right: 0, height: 140, zIndex: 5 },
  channel: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: 20,
    paddingTop: 10,
    paddingBottom: 10,
    borderBottomWidth: 2,
  },
  channelText: { fontSize: 10, fontWeight: '800', letterSpacing: 1.6 },
  body: { flex: 1, paddingHorizontal: 20, paddingTop: 22 },
  kicker: { fontSize: 10, fontWeight: '800', letterSpacing: 1.8, marginBottom: 10 },
  // Vietnamese uppercase stacks two marks (Ả, Ằ, Ẩ), so the line box needs
  // ~1.3x headroom — a tighter lineHeight clips the tone mark off the top.
  scramble: { fontSize: 34, fontWeight: '900', letterSpacing: -0.6, lineHeight: 44 },
  headline: { fontSize: 34, fontWeight: '900', letterSpacing: -0.6, lineHeight: 44 },
  panel: { borderWidth: 2, marginTop: 18 },
  panelHead: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  panelHeadText: { fontSize: 9, fontWeight: '900', letterSpacing: 1.6 },
  steps: { paddingHorizontal: 12, paddingTop: 6 },
  stepRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 7, borderBottomWidth: 1 },
  stepMark: { width: 12, fontSize: 12, fontWeight: '900' },
  stepLabel: { flex: 1, fontSize: 12.5 },
  hexWrap: { borderTopWidth: 1, paddingHorizontal: 12, paddingVertical: 8 },
  hex: { fontSize: 10, lineHeight: 15, letterSpacing: 1, fontVariant: ['tabular-nums'] },
  logs: { marginTop: 14, gap: 2 },
  logRow: { flexDirection: 'row', gap: 10 },
  logTime: { width: 42, fontSize: 10.5, fontVariant: ['tabular-nums'] },
  logText: { flex: 1, fontSize: 10.5 },
  footer: { borderTopWidth: 2, paddingHorizontal: 20, paddingTop: 14, zIndex: 7 },
  footerTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'baseline',
    marginBottom: 8,
  },
  footerLabel: { fontSize: 10, fontWeight: '700', letterSpacing: 1.4, textTransform: 'uppercase' },
  pct: { fontSize: 22, fontWeight: '900', fontVariant: ['tabular-nums'] },
  track: { height: 16, overflow: 'hidden' },
  segRow: { flexDirection: 'row', justifyContent: 'space-between', height: '100%' },
  doNotClose: { fontSize: 9.5, fontWeight: '700', letterSpacing: 1.2, marginTop: 9 },
  abort: { borderWidth: 2, height: 48, justifyContent: 'center', paddingHorizontal: 14, marginTop: 14 },
  abortText: { fontSize: 13, fontWeight: '800', letterSpacing: 1.6 },
});
