import { DefaultTheme, NavigationContainer, Theme } from '@react-navigation/native';
import { StatusBar } from 'expo-status-bar';
import React from 'react';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

import { Tabs } from './src/navigation/Tabs';
import { ThemeProvider, useTheme } from './src/theme/ThemeContext';

function Root() {
  const { colors, mode } = useTheme();

  const navTheme: Theme = {
    ...DefaultTheme,
    dark: mode === 'dark',
    colors: {
      ...DefaultTheme.colors,
      primary: colors.accent,
      background: colors.bg,
      card: colors.bg,
      text: colors.text,
      border: colors.divider,
      notification: colors.accent,
    },
  };

  return (
    <NavigationContainer theme={navTheme}>
      <StatusBar style={mode === 'dark' ? 'light' : 'dark'} />
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }} edges={['top']}>
        <Tabs />
      </SafeAreaView>
    </NavigationContainer>
  );
}

export default function App() {
  return (
    <SafeAreaProvider>
      <ThemeProvider>
        <Root />
      </ThemeProvider>
    </SafeAreaProvider>
  );
}
