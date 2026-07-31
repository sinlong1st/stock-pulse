import { Feather } from '@expo/vector-icons';
import React from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Switch, Text, View } from 'react-native';

import { ScreenHeader } from '../components/ScreenHeader';
import { useTheme } from '../theme/ThemeContext';
import { checkForUpdate, versionLabel } from '../updates';

function SectionLabel({ children }: { children: string }) {
  const { colors } = useTheme();
  return <Text style={[styles.sectionLabel, { color: colors.muted }]}>{children}</Text>;
}

function Row({
  label,
  value,
  danger,
  onPress,
}: {
  label: string;
  value?: string;
  danger?: boolean;
  onPress?: () => void;
}) {
  const { colors } = useTheme();
  return (
    <Pressable onPress={onPress} style={[styles.row, { borderTopColor: colors.divider }]}>
      <Text style={[styles.rowLabel, { color: danger ? colors.accent : colors.text }]}>{label}</Text>
      {value ? <Text style={[styles.rowValue, { color: colors.muted }]}>{value}</Text> : null}
      {!danger && <Feather name="chevron-right" size={16} color={colors.faint} />}
    </Pressable>
  );
}

async function onCheckUpdate() {
  const r = await checkForUpdate();
  if (r === 'current') Alert.alert('Up to date', 'You’re on the latest version.');
  else if (r === 'dev') Alert.alert('Dev mode', 'OTA updates only apply in a real (EAS) build.');
  else if (r === 'error') Alert.alert('Couldn’t check', 'Try again in a moment.');
  // 'downloading' reloads the app automatically.
}

export function SettingsScreen() {
  const { colors, mode, toggle } = useTheme();
  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <ScreenHeader kicker="ACCOUNT" title="Settings" />
      <ScrollView showsVerticalScrollIndicator={false}>
        {/* profile */}
        <View style={[styles.profile, { borderBottomColor: colors.divider }]}>
          <View style={[styles.avatar, { backgroundColor: colors.accent }]}>
            <Text style={[styles.avatarText, { color: colors.onAccent }]}>JR</Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={[styles.name, { color: colors.text }]}>Jordan Reyes</Text>
            <Text style={[styles.email, { color: colors.muted }]}>jordan@stockpulse.app</Text>
          </View>
          <View style={[styles.pro, { backgroundColor: colors.accent }]}>
            <Text style={[styles.proText, { color: colors.onAccent }]}>PRO</Text>
          </View>
        </View>

        <SectionLabel>PREFERENCES</SectionLabel>
        <Row label="Language" value="English" />
        <Row label="Quiet hours" value="10 PM – 7 AM" />
        <Row label="Briefing schedule" value="Daily · 8:00 AM" />
        {/* live theme toggle */}
        <View style={[styles.row, { borderTopColor: colors.divider }]}>
          <Text style={[styles.rowLabel, { color: colors.text }]}>Dark theme</Text>
          <Switch
            value={mode === 'dark'}
            onValueChange={toggle}
            trackColor={{ true: colors.accent, false: colors.dividerStrong }}
            thumbColor={colors.onAccent}
          />
        </View>

        <SectionLabel>INTEGRATIONS &amp; ACCOUNT</SectionLabel>
        <Row label="Link Telegram" value="✓ @jreyes" />
        <Row label="Manage subscription" />
        <Row label="Check for updates" onPress={onCheckUpdate} />
        <Row label="Sign out" />
        <Row label="Delete account" danger />

        <Text style={[styles.version, { color: colors.faint }]}>{versionLabel()}</Text>
        <Text style={[styles.disclaimer, { color: colors.faint }]}>
          AI-generated summaries. Not investment advice.
        </Text>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  profile: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: 2 },
  avatar: { width: 42, height: 42, alignItems: 'center', justifyContent: 'center' },
  avatarText: { fontSize: 16, fontWeight: '900' },
  name: { fontSize: 15, fontWeight: '800' },
  email: { fontSize: 11, marginTop: 1 },
  pro: { paddingHorizontal: 8, paddingVertical: 3 },
  proText: { fontSize: 10, fontWeight: '800' },
  sectionLabel: { fontSize: 10, fontWeight: '900', letterSpacing: 1, paddingHorizontal: 16, paddingTop: 14, paddingBottom: 6 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, paddingVertical: 13, borderTopWidth: 1 },
  rowLabel: { flex: 1, fontSize: 13.5, fontWeight: '700' },
  rowValue: { fontSize: 12 },
  version: { fontSize: 10, fontWeight: '700', paddingHorizontal: 16, paddingTop: 20 },
  disclaimer: { fontSize: 10, fontWeight: '600', paddingHorizontal: 16, paddingTop: 6, paddingBottom: 20 },
});
