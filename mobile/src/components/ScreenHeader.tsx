import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { useTheme } from '../theme/ThemeContext';

/** The tall modernist screen header: an accent kicker over a heavy title. */
export function ScreenHeader({
  kicker,
  title,
  right,
}: {
  kicker: string;
  title: string;
  right?: React.ReactNode;
}) {
  const { colors } = useTheme();
  return (
    <View style={[styles.wrap, { borderBottomColor: colors.dividerStrong }]}>
      <View>
        <Text style={[styles.kicker, { color: colors.accent }]}>{kicker}</Text>
        <Text style={[styles.title, { color: colors.text }]}>{title}</Text>
      </View>
      {right ? <View style={styles.right}>{right}</View> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingTop: 4,
    paddingBottom: 12,
    borderBottomWidth: 2,
  },
  kicker: { fontSize: 9, fontWeight: '900', letterSpacing: 1.5 },
  title: { fontSize: 27, fontWeight: '900', letterSpacing: -0.5, marginTop: 2 },
  right: { paddingBottom: 4 },
});
