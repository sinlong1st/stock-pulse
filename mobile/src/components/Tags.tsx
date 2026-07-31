import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { useTheme } from '../theme/ThemeContext';

/** MACRO / TICKER / SECTOR — an outline tag. */
export function CategoryTag({ label }: { label: string }) {
  const { colors } = useTheme();
  return (
    <View style={[styles.category, { borderColor: colors.dividerStrong }]}>
      <Text style={[styles.categoryText, { color: colors.muted }]}>{label}</Text>
    </View>
  );
}

/** A ticker chip (filled surface). */
export function TickerChip({ symbol }: { symbol: string }) {
  const { colors } = useTheme();
  return (
    <View style={[styles.ticker, { backgroundColor: colors.surface2 }]}>
      <Text style={[styles.tickerText, { color: colors.text }]}>{symbol}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  category: { borderWidth: 1, paddingVertical: 3, paddingHorizontal: 7 },
  categoryText: { fontSize: 9, fontWeight: '800', letterSpacing: 0.7 },
  ticker: { paddingVertical: 3, paddingHorizontal: 7 },
  tickerText: { fontSize: 10.5, fontWeight: '800' },
});
