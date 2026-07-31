import { Feather } from '@expo/vector-icons';
import React, { useMemo, useState } from 'react';
import { FlatList, StyleSheet, Text, View } from 'react-native';

import { AlertCard } from '../components/AlertCard';
import { ScreenHeader } from '../components/ScreenHeader';
import { Segmented } from '../components/Segmented';
import { mockAlerts } from '../data/mock';
import { useTheme } from '../theme/ThemeContext';

const FILTERS = ['All', 'Watchlist', 'Macro'] as const;

export function FeedScreen() {
  const { colors, toggle } = useTheme();
  const [filter, setFilter] = useState<string>('All');

  const data = useMemo(() => {
    if (filter === 'Macro') return mockAlerts.filter((a) => a.category === 'MACRO');
    if (filter === 'Watchlist') return mockAlerts.filter((a) => a.tickers.length > 0);
    return mockAlerts;
  }, [filter]);

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <ScreenHeader
        kicker="STOCKPULSE"
        title="Feed"
        right={
          <View style={styles.icons}>
            {/* theme toggle stands in for search until wired */}
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

      <View style={[styles.refresh, { backgroundColor: colors.surface }]}>
        <Feather name="refresh-cw" size={12} color={colors.muted} />
        <Text style={[styles.refreshText, { color: colors.muted }]}>UPDATED 2 MIN AGO · PULL TO REFRESH</Text>
      </View>

      <FlatList
        data={data}
        keyExtractor={(a) => a.id}
        renderItem={({ item }) => <AlertCard alert={item} />}
        showsVerticalScrollIndicator={false}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  icons: { flexDirection: 'row', gap: 16, alignItems: 'center' },
  badge: { position: 'absolute', top: -1, right: -1, width: 8, height: 8, borderWidth: 1.5 },
  filterRow: { paddingHorizontal: 16, paddingVertical: 10 },
  refresh: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 7 },
  refreshText: { fontSize: 10, fontWeight: '800', letterSpacing: 0.6 },
});
