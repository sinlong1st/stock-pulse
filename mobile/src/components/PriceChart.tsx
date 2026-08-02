import React, { useState } from 'react';
import { GestureResponderEvent, LayoutChangeEvent, StyleSheet, Text, View } from 'react-native';
import Svg, { Circle, Line, Path } from 'react-native-svg';

import { useTheme } from '../theme/ThemeContext';

function fmtDate(iso?: string) {
  if (!iso) return '';
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

/** Interactive price line: drag across it for a crosshair + price/date tooltip. */
export function PriceChart({
  values,
  dates,
  height = 128,
}: {
  values: number[];
  dates?: string[];
  height?: number;
}) {
  const { colors } = useTheme();
  const [width, setWidth] = useState(0);
  const [active, setActive] = useState<number | null>(null);

  if (values.length < 2) return null;

  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pad = 8;
  const h = height - pad * 2;
  const n = values.length;

  const x = (i: number) => (width <= 0 ? 0 : (i / (n - 1)) * width);
  const y = (v: number) => pad + (1 - (v - min) / span) * h;

  const line = values.map((v, i) => `${i === 0 ? 'M' : 'L'} ${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(' ');
  const area = width > 0 ? `${line} L ${width.toFixed(1)} ${height} L 0 ${height} Z` : '';

  const rise = values[n - 1] >= values[0];
  const stroke = rise ? colors.bull : colors.bear;

  const onTouch = (e: GestureResponderEvent) => {
    if (width <= 0) return;
    const lx = e.nativeEvent.locationX;
    setActive(Math.max(0, Math.min(n - 1, Math.round((lx / width) * (n - 1)))));
  };

  return (
    <View onLayout={(e: LayoutChangeEvent) => setWidth(e.nativeEvent.layout.width)} style={{ height }}>
      {width > 0 && (
        <Svg width={width} height={height}>
          <Path d={area} fill={stroke} fillOpacity={0.1} />
          <Path d={line} stroke={stroke} strokeWidth={2} fill="none" />
          {active != null && (
            <>
              <Line x1={x(active)} y1={0} x2={x(active)} y2={height} stroke={colors.dividerStrong} strokeWidth={1} />
              <Circle cx={x(active)} cy={y(values[active])} r={4} fill={stroke} />
            </>
          )}
        </Svg>
      )}

      {/* touch layer */}
      <View
        style={StyleSheet.absoluteFill}
        onStartShouldSetResponder={() => true}
        onMoveShouldSetResponder={() => true}
        onResponderGrant={onTouch}
        onResponderMove={onTouch}
        onResponderRelease={() => setActive(null)}
        onResponderTerminate={() => setActive(null)}
      />

      {/* tooltip */}
      {active != null && width > 0 && (
        <View
          pointerEvents="none"
          style={[
            styles.tip,
            {
              backgroundColor: colors.elevated,
              borderColor: colors.dividerStrong,
              left: Math.max(0, Math.min(width - 92, x(active) - 46)),
            },
          ]}
        >
          <Text style={[styles.tipPrice, { color: colors.text }]}>${values[active].toFixed(2)}</Text>
          {dates?.[active] ? <Text style={[styles.tipDate, { color: colors.muted }]}>{fmtDate(dates[active])}</Text> : null}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  tip: { position: 'absolute', top: 0, width: 92, alignItems: 'center', paddingVertical: 4, borderWidth: 1 },
  tipPrice: { fontSize: 12, fontWeight: '800', fontVariant: ['tabular-nums'] },
  tipDate: { fontSize: 9, fontWeight: '700' },
});
