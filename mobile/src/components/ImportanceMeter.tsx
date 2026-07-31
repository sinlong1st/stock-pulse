import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { Importance } from '../data/types';
import { useTheme } from '../theme/ThemeContext';
import { importance as importanceOf } from '../theme/semantics';

/** LOW→CRITICAL as a 1–4 notch meter + label (per the design). */
export function ImportanceMeter({ level }: { level: Importance }) {
  const { colors } = useTheme();
  const meta = importanceOf(colors, level);
  const cells = [0, 1, 2, 3];

  return (
    <View style={[styles.wrap, { backgroundColor: meta.bg }]}>
      <View style={styles.cells}>
        {cells.map((i) => (
          <View
            key={i}
            style={[
              styles.cell,
              { backgroundColor: i < meta.filled ? meta.fg : colors.dividerStrong },
            ]}
          />
        ))}
      </View>
      <Text style={[styles.label, { color: meta.fg }]}>{meta.label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flexDirection: 'row', alignItems: 'center', gap: 7, paddingVertical: 3, paddingHorizontal: 8 },
  cells: { flexDirection: 'row', gap: 2 },
  cell: { width: 3, height: 11 },
  label: { fontSize: 9, fontWeight: '800', letterSpacing: 0.6 },
});
