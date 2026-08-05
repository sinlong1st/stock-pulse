import { Feather } from '@expo/vector-icons';
import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { ScreenHeader } from '../components/ScreenHeader';
import { SentimentPill } from '../components/SentimentPill';
import { addWatch, fetchWatchlist, removeWatch } from '../data/api';
import { WatchRow } from '../data/types';
import { primeWatchlist } from '../data/useWatchlist';
import { useI18n } from '../i18n/LanguageContext';
import { useTheme } from '../theme/ThemeContext';
import { changeColor, formatChange } from '../theme/semantics';

export function WatchlistScreen() {
  const { colors } = useTheme();
  const { t } = useI18n();
  const [rows, setRows] = useState<WatchRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [query, setQuery] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    try {
      const fresh = await fetchWatchlist();
      setRows(fresh);
      primeWatchlist(fresh); // keep the Report/Predict pickers in step
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : t('wl.loadErr'));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const submitAdd = async () => {
    if (!query.trim() || busy) return;
    setBusy(true);
    try {
      const res = await addWatch(query.trim());
      if (res.added) {
        setQuery('');
        setAdding(false);
        await load(true);
      } else {
        Alert.alert(t('wl.notAdded'), res.reason ?? t('wl.addErr'));
      }
    } catch (e) {
      Alert.alert(t('wl.addErr'), e instanceof Error ? e.message : '');
    } finally {
      setBusy(false);
    }
  };

  const confirmRemove = (w: WatchRow) => {
    Alert.alert(t('wl.removeTitle', { ticker: w.ticker }), w.name ?? '', [
      { text: t('common.cancel'), style: 'cancel' },
      {
        text: t('wl.remove'),
        style: 'destructive',
        onPress: async () => {
          try {
            await removeWatch(w.ticker);
            await load(true);
          } catch (e) {
            Alert.alert(t('wl.removeErr'), e instanceof Error ? e.message : '');
          }
        },
      },
    ]);
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <ScreenHeader
        kicker={rows.length ? t('wl.count', { n: rows.length }) : t('wl.label')}
        title={t('wl.title')}
        right={
          <Pressable
            onPress={() => setAdding((v) => !v)}
            style={[styles.add, { backgroundColor: adding ? colors.surface2 : colors.accent }]}
          >
            <Feather name={adding ? 'x' : 'plus'} size={20} color={adding ? colors.text : colors.onAccent} />
          </Pressable>
        }
      />

      {adding && (
        <View style={styles.addBar}>
          <TextInput
            value={query}
            onChangeText={setQuery}
            placeholder={t('wl.addPlaceholder')}
            placeholderTextColor={colors.faint}
            autoCapitalize="none"
            autoCorrect={false}
            autoFocus
            onSubmitEditing={submitAdd}
            style={[
              styles.input,
              { color: colors.text, backgroundColor: colors.surface, borderColor: colors.dividerStrong },
            ]}
          />
          <Pressable
            onPress={submitAdd}
            disabled={busy || !query.trim()}
            style={[styles.addBtn, { backgroundColor: colors.accent, opacity: busy || !query.trim() ? 0.4 : 1 }]}
          >
            {busy ? (
              <ActivityIndicator size="small" color={colors.onAccent} />
            ) : (
              <Text style={[styles.addBtnText, { color: colors.onAccent }]}>{t('wl.add')}</Text>
            )}
          </Pressable>
        </View>
      )}

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator color={colors.accent} />
        </View>
      ) : error ? (
        <View style={styles.center}>
          <Feather name="alert-triangle" size={30} color={colors.accent} />
          <Text style={[styles.errorText, { color: colors.muted }]}>{error}</Text>
        </View>
      ) : (
        <ScrollView
          showsVerticalScrollIndicator={false}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor={colors.accent} />
          }
        >
          {rows.map((w) => (
            <Pressable
              key={w.ticker}
              onLongPress={() => confirmRemove(w)}
              style={[styles.row, { borderBottomColor: colors.divider }]}
            >
              <View style={{ flex: 1 }}>
                <View style={styles.tickerRow}>
                  <Text style={[styles.ticker, { color: colors.text }]}>{w.ticker}</Text>
                  {w.sentiment ? <SentimentPill value={w.sentiment} /> : null}
                </View>
                <Text style={[styles.name, { color: colors.muted }]}>{w.name}</Text>
              </View>
              <View style={{ alignItems: 'flex-end' }}>
                <Text style={[styles.px, { color: colors.text }]}>{w.price ?? '—'}</Text>
                {w.changePct != null ? (
                  <Text style={[styles.chg, { color: changeColor(colors, w.changePct) }]}>
                    {formatChange(w.changePct)}
                  </Text>
                ) : (
                  <Text style={[styles.chg, { color: colors.faint }]}>—</Text>
                )}
              </View>
            </Pressable>
          ))}
          <Text style={[styles.footer, { color: colors.faint }]}>
            {t('wl.footer')}
          </Text>
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  add: { width: 34, height: 34, alignItems: 'center', justifyContent: 'center' },
  addBar: { flexDirection: 'row', gap: 8, paddingHorizontal: 16, paddingVertical: 10 },
  input: { flex: 1, borderWidth: 1, paddingHorizontal: 12, paddingVertical: 10, fontSize: 14, fontWeight: '600' },
  addBtn: { paddingHorizontal: 18, alignItems: 'center', justifyContent: 'center' },
  addBtnText: { fontSize: 14, fontWeight: '800' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12, padding: 32 },
  errorText: { fontSize: 13, textAlign: 'center', lineHeight: 19, maxWidth: 260 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: 2 },
  tickerRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  ticker: { fontSize: 16, fontWeight: '900' },
  name: { fontSize: 11, marginTop: 3 },
  px: { fontSize: 15, fontWeight: '800', fontVariant: ['tabular-nums'] },
  chg: { fontSize: 12, fontWeight: '800', fontVariant: ['tabular-nums'] },
  footer: { fontSize: 10, fontWeight: '800', letterSpacing: 0.5, textAlign: 'center', paddingVertical: 12 },
});
