import { DefaultTheme, NavigationContainer, Theme } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import React, { useEffect } from 'react';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

import { LanguageProvider, useI18n } from './src/i18n/LanguageContext';
import { Tabs } from './src/navigation/Tabs';
import { RootStackParamList } from './src/navigation/types';
import { registerForPush } from './src/push';
import { AlertDetailScreen } from './src/screens/AlertDetailScreen';
import { EvaluationScreen } from './src/screens/EvaluationScreen';
import { StrategiesScreen } from './src/screens/StrategiesScreen';
import { ThemeProvider, useTheme } from './src/theme/ThemeContext';

const Stack = createNativeStackNavigator<RootStackParamList>();

// Hold the native splash ourselves so the first frame is already in the right
// language. Rejections are ignored: the splash may already be gone on reload.
SplashScreen.preventAutoHideAsync().catch(() => {});

/** Keeps the splash up until the language config has resolved. */
function SplashGate({ children }: { children: React.ReactNode }) {
  const { ready } = useI18n();

  useEffect(() => {
    if (ready) SplashScreen.hideAsync().catch(() => {});
  }, [ready]);

  return ready ? <>{children}</> : null;
}

function Root() {
  const { colors, mode } = useTheme();

  useEffect(() => {
    registerForPush();
  }, []);

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
        <Stack.Navigator screenOptions={{ headerShown: false }}>
          <Stack.Screen name="Tabs" component={Tabs} />
          <Stack.Screen name="AlertDetail" component={AlertDetailScreen} />
          <Stack.Screen name="Evaluation" component={EvaluationScreen} />
          <Stack.Screen name="Strategies" component={StrategiesScreen} />
        </Stack.Navigator>
      </SafeAreaView>
    </NavigationContainer>
  );
}

export default function App() {
  return (
    <SafeAreaProvider>
      <ThemeProvider>
        <LanguageProvider>
          <SplashGate>
            <Root />
          </SplashGate>
        </LanguageProvider>
      </ThemeProvider>
    </SafeAreaProvider>
  );
}
