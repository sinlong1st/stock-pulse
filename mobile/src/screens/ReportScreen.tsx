import React, { useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { ScreenHeader } from '../components/ScreenHeader';
import { Segmented } from '../components/Segmented';
import { mockReport } from '../data/mock';
import { useTheme } from '../theme/ThemeContext';
import { changeColor, formatChange, sentiment as sentimentOf } from '../theme/semantics';

export function ReportScreen() {
  const { colors } = useTheme();
  const [scope, setScope] = useState('Whole watchlist');
  const r = mockReport;

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <ScreenHeader kicker={`BRIEFING · ${r.dateLabel}`} title="Report" />
      <View style={styles.scope}>
        <Segmented options={['Whole watchlist', 'Single stock']} value={scope} onChange={setScope} />
      </View>

      <ScrollView contentContainerStyle={styles.body} showsVerticalScrollIndicator={false}>
        {/* takeaway */}
        <View style={[styles.takeaway, { borderTopColor: colors.accent }]}>
          <Text style={[styles.takeawayKicker, { color: colors.accentInk }]}>TODAY'S TAKEAWAY</Text>
          <Text style={[styles.takeawayText, { color: colors.text }]}>{r.takeaway}</Text>
        </View>

        {/* themed sections */}
        {r.sections.map((s) => {
          const meta = sentimentOf(colors, s.sentiment);
          return (
            <View key={s.title} style={[styles.section, { borderBottomColor: colors.divider }]}>
              <View style={styles.sectionHead}>
                <View style={[styles.dot, { backgroundColor: meta.fg }]} />
                <Text style={[styles.sectionTitle, { color: colors.text }]}>{s.title}</Text>
                <Text style={[styles.sectionSent, { color: meta.fg }]}>
                  {meta.glyph} {meta.label}
                </Text>
              </View>
              <Text style={[styles.sectionBody, { color: colors.muted }]}>{s.body}</Text>
            </View>
          );
        })}

        {/* watchlist % vs open */}
        <View style={styles.watchHead}>
          <Text style={[styles.watchLabel, { color: colors.muted }]}>WATCHLIST · % VS OPEN</Text>
          <Text style={[styles.watchFresh, { color: colors.faint }]}>{r.freshness}</Text>
        </View>
        {r.watchlist.map((w) => (
          <View key={w.ticker} style={[styles.watchRow, { borderBottomColor: colors.divider }]}>
            <Text style={[styles.wTk, { color: colors.text }]}>{w.ticker}</Text>
            <Text style={[styles.wName, { color: colors.muted }]} numberOfLines={1}>
              {w.name}
            </Text>
            <Text style={[styles.wPx, { color: colors.text }]}>{w.price}</Text>
            <Text style={[styles.wChg, { color: changeColor(colors, w.changePct) }]}>
              {formatChange(w.changePct)}
            </Text>
          </View>
        ))}

        <Text style={[styles.footnote, { color: colors.faint }]}>{r.footnote}</Text>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  scope: { paddingHorizontal: 16, paddingVertical: 10 },
  body: { padding: 16 },
  takeaway: { borderTopWidth: 3, paddingTop: 12, marginBottom: 16 },
  takeawayKicker: { fontSize: 10, fontWeight: '900', letterSpacing: 1.2, marginBottom: 8 },
  takeawayText: { fontSize: 19, fontWeight: '900', lineHeight: 23, letterSpacing: -0.3 },
  section: { paddingVertical: 14, borderBottomWidth: 2 },
  sectionHead: { flexDirection: 'row', alignItems: 'center', gap: 9, marginBottom: 7 },
  dot: { width: 10, height: 10 },
  sectionTitle: { fontSize: 15, fontWeight: '900', letterSpacing: -0.15 },
  sectionSent: { marginLeft: 'auto', fontSize: 9, fontWeight: '800', letterSpacing: 0.5 },
  sectionBody: { fontSize: 13, lineHeight: 19.5 },
  watchHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 16, marginBottom: 6 },
  watchLabel: { fontSize: 10, fontWeight: '900', letterSpacing: 1 },
  watchFresh: { fontSize: 9, fontWeight: '800', letterSpacing: 0.5 },
  watchRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 9, borderBottomWidth: 1 },
  wTk: { fontSize: 12.5, fontWeight: '800', width: 46 },
  wName: { fontSize: 11, flex: 1 },
  wPx: { fontSize: 12.5, fontWeight: '700', fontVariant: ['tabular-nums'] },
  wChg: { fontSize: 12, fontWeight: '800', width: 66, textAlign: 'right', fontVariant: ['tabular-nums'] },
  footnote: { fontSize: 10, fontWeight: '600', lineHeight: 14, marginTop: 14 },
});
