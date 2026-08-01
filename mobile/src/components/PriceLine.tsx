import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { PriceSnapshot } from '../data/types';
import { useTheme } from '../theme/ThemeContext';
import { changeColor, formatChange } from '../theme/semantics';

/** Ticker · price · %-vs-open · freshness. `LIVE` shows a dot; else the as-of stamp. */
export function PriceLine({ price }: { price: PriceSnapshot }) {
  const { colors } = useTheme();
  const isLive = price.fresh.toUpperCase() === 'LIVE';
  return (
    <View style={styles.row}>
      <Text style={[styles.sym, { color: colors.text }]}>{price.symbol}</Text>
      <Text style={[styles.px, { color: colors.text }]}>{price.price}</Text>
      {price.changePct != null ? (
        <Text style={[styles.chg, { color: changeColor(colors, price.changePct) }]}>
          {formatChange(price.changePct)}
        </Text>
      ) : null}
      <View style={styles.fresh}>
        {isLive && <View style={[styles.dot, { backgroundColor: colors.bull }]} />}
        <Text style={[styles.freshText, { color: colors.faint }]}>{price.fresh}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  sym: { fontSize: 12.5, fontWeight: '800' },
  px: { fontSize: 12.5, fontWeight: '700', fontVariant: ['tabular-nums'] },
  chg: { fontSize: 11.5, fontWeight: '800', fontVariant: ['tabular-nums'] },
  fresh: { marginLeft: 'auto', flexDirection: 'row', alignItems: 'center', gap: 4 },
  dot: { width: 6, height: 6 },
  freshText: { fontSize: 8.5, fontWeight: '800', letterSpacing: 0.5 },
});
