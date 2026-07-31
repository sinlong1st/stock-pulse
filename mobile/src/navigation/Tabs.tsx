import { Feather } from '@expo/vector-icons';
import { BottomTabNavigationOptions, createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import React from 'react';

import { FeedScreen } from '../screens/FeedScreen';
import { ReportScreen } from '../screens/ReportScreen';
import { SettingsScreen } from '../screens/SettingsScreen';
import { WatchlistScreen } from '../screens/WatchlistScreen';
import { useTheme } from '../theme/ThemeContext';

const Tab = createBottomTabNavigator();

type IconName = React.ComponentProps<typeof Feather>['name'];
const ICONS: Record<string, IconName> = {
  Feed: 'list',
  Report: 'bar-chart-2',
  Watchlist: 'eye',
  Settings: 'sliders',
};

export function Tabs() {
  const { colors } = useTheme();

  const screenOptions = ({ route }: { route: { name: string } }): BottomTabNavigationOptions => ({
    headerShown: false,
    tabBarActiveTintColor: colors.accent,
    tabBarInactiveTintColor: colors.muted,
    tabBarStyle: {
      backgroundColor: colors.bg,
      borderTopColor: colors.divider,
      borderTopWidth: 2,
    },
    tabBarLabelStyle: { fontSize: 10, fontWeight: '800' },
    tabBarIcon: ({ color, size }) => <Feather name={ICONS[route.name]} size={size - 2} color={color} />,
  });

  return (
    <Tab.Navigator screenOptions={screenOptions}>
      <Tab.Screen name="Feed" component={FeedScreen} />
      <Tab.Screen name="Report" component={ReportScreen} />
      <Tab.Screen name="Watchlist" component={WatchlistScreen} />
      <Tab.Screen name="Settings" component={SettingsScreen} />
    </Tab.Navigator>
  );
}
