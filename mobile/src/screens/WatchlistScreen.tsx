import { Feather } from '@expo/vector-icons';
import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';

import { ScreenHeader } from '../components/ScreenHeader';
import { SentimentPill } from '../components/SentimentPill';
import { fetchWatchlist } from '../data/api';
import { WatchRow } from '../data/types';
import { useTheme } from '../theme/ThemeContext';
import { changeColor, formatChange } from '../theme/semantics';

export function WatchlistScreen() {
  const { colors } = useTheme();
  const [rows, setRows] = useState<WatchRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    try {
      setRows(await fetchWatchlist());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Couldn’t load your watchlist.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <ScreenHeader
        kicker={rows.length ? `${rows.length} STOCKS` : 'WATCHLIST'}
        title="Watchlist"
        right={
          <View style={[styles.add, { backgroundColor: colors.accent }]}>
            <Feather name="plus" size={20} color={colors.onAccent} />
          </View>
        }
      />

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
            <View key={w.ticker} style={[styles.row, { borderBottomColor: colors.divider }]}>
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
            </View>
          ))}
          <Text style={[styles.footer, { color: colors.faint }]}>
            {rows[0]?.fresh ? `AS OF ${rows[0].fresh}` : 'PULL TO REFRESH'}
          </Text>
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  add: { width: 34, height: 34, alignItems: 'center', justifyContent: 'center' },
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
