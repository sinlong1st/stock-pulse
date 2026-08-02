import { Feather } from '@expo/vector-icons';
import React, { useEffect, useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Switch, Text, View } from 'react-native';

import {
  BriefingInfo,
  Channels,
  fetchSettings,
  Language,
  setChannel,
  setLanguage,
  usingMockData,
} from '../data/api';
import { Logo } from '../components/Logo';
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
      {!danger && !value?.length && onPress ? (
        <Feather name="chevron-right" size={16} color={colors.faint} />
      ) : null}
    </Pressable>
  );
}

function ToggleRow({
  label,
  hint,
  value,
  onValueChange,
  disabled,
}: {
  label: string;
  hint?: string;
  value: boolean;
  onValueChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  const { colors } = useTheme();
  return (
    <View style={[styles.row, { borderTopColor: colors.divider, opacity: disabled ? 0.55 : 1 }]}>
      <View style={{ flex: 1 }}>
        <Text style={[styles.rowLabel, { color: colors.text }]}>{label}</Text>
        {hint ? <Text style={[styles.hint, { color: colors.faint }]}>{hint}</Text> : null}
      </View>
      <Switch
        value={value}
        onValueChange={onValueChange}
        disabled={disabled}
        trackColor={{ true: colors.accent, false: colors.dividerStrong }}
        thumbColor={colors.onAccent}
      />
    </View>
  );
}

async function onCheckUpdate() {
  const r = await checkForUpdate();
  if (r === 'current') Alert.alert('Up to date', 'You’re on the latest version.');
  else if (r === 'dev') Alert.alert('Dev mode', 'OTA updates only apply in a real (EAS) build.');
  else if (r === 'error') Alert.alert('Couldn’t check', 'Try again in a moment.');
}

export function SettingsScreen() {
  const { colors, mode, toggle } = useTheme();
  const [language, setLang] = useState('English');
  const [languages, setLanguages] = useState<Language[]>([]);
  const [channels, setChannels] = useState<Channels | null>(null);
  const [briefing, setBriefing] = useState<BriefingInfo | null>(null);

  useEffect(() => {
    if (usingMockData) return;
    fetchSettings()
      .then((s) => {
        setLang(s.language);
        setLanguages(s.languages);
        setChannels(s.channels);
        setBriefing(s.briefing);
      })
      .catch(() => {});
  }, []);

  const changeLanguage = () => {
    const opts = languages.length
      ? languages
      : [
          { code: 'en', name: 'English' },
          { code: 'vi', name: 'Vietnamese' },
        ];
    Alert.alert('Output language', 'Applies to alerts and briefings.', [
      ...opts.map((l) => ({
        text: l.name,
        onPress: async () => {
          try {
            const r = await setLanguage(l.code);
            setLang(r.language);
          } catch (e) {
            Alert.alert('Couldn’t change language', e instanceof Error ? e.message : '');
          }
        },
      })),
      { text: 'Cancel', style: 'cancel' as const },
    ]);
  };

  const toggleChannel = async (which: 'telegram' | 'push', next: boolean) => {
    if (!channels) return;
    const prev = channels;
    setChannels({ ...channels, [which]: { ...channels[which], enabled: next } });
    try {
      await setChannel(which, next);
    } catch (e) {
      setChannels(prev); // revert
      Alert.alert('Couldn’t update', e instanceof Error ? e.message : '');
    }
  };

  const briefingValue = briefing
    ? briefing.enabled
      ? `Daily · ${briefing.morningAt}`
      : 'Off'
    : '—';

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

        <SectionLabel>NOTIFICATIONS</SectionLabel>
        <ToggleRow
          label="Push to this phone"
          hint="Alerts on your lock screen"
          value={channels?.push.enabled ?? false}
          onValueChange={(v) => toggleChannel('push', v)}
        />
        <ToggleRow
          label="Telegram"
          hint={channels?.telegram.configured ? 'Also send alerts to Telegram' : 'Not set up on the server'}
          value={channels?.telegram.enabled ?? false}
          onValueChange={(v) => toggleChannel('telegram', v)}
          disabled={!channels?.telegram.configured}
        />

        <SectionLabel>PREFERENCES</SectionLabel>
        <Row label="Language" value={language} onPress={changeLanguage} />
        <Row
          label="Briefing schedule"
          value={briefingValue}
          onPress={() =>
            Alert.alert(
              'Briefing schedule',
              briefing
                ? `Morning ${briefing.morningAt}, then every ${briefing.intradayEveryHours}h until ${briefing.intradayUntil}, wrap ${briefing.wrapAt} (${briefing.timezone}).\n\nEdited on the server for now.`
                : '',
            )
          }
        />
        <View style={[styles.row, { borderTopColor: colors.divider }]}>
          <Text style={[styles.rowLabel, { color: colors.text }]}>Dark theme</Text>
          <Switch
            value={mode === 'dark'}
            onValueChange={toggle}
            trackColor={{ true: colors.accent, false: colors.dividerStrong }}
            thumbColor={colors.onAccent}
          />
        </View>

        <SectionLabel>ACCOUNT</SectionLabel>
        <Row label="Manage subscription" onPress={() => {}} />
        <Row label="Check for updates" onPress={onCheckUpdate} />
        <Row label="Sign out" onPress={() => {}} />
        <Row label="Delete account" danger onPress={() => {}} />

        <View style={styles.brandRow}>
          <Logo size={13} color={colors.faint} />
          <Text style={[styles.version, { color: colors.faint }]}>StockPulse · {versionLabel()}</Text>
        </View>
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
  hint: { fontSize: 10.5, marginTop: 2 },
  brandRow: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 16, paddingTop: 20 },
  version: { fontSize: 10, fontWeight: '700' },
  disclaimer: { fontSize: 10, fontWeight: '600', paddingHorizontal: 16, paddingTop: 6, paddingBottom: 20 },
});
