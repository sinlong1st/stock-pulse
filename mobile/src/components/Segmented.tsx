import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useTheme } from '../theme/ThemeContext';

/** A modernist segmented control (bordered, square, filled active segment). */
export function Segmented({
  options,
  value,
  onChange,
  renderLabel,
}: {
  options: string[];
  value: string;
  onChange: (v: string) => void;
  renderLabel?: (v: string) => string;
}) {
  const { colors } = useTheme();
  return (
    <View style={[styles.wrap, { borderColor: colors.dividerStrong }]}>
      {options.map((opt, i) => {
        const active = opt === value;
        return (
          <Pressable
            key={opt}
            onPress={() => onChange(opt)}
            style={[
              styles.seg,
              i > 0 && { borderLeftWidth: 1, borderLeftColor: colors.dividerStrong },
              active && { backgroundColor: colors.accent },
            ]}
          >
            <Text style={[styles.segText, { color: active ? colors.onAccent : colors.muted }]}>
              {renderLabel ? renderLabel(opt) : opt}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flexDirection: 'row', borderWidth: 1, alignSelf: 'flex-start' },
  seg: { paddingVertical: 6, paddingHorizontal: 12 },
  segText: { fontSize: 11, fontWeight: '800' },
});
