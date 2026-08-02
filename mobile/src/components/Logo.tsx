import React from 'react';
import { Image } from 'react-native';

/** The StockPulse pulse mark, tinted to any color. Subtle in-app branding. */
export function Logo({ size = 20, color }: { size?: number; color: string }) {
  return (
    <Image
      source={require('../../assets/logo-mark.png')}
      style={{ width: size, height: size, tintColor: color }}
      resizeMode="contain"
    />
  );
}
