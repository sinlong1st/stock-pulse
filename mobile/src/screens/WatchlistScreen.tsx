import { Feather } from '@expo/vector-icons';
import React from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { ScreenHeader } from '../components/ScreenHeader';
import { SentimentPill } from '../components/SentimentPill';
import { mockWatchlist } from '../data/mock';
import { useTheme } from '../theme/ThemeContext';
import { changeColor, formatChange } from '../theme/semantics';

export function WatchlistScreen() {
  const { colors } = useTheme();
  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <ScreenHeader
        kicker={`${mockWatchlist.length} STOCKS`}
        title="Watchlist"
        right={
          <View style={[styles.add, { backgroundColor: colors.accent }]}>
            <Feather name="plus" size={20} color={colors.onAccent} />
          </View>
        }
      />
      <ScrollView showsVerticalScrollIndicator={false}>
        {mockWatchlist.map((w) => (
          <View key={w.ticker} style={[styles.row, { borderBottomColor: colors.divider }]}>
            <View style={{ flex: 1 }}>
              <View style={styles.tickerRow}>
                <Text style={[styles.ticker, { color: colors.text }]}>{w.ticker}</Text>
                <SentimentPill value={w.sentiment} />
              </View>
              <Text style={[styles.name, { color: colors.muted }]}>{w.name}</Text>
            </View>
            <View style={{ alignItems: 'flex-end' }}>
              <Text style={[styles.px, { color: colors.text }]}>{w.price}</Text>
              <Text style={[styles.chg, { color: changeColor(colors, w.changePct) }]}>
                {formatChange(w.changePct)}
              </Text>
            </View>
          </View>
        ))}
        <Text style={[styles.footer, { color: colors.faint }]}>
          SWIPE A ROW TO REMOVE · AS OF FRI 13:00 PDT
        </Text>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  add: { width: 34, height: 34, alignItems: 'center', justifyContent: 'center' },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: 2 },
  tickerRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  ticker: { fontSize: 16, fontWeight: '900' },
  name: { fontSize: 11, marginTop: 3 },
  px: { fontSize: 15, fontWeight: '800', fontVariant: ['tabular-nums'] },
  chg: { fontSize: 12, fontWeight: '800', fontVariant: ['tabular-nums'] },
  footer: { fontSize: 10, fontWeight: '800', letterSpacing: 0.5, textAlign: 'center', paddingVertical: 12 },
});
