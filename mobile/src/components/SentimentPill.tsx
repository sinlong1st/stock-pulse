import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { Sentiment } from '../data/types';
import { useTheme } from '../theme/ThemeContext';
import { sentiment as sentimentOf } from '../theme/semantics';

/** Bullish/bearish/neutral as a glyph + label pill (never color alone). */
export function SentimentPill({ value }: { value: Sentiment }) {
  const { colors } = useTheme();
  const meta = sentimentOf(colors, value);
  return (
    <View style={[styles.wrap, { backgroundColor: meta.bg }]}>
      <Text style={[styles.glyph, { color: meta.fg }]}>{meta.glyph}</Text>
      <Text style={[styles.label, { color: meta.fg }]}>{meta.label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingVertical: 3, paddingHorizontal: 9 },
  glyph: { fontSize: 11, fontWeight: '900', lineHeight: 13 },
  label: { fontSize: 9, fontWeight: '800', letterSpacing: 0.5 },
});
