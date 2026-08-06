import { Feather } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
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
import { RootStackParamList } from '../navigation/types';
import { useI18n } from '../i18n/LanguageContext';
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

export function SettingsScreen() {
  const { colors, mode, toggle } = useTheme();
  const { t, language, setLanguage: setCtxLanguage } = useI18n();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const [languages, setLanguages] = useState<Language[]>([]);
  const [channels, setChannels] = useState<Channels | null>(null);
  const [briefing, setBriefing] = useState<BriefingInfo | null>(null);

  useEffect(() => {
    if (usingMockData) return;
    fetchSettings()
      .then((s) => {
        setLanguages(s.languages);
        setChannels(s.channels);
        setBriefing(s.briefing);
      })
      .catch(() => {});
  }, []);

  const onCheckUpdate = async () => {
    const r = await checkForUpdate();
    if (r === 'current') Alert.alert(t('set.upToDate'), t('set.upToDateBody'));
    else if (r === 'dev') Alert.alert(t('set.devMode'), t('set.devModeBody'));
    else if (r === 'error') Alert.alert(t('set.checkErr'), t('set.checkErrBody'));
  };

  const changeLanguage = () => {
    const opts = languages.length
      ? languages
      : [
          { code: 'en', name: 'English' },
          { code: 'vi', name: 'Vietnamese' },
        ];
    Alert.alert(t('set.langTitle'), t('set.langBody'), [
      ...opts.map((l) => ({
        text: l.name,
        onPress: async () => {
          try {
            const r = await setLanguage(l.code);
            setCtxLanguage(r.language);
          } catch (e) {
            Alert.alert(t('set.langErr'), e instanceof Error ? e.message : '');
          }
        },
      })),
      { text: t('common.cancel'), style: 'cancel' as const },
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
      ? `${t('set.briefingDaily')} · ${briefing.morningAt}`
      : t('set.briefingOff')
    : '—';

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <ScreenHeader kicker={t('set.kicker')} title={t('set.title')} />
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

        <SectionLabel>{t('set.notifications')}</SectionLabel>
        <ToggleRow
          label={t('set.push')}
          hint={t('set.pushHint')}
          value={channels?.push.enabled ?? false}
          onValueChange={(v) => toggleChannel('push', v)}
        />
        <ToggleRow
          label={t('set.telegram')}
          hint={channels?.telegram.configured ? t('set.telegramOn') : t('set.telegramOff')}
          value={channels?.telegram.enabled ?? false}
          onValueChange={(v) => toggleChannel('telegram', v)}
          disabled={!channels?.telegram.configured}
        />

        <SectionLabel>{t('set.preferences')}</SectionLabel>
        <Row label={t('set.language')} value={language} onPress={changeLanguage} />
        <Row
          label={t('strat.title')}
          onPress={() => navigation.navigate('Strategies')}
        />
        <Row
          label={t('set.briefing')}
          value={briefingValue}
          onPress={() =>
            Alert.alert(
              t('set.briefing'),
              briefing
                ? t('set.briefingDetail', {
                    morning: briefing.morningAt,
                    hours: briefing.intradayEveryHours,
                    until: briefing.intradayUntil,
                    wrap: briefing.wrapAt,
                    tz: briefing.timezone,
                  })
                : '',
            )
          }
        />
        <View style={[styles.row, { borderTopColor: colors.divider }]}>
          <Text style={[styles.rowLabel, { color: colors.text }]}>{t('set.darkTheme')}</Text>
          <Switch
            value={mode === 'dark'}
            onValueChange={toggle}
            trackColor={{ true: colors.accent, false: colors.dividerStrong }}
            thumbColor={colors.onAccent}
          />
        </View>

        <SectionLabel>{t('set.kicker')}</SectionLabel>
        <Row label={t('set.manageSub')} onPress={() => {}} />
        <Row label={t('set.checkUpdates')} onPress={onCheckUpdate} />
        <Row label={t('set.signOut')} onPress={() => {}} />
        <Row label={t('set.deleteAccount')} danger onPress={() => {}} />

        <View style={styles.brandRow}>
          <Logo size={13} color={colors.faint} />
          <Text style={[styles.version, { color: colors.faint }]}>StockPulse · {versionLabel()}</Text>
        </View>
        <Text style={[styles.disclaimer, { color: colors.faint }]}>
          {t('set.disclaimer')}
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
