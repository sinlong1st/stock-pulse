/**
 * Your saved holdings, on the sell tab.
 *
 * The point of this list is that an exit decision is something you revisit —
 * daily, on the same three or four names. Retyping the share count and average
 * cost every time is the difference between a feature you use and a form you
 * avoid, which is why the store exists at all.
 *
 * Tapping a row analyses by `positionId` rather than by the typed fields, so
 * the saved stop and target come along too — the backend reads them and the
 * advice accounts for them.
 */
import { Feather } from '@expo/vector-icons';
import React from 'react';
import { Alert, Pressable, StyleSheet, Text, View } from 'react-native';

import { SavedPosition } from '../data/api';
import { useI18n } from '../i18n/LanguageContext';
import { useTheme } from '../theme/ThemeContext';

export function SavedPositions({
  positions,
  activeId,
  onPick,
  onRemove,
}: {
  positions: SavedPosition[];
  /** The row currently on screen, so it reads as selected rather than as a
   *  list you tapped into and left. */
  activeId?: string | null;
  onPick: (position: SavedPosition) => void;
  onRemove: (position: SavedPosition) => void;
}) {
  const { colors } = useTheme();
  const { t } = useI18n();
  if (!positions.length) return null;

  const confirmRemove = (position: SavedPosition) =>
    Alert.alert(t('exit.removeTitle', { ticker: position.ticker }), undefined, [
      { text: t('common.cancel'), style: 'cancel' },
      { text: t('exit.remove'), style: 'destructive', onPress: () => onRemove(position) },
    ]);

  return (
    <View style={styles.wrap}>
      <Text style={[styles.label, { color: colors.faint }]}>{t('exit.savedTitle')}</Text>
      <View style={styles.rows}>
        {positions.map((position) => {
          const active = position.id === activeId;
          return (
            <Pressable
              key={position.id}
              onPress={() => onPick(position)}
              onLongPress={() => confirmRemove(position)}
              style={[
                styles.row,
                {
                  borderColor: active ? colors.accent : colors.dividerStrong,
                  backgroundColor: active ? colors.accentBg : 'transparent',
                },
              ]}
            >
              <Text style={[styles.ticker, { color: colors.text }]}>{position.ticker}</Text>
              <Text style={[styles.detail, { color: colors.muted }]}>
                {position.shares.toLocaleString()} @ ${position.averageCost.toFixed(2)}
              </Text>
              <Feather name="chevron-right" size={13} color={colors.faint} />
            </Pressable>
          );
        })}
      </View>
      <Text style={[styles.hint, { color: colors.faint }]}>{t('exit.savedHint')}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { paddingHorizontal: 16, paddingBottom: 10, gap: 5 },
  label: { fontSize: 9, fontWeight: '900', letterSpacing: 0.8 },
  rows: { gap: 6 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 9,
  },
  ticker: { fontSize: 13, fontWeight: '900', width: 62 },
  detail: { flex: 1, fontSize: 11.5, fontVariant: ['tabular-nums'] },
  hint: { fontSize: 9, fontWeight: '700', letterSpacing: 0.3 },
});
