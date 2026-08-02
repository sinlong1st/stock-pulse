import React from 'react';
import { View } from 'react-native';

/** A lightweight column chart (no native deps). Heights are min-normalized so
 * the shape of the series is what shows. The last column can be emphasized. */
export function MiniBars({
  values,
  color,
  lastColor,
  height = 56,
}: {
  values: number[];
  color: string;
  lastColor?: string;
  height?: number;
}) {
  if (!values.length) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const floor = 3;
  return (
    <View style={{ flexDirection: 'row', alignItems: 'flex-end', height, gap: 1 }}>
      {values.map((v, i) => (
        <View
          key={i}
          style={{
            flex: 1,
            height: floor + ((v - min) / span) * (height - floor),
            backgroundColor: i === values.length - 1 && lastColor ? lastColor : color,
          }}
        />
      ))}
    </View>
  );
}
