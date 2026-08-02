import { DefaultTheme, NavigationContainer, Theme } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { StatusBar } from 'expo-status-bar';
import React, { useEffect } from 'react';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

import { Tabs } from './src/navigation/Tabs';
import { RootStackParamList } from './src/navigation/types';
import { registerForPush } from './src/push';
import { AlertDetailScreen } from './src/screens/AlertDetailScreen';
import { EvaluationScreen } from './src/screens/EvaluationScreen';
import { ThemeProvider, useTheme } from './src/theme/ThemeContext';

const Stack = createNativeStackNavigator<RootStackParamList>();

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
        </Stack.Navigator>
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
