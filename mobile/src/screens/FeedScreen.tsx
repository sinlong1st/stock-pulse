import { Feather } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { AlertCard } from '../components/AlertCard';
import { ScreenHeader } from '../components/ScreenHeader';
import { Segmented } from '../components/Segmented';
import { fetchFeed, usingMockData } from '../data/api';
import { Alert } from '../data/types';
import { useI18n } from '../i18n/LanguageContext';
import { RootStackParamList } from '../navigation/types';
import { useTheme } from '../theme/ThemeContext';

const FILTERS = ['All', 'Watchlist', 'Macro'] as const;
const FILTER_KEY: Record<string, string> = { All: 'feed.all', Watchlist: 'feed.watchlist', Macro: 'feed.macro' };

export function FeedScreen() {
  const { colors } = useTheme();
  const { t } = useI18n();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const [filter, setFilter] = useState<string>('All');
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);
  const [query, setQuery] = useState('');

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
    let rows = alerts;
    if (filter === 'Macro') rows = rows.filter((a) => a.category === 'MACRO');
    else if (filter === 'Watchlist') rows = rows.filter((a) => a.tickers.length > 0);

    const q = query.trim().toLowerCase();
    if (q) {
      rows = rows.filter((a) =>
        [a.summary, a.why, a.source, ...a.tickers].join(' ').toLowerCase().includes(q),
      );
    }
    return rows;
  }, [alerts, filter, query]);

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <ScreenHeader
        showLogo
        kicker={usingMockData ? t('feed.sample') : 'STOCKPULSE'}
        title={t('feed.title')}
        right={
          <View style={styles.icons}>
            <Feather
              name={searching ? 'x' : 'search'}
              size={21}
              color={colors.text}
              onPress={() => {
                setSearching((v) => !v);
                if (searching) setQuery('');
              }}
            />
            <View>
              <Feather name="bell" size={21} color={colors.text} />
              <View style={[styles.badge, { backgroundColor: colors.accent, borderColor: colors.bg }]} />
            </View>
          </View>
        }
      />

      {searching ? (
        <View style={[styles.searchRow, { borderColor: colors.dividerStrong, backgroundColor: colors.surface }]}>
          <Feather name="search" size={16} color={colors.muted} />
          <TextInput
            value={query}
            onChangeText={setQuery}
            placeholder={t('feed.search')}
            placeholderTextColor={colors.faint}
            autoFocus
            autoCorrect={false}
            style={[styles.searchInput, { color: colors.text }]}
          />
          {query ? (
            <Pressable onPress={() => setQuery('')} hitSlop={8}>
              <Feather name="x-circle" size={16} color={colors.faint} />
            </Pressable>
          ) : null}
        </View>
      ) : (
        <View style={styles.filterRow}>
          <Segmented
            options={[...FILTERS]}
            value={filter}
            onChange={setFilter}
            renderLabel={(v) => t(FILTER_KEY[v])}
          />
        </View>
      )}

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator color={colors.accent} />
          <Text style={[styles.centerText, { color: colors.muted }]}>{t('feed.fetching')}</Text>
        </View>
      ) : error ? (
        <View style={styles.center}>
          <Feather name="alert-triangle" size={34} color={colors.accent} />
          <Text style={[styles.centerTitle, { color: colors.text }]}>{t('feed.errTitle')}</Text>
          <Text style={[styles.centerBody, { color: colors.muted }]}>{error}</Text>
        </View>
      ) : data.length === 0 ? (
        <View style={styles.center}>
          <Feather name={query ? 'search' : 'bell'} size={34} color={colors.muted} />
          <Text style={[styles.centerTitle, { color: colors.text }]}>
            {query ? t('feed.noMatch') : t('feed.caughtUp')}
          </Text>
          <Text style={[styles.centerBody, { color: colors.muted }]}>
            {query ? t('feed.noMatchBody', { q: query.trim() }) : t('feed.caughtUpBody')}
          </Text>
        </View>
      ) : (
        <FlatList
          data={data}
          keyExtractor={(a) => a.id}
          renderItem={({ item }) => (
            <AlertCard alert={item} onPress={() => navigation.navigate('AlertDetail', { alert: item })} />
          )}
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
  searchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginHorizontal: 16,
    marginVertical: 10,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderWidth: 1,
  },
  searchInput: { flex: 1, fontSize: 14, fontWeight: '600', padding: 0 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12, padding: 32 },
  centerText: { fontSize: 10, fontWeight: '800', letterSpacing: 0.6 },
  centerTitle: { fontSize: 20, fontWeight: '900' },
  centerBody: { fontSize: 13, textAlign: 'center', lineHeight: 19, maxWidth: 240 },
});
