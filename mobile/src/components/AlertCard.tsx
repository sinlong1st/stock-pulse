import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { Alert } from '../data/types';
import { useTheme } from '../theme/ThemeContext';
import { ImportanceMeter } from './ImportanceMeter';
import { PriceLine } from './PriceLine';
import { SentimentPill } from './SentimentPill';
import { CategoryTag, TickerChip } from './Tags';

/** The workhorse Feed card — importance, category, summary, why, tickers, price. */
export function AlertCard({ alert, onPress }: { alert: Alert; onPress?: () => void }) {
  const { colors } = useTheme();
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.card,
        { borderBottomColor: colors.divider, backgroundColor: pressed ? colors.surface : colors.bg },
      ]}
    >
      {/* header row */}
      <View style={styles.headerRow}>
        <ImportanceMeter level={alert.importance} />
        <CategoryTag label={alert.category} />
        <Text style={[styles.time, { color: colors.faint }]}>{alert.time}</Text>
      </View>

      {/* summary */}
      <Text style={[styles.summary, { color: colors.text }]}>{alert.summary}</Text>

      {/* why it matters */}
      <View style={styles.whyRow}>
        <Text style={[styles.whyTag, { color: colors.accentInk }]}>WHY</Text>
        <Text style={[styles.whyText, { color: colors.muted }]}>{alert.why}</Text>
      </View>

      {/* tickers + sentiment */}
      <View style={styles.tickerRow}>
        {alert.tickers.map((t) => (
          <TickerChip key={t} symbol={t} />
        ))}
        <View style={styles.sentiment}>
          <SentimentPill value={alert.sentiment} />
        </View>
      </View>

      {/* price line — only when the item carries price context */}
      {alert.price ? <PriceLine price={alert.price} /> : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: { borderBottomWidth: 2, paddingHorizontal: 16, paddingTop: 13, paddingBottom: 14, gap: 8 },
  headerRow: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  time: { marginLeft: 'auto', fontSize: 10, fontWeight: '700' },
  summary: { fontSize: 14.5, fontWeight: '700', lineHeight: 18, letterSpacing: -0.15 },
  whyRow: { flexDirection: 'row', gap: 7 },
  whyTag: { fontSize: 12, fontWeight: '900' },
  whyText: { flex: 1, fontSize: 12, lineHeight: 16.5, fontWeight: '400' },
  tickerRow: { flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' },
  sentiment: { marginLeft: 'auto' },
});
