/**
 * Tap-to-fill row of your watchlist tickers, so Report and Predict don't make
 * you type a symbol you already track. Loads once and stays quiet on failure —
 * it's a shortcut, never the only way in (the text input still works).
 */
import React, { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { fetchWatchlist } from '../data/api';
import { WatchRow } from '../data/types';
import { useI18n } from '../i18n/LanguageContext';
import { useTheme } from '../theme/ThemeContext';

/** Roughly two rows on a phone before the tail collapses behind "+N". */
const COLLAPSED_COUNT = 8;

export function WatchlistPicker({
  selected,
  onPick,
}: {
  /** Currently chosen ticker, so the matching chip can read as active. */
  selected?: string;
  onPick: (ticker: string) => void;
}) {
  const { colors } = useTheme();
  const { t } = useI18n();
  const [rows, setRows] = useState<WatchRow[]>([]);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let alive = true;
    fetchWatchlist()
      .then((r) => alive && setRows(r))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  if (!rows.length) return null;

  const active = selected?.trim().toUpperCase();
  // Show a couple of rows, then collapse the tail behind a "+N" chip. Wrapping
  // beats a horizontal scroller here: nothing is hidden off-screen edge.
  const visible = expanded ? rows : rows.slice(0, COLLAPSED_COUNT);
  const hidden = rows.length - visible.length;

  return (
    <View style={styles.wrap}>
      <Text style={[styles.label, { color: colors.faint }]}>{t('picker.label')}</Text>
      <View style={styles.row}>
        {visible.map((r) => {
          const on = active === r.ticker.toUpperCase();
          return (
            <Pressable
              key={r.ticker}
              onPress={() => onPick(r.ticker)}
              style={[
                styles.chip,
                {
                  backgroundColor: on ? colors.accent : colors.surface,
                  borderColor: on ? colors.accent : colors.dividerStrong,
                },
              ]}
            >
              <Text style={[styles.chipText, { color: on ? colors.onAccent : colors.text }]}>
                {r.ticker}
              </Text>
            </Pressable>
          );
        })}

        {hidden > 0 || expanded ? (
          <Pressable
            onPress={() => setExpanded((e) => !e)}
            style={[styles.chip, styles.moreChip, { borderColor: colors.dividerStrong }]}
          >
            <Text style={[styles.chipText, { color: colors.muted }]}>
              {expanded ? t('picker.less') : `+${hidden}`}
            </Text>
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 5 },
  label: { fontSize: 9, fontWeight: '900', letterSpacing: 0.8 },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  chip: { borderWidth: 1, paddingHorizontal: 11, paddingVertical: 6 },
  moreChip: { backgroundColor: 'transparent' },
  chipText: { fontSize: 12, fontWeight: '800', letterSpacing: 0.3 },
});
