import { Feather } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import React, { useMemo, useRef, useState } from 'react';
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { HackerLoader } from '../components/HackerLoader';
import { ScreenHeader } from '../components/ScreenHeader';
import { Segmented } from '../components/Segmented';
import { WatchlistPicker } from '../components/WatchlistPicker';
import { fetchReport, isAborted } from '../data/api';
import { Report } from '../data/types';
import { useI18n } from '../i18n/LanguageContext';
import { RootStackParamList } from '../navigation/types';
import { useTheme } from '../theme/ThemeContext';
import { changeColor, formatChange, sentiment as sentimentOf } from '../theme/semantics';

const WHOLE = 'Whole watchlist';
const SINGLE = 'Single stock';

export function ReportScreen() {
  const { colors } = useTheme();
  const { t } = useI18n();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scope, setScope] = useState<string>(WHOLE);
  const [ticker, setTicker] = useState('');

  const abort = useRef<AbortController | null>(null);

  const generate = async () => {
    abort.current?.abort(); // a re-tap replaces the in-flight run
    const ctrl = new AbortController();
    abort.current = ctrl;
    setLoading(true);
    setError(null);
    try {
      setReport(await fetchReport(scope === SINGLE ? ticker : undefined, ctrl.signal));
    } catch (e) {
      if (isAborted(e)) return; // cancelled on purpose — leave the screen as it was
      setError(e instanceof Error ? e.message : t('report.genErr'));
    } finally {
      if (abort.current === ctrl) {
        abort.current = null;
        setLoading(false);
      }
    }
  };

  const loaderSteps = useMemo(
    () => [1, 2, 3, 4].map((n) => t(`loader.report.step${n}`)),
    [t],
  );
  const loaderLogs = useMemo(
    () => [1, 2, 3, 4, 5, 6, 7, 8].map((n) => t(`loader.report.log${n}`)),
    [t],
  );

  const canGenerate = scope === WHOLE || ticker.trim().length > 0;

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <ScreenHeader
        kicker={t('report.kicker')}
        title={t('report.title')}
        right={
          <View style={styles.headerIcons}>
            {report && !loading ? (
              <Pressable
                onPress={generate}
                hitSlop={8}
                style={[styles.regen, { borderColor: colors.accent }]}
              >
                <Feather name="refresh-cw" size={13} color={colors.accent} />
                <Text style={[styles.regenText, { color: colors.accent }]}>
                  {t('report.regenerate')}
                </Text>
              </Pressable>
            ) : null}
            <Pressable onPress={() => navigation.navigate('Evaluation')} hitSlop={10}>
              <Feather name="target" size={20} color={colors.text} />
            </Pressable>
          </View>
        }
      />

      {/* scope control */}
      <View style={styles.control}>
        <Segmented
          options={[WHOLE, SINGLE]}
          value={scope}
          onChange={setScope}
          renderLabel={(v) => t(v === WHOLE ? 'report.whole' : 'report.single')}
        />
        {scope === SINGLE && (
          <>
            <TextInput
              value={ticker}
              onChangeText={setTicker}
              placeholder={t('report.tickerPlaceholder')}
              placeholderTextColor={colors.faint}
              autoCapitalize="characters"
              autoCorrect={false}
              onSubmitEditing={() => canGenerate && generate()}
              style={[
                styles.input,
                { color: colors.text, backgroundColor: colors.surface, borderColor: colors.dividerStrong },
              ]}
            />
            <WatchlistPicker selected={ticker} onPick={setTicker} />
          </>
        )}
      </View>

      {error ? (
        <View style={styles.center}>
          <Feather name="alert-triangle" size={30} color={colors.accent} />
          <Text style={[styles.centerBody, { color: colors.muted }]}>{error}</Text>
          <GenerateButton label={t('common.tryAgain')} onPress={generate} />
        </View>
      ) : !report ? (
        <View style={styles.center}>
          <Feather name="bar-chart-2" size={34} color={colors.muted} />
          <Text style={[styles.centerTitle, { color: colors.text }]}>{t('report.emptyTitle')}</Text>
          <Text style={[styles.centerBody, { color: colors.muted }]}>
            {scope === SINGLE ? t('report.emptyBodyStock') : t('report.emptyBodyWatchlist')}
          </Text>
          <GenerateButton label={t('report.generate')} onPress={generate} disabled={!canGenerate} />
        </View>
      ) : (
        <ScrollView contentContainerStyle={styles.body} showsVerticalScrollIndicator={false}>
          {report.note ? (
            <Text style={[styles.note, { color: colors.muted }]}>{report.note}</Text>
          ) : (
            <View style={[styles.takeaway, { borderTopColor: colors.accent }]}>
              <Text style={[styles.takeawayKicker, { color: colors.accentInk }]}>{t('report.takeaway')}</Text>
              <Text style={[styles.takeawayText, { color: colors.text }]}>{report.takeaway}</Text>
            </View>
          )}

          {report.sections.map((s, i) => {
            const meta = sentimentOf(colors, s.sentiment);
            return (
              <View key={`${s.title}-${i}`} style={[styles.section, { borderBottomColor: colors.divider }]}>
                <View style={styles.sectionHead}>
                  <View style={[styles.dot, { backgroundColor: meta.fg }]} />
                  <Text style={[styles.sectionTitle, { color: colors.text }]}>{s.title}</Text>
                  <Text style={[styles.sectionSent, { color: meta.fg }]}>
                    {meta.glyph} {meta.label}
                  </Text>
                </View>
                <Text style={[styles.sectionBody, { color: colors.muted }]}>{s.body}</Text>
              </View>
            );
          })}

          {report.watchlist.length > 0 && (
            <>
              <View style={styles.watchHead}>
                <Text style={[styles.watchLabel, { color: colors.muted }]}>{t('report.watchlist')}</Text>
                <Text style={[styles.watchFresh, { color: colors.faint }]}>
                  {report.watchlist[0]?.fresh ?? ''}
                </Text>
              </View>
              {report.watchlist.map((w) => (
                <View key={w.ticker} style={[styles.watchRow, { borderBottomColor: colors.divider }]}>
                  <Text style={[styles.wTk, { color: colors.text }]}>{w.ticker}</Text>
                  <Text style={[styles.wName, { color: colors.muted }]} numberOfLines={1}>
                    {w.name}
                  </Text>
                  <Text style={[styles.wPx, { color: colors.text }]}>{w.price ?? '—'}</Text>
                  <Text
                    style={[
                      styles.wChg,
                      { color: w.changePct != null ? changeColor(colors, w.changePct) : colors.faint },
                    ]}
                  >
                    {w.changePct != null ? formatChange(w.changePct) : '—'}
                  </Text>
                </View>
              ))}
            </>
          )}

          <Text style={[styles.footnote, { color: colors.faint }]}>
            {t('report.footnote')}
          </Text>
        </ScrollView>
      )}

      <HackerLoader
        visible={loading}
        kicker={t('loader.report.kicker')}
        scrambleWord={t('loader.report.scramble')}
        headline={scope === SINGLE && ticker.trim() ? ticker.trim().toUpperCase() : t('loader.report.headline')}
        steps={loaderSteps}
        logLines={loaderLogs}
        onCancel={() => {
          abort.current?.abort();
          abort.current = null;
          setLoading(false);
        }}
      />
    </View>
  );
}

function GenerateButton({
  label,
  onPress,
  disabled,
}: {
  label: string;
  onPress: () => void;
  disabled?: boolean;
}) {
  const { colors } = useTheme();
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      style={[styles.cta, { backgroundColor: colors.accent, opacity: disabled ? 0.4 : 1 }]}
    >
      <Text style={[styles.ctaText, { color: colors.onAccent }]}>{label}</Text>
      <Feather name="chevron-right" size={16} color={colors.onAccent} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  headerIcons: { flexDirection: 'row', alignItems: 'center', gap: 14 },
  regen: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    borderWidth: 1,
    paddingHorizontal: 8,
    paddingVertical: 5,
  },
  regenText: { fontSize: 11, fontWeight: '800', letterSpacing: 0.3 },
  control: { paddingHorizontal: 16, paddingVertical: 10, gap: 10 },
  input: { borderWidth: 1, paddingHorizontal: 12, paddingVertical: 10, fontSize: 14, fontWeight: '600' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12, padding: 32 },
  centerTitle: { fontSize: 20, fontWeight: '900' },
  centerBody: { fontSize: 13, textAlign: 'center', lineHeight: 19, maxWidth: 260 },
  cta: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 12, paddingHorizontal: 18, marginTop: 6 },
  ctaText: { fontSize: 14, fontWeight: '800' },
  body: { padding: 16 },
  note: { fontSize: 13, lineHeight: 19, marginBottom: 8 },
  takeaway: { borderTopWidth: 3, paddingTop: 12, marginBottom: 16 },
  takeawayKicker: { fontSize: 10, fontWeight: '900', letterSpacing: 1.2, marginBottom: 8 },
  takeawayText: { fontSize: 19, fontWeight: '900', lineHeight: 23, letterSpacing: -0.3 },
  section: { paddingVertical: 14, borderBottomWidth: 2 },
  sectionHead: { flexDirection: 'row', alignItems: 'center', gap: 9, marginBottom: 7 },
  dot: { width: 10, height: 10 },
  sectionTitle: { fontSize: 15, fontWeight: '900', letterSpacing: -0.15, flexShrink: 1 },
  sectionSent: { marginLeft: 'auto', fontSize: 9, fontWeight: '800', letterSpacing: 0.5 },
  sectionBody: { fontSize: 13, lineHeight: 19.5 },
  watchHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 16, marginBottom: 6 },
  watchLabel: { fontSize: 10, fontWeight: '900', letterSpacing: 1 },
  watchFresh: { fontSize: 9, fontWeight: '800', letterSpacing: 0.5 },
  watchRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 9, borderBottomWidth: 1 },
  wTk: { fontSize: 12.5, fontWeight: '800', width: 46 },
  wName: { fontSize: 11, flex: 1 },
  wPx: { fontSize: 12.5, fontWeight: '700', fontVariant: ['tabular-nums'] },
  wChg: { fontSize: 12, fontWeight: '800', width: 66, textAlign: 'right', fontVariant: ['tabular-nums'] },
  footnote: { fontSize: 10, fontWeight: '600', lineHeight: 14, marginTop: 14 },
});
