import { Feather } from '@expo/vector-icons';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, FlatList, RefreshControl, StyleSheet, Text, View } from 'react-native';

import { AlertCard } from '../components/AlertCard';
import { ScreenHeader } from '../components/ScreenHeader';
import { Segmented } from '../components/Segmented';
import { fetchFeed, usingMockData } from '../data/api';
import { Alert } from '../data/types';
import { useTheme } from '../theme/ThemeContext';

const FILTERS = ['All', 'Watchlist', 'Macro'] as const;

export function FeedScreen() {
  const { colors, toggle } = useTheme();
  const [filter, setFilter] = useState<string>('All');
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    try {
      const data = await fetchFeed();
      setAlerts(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Couldn’t reach the feed.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const data = useMemo(() => {
    if (filter === 'Macro') return alerts.filter((a) => a.category === 'MACRO');
    if (filter === 'Watchlist') return alerts.filter((a) => a.tickers.length > 0);
    return alerts;
  }, [alerts, filter]);

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <ScreenHeader
        kicker={usingMockData ? 'STOCKPULSE · SAMPLE DATA' : 'STOCKPULSE'}
        title="Feed"
        right={
          <View style={styles.icons}>
            <Feather name="search" size={21} color={colors.text} onPress={toggle} />
            <View>
              <Feather name="bell" size={21} color={colors.text} />
              <View style={[styles.badge, { backgroundColor: colors.accent, borderColor: colors.bg }]} />
            </View>
          </View>
        }
      />

      <View style={styles.filterRow}>
        <Segmented options={[...FILTERS]} value={filter} onChange={setFilter} />
      </View>

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator color={colors.accent} />
          <Text style={[styles.centerText, { color: colors.muted }]}>FETCHING LATEST</Text>
        </View>
      ) : error ? (
        <View style={styles.center}>
          <Feather name="alert-triangle" size={34} color={colors.accent} />
          <Text style={[styles.centerTitle, { color: colors.text }]}>Couldn’t reach the feed</Text>
          <Text style={[styles.centerBody, { color: colors.muted }]}>{error}</Text>
        </View>
      ) : data.length === 0 ? (
        <View style={styles.center}>
          <Feather name="bell" size={34} color={colors.muted} />
          <Text style={[styles.centerTitle, { color: colors.text }]}>All caught up</Text>
          <Text style={[styles.centerBody, { color: colors.muted }]}>
            No alerts that matter right now. Pull to refresh.
          </Text>
        </View>
      ) : (
        <FlatList
          data={data}
          keyExtractor={(a) => a.id}
          renderItem={({ item }) => <AlertCard alert={item} />}
          showsVerticalScrollIndicator={false}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor={colors.accent} />
          }
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  icons: { flexDirection: 'row', gap: 16, alignItems: 'center' },
  badge: { position: 'absolute', top: -1, right: -1, width: 8, height: 8, borderWidth: 1.5 },
  filterRow: { paddingHorizontal: 16, paddingVertical: 10 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12, padding: 32 },
  centerText: { fontSize: 10, fontWeight: '800', letterSpacing: 0.6 },
  centerTitle: { fontSize: 20, fontWeight: '900' },
  centerBody: { fontSize: 13, textAlign: 'center', lineHeight: 19, maxWidth: 240 },
});
