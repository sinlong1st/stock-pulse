import { Feather } from '@expo/vector-icons';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import React from 'react';
import { Linking, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ImportanceMeter } from '../components/ImportanceMeter';
import { SentimentPill } from '../components/SentimentPill';
import { CategoryTag, TickerChip } from '../components/Tags';
import { useI18n } from '../i18n/LanguageContext';
import { RootStackParamList } from '../navigation/types';
import { useTheme } from '../theme/ThemeContext';

type Props = NativeStackScreenProps<RootStackParamList, 'AlertDetail'>;

export function AlertDetailScreen({ route, navigation }: Props) {
  const { colors } = useTheme();
  const { t } = useI18n();
  const insets = useSafeAreaInsets();
  const { alert } = route.params;

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      {/* top bar */}
      <View style={[styles.topbar, { borderBottomColor: colors.dividerStrong }]}>
        <Pressable onPress={() => navigation.goBack()} hitSlop={10}>
          <Feather name="arrow-left" size={22} color={colors.text} />
        </Pressable>
        <Text style={[styles.topbarTitle, { color: colors.text }]}>{t('alert.title')}</Text>
      </View>

      <ScrollView
        contentContainerStyle={[styles.body, { paddingBottom: insets.bottom + 28 }]}
        showsVerticalScrollIndicator={false}
      >
        {/* meta */}
        <View style={styles.metaRow}>
          <ImportanceMeter level={alert.importance} />
          <CategoryTag label={alert.category} />
          <Text style={[styles.time, { color: colors.faint }]}>{t('alert.ago', { time: alert.time })}</Text>
        </View>

        {/* headline */}
        <Text style={[styles.headline, { color: colors.text }]}>{alert.summary}</Text>

        {/* sentiment + tickers */}
        <View style={styles.chips}>
          <SentimentPill value={alert.sentiment} />
          {alert.tickers.map((sym) => (
            <TickerChip key={sym} symbol={sym} />
          ))}
        </View>

        <View style={[styles.rule, { backgroundColor: colors.divider }]} />

        {/* why it matters */}
        <Text style={[styles.sectionLabel, { color: colors.accentInk }]}>{t('alert.why')}</Text>
        <Text style={[styles.why, { color: colors.text }]}>{alert.why}</Text>

        {/* affected tickers */}
        {alert.tickers.length > 0 && (
          <>
            <Text style={[styles.sectionLabel, { color: colors.muted, marginTop: 20 }]}>
              {t('alert.affected')}
            </Text>
            <View style={styles.tickerList}>
              {alert.tickers.map((sym) => (
                <TickerChip key={sym} symbol={sym} />
              ))}
            </View>
          </>
        )}

        {/* source */}
        <View style={[styles.source, { backgroundColor: colors.surface }]}>
          <View style={{ flex: 1 }}>
            <Text style={[styles.sourceName, { color: colors.text }]}>{alert.source}</Text>
          </View>
          {alert.url ? (
            <Pressable style={styles.open} onPress={() => Linking.openURL(alert.url!)}>
              <Text style={[styles.openText, { color: colors.accentInk }]}>{t('alert.open')}</Text>
              <Feather name="external-link" size={13} color={colors.accentInk} />
            </Pressable>
          ) : null}
        </View>

        <Text style={[styles.disclaimer, { color: colors.faint }]}>
          {t('alert.disclaimer')}
        </Text>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 14, paddingTop: 6, paddingBottom: 12, borderBottomWidth: 2 },
  topbarTitle: { fontSize: 14, fontWeight: '800' },
  body: { padding: 16, gap: 14 },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  time: { marginLeft: 'auto', fontSize: 10, fontWeight: '700' },
  headline: { fontSize: 22, fontWeight: '900', lineHeight: 26, letterSpacing: -0.4 },
  chips: { flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  rule: { height: 2 },
  sectionLabel: { fontSize: 10, fontWeight: '900', letterSpacing: 1, marginBottom: 8 },
  why: { fontSize: 13.5, lineHeight: 20 },
  tickerList: { flexDirection: 'row', gap: 6, flexWrap: 'wrap' },
  source: { flexDirection: 'row', alignItems: 'center', gap: 10, padding: 12, marginTop: 6 },
  sourceName: { fontSize: 12, fontWeight: '800' },
  open: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  openText: { fontSize: 12, fontWeight: '800' },
  disclaimer: { fontSize: 10, fontWeight: '600', lineHeight: 14, marginTop: 4 },
});
