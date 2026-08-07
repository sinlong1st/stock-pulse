/**
 * Edit when briefings arrive, from the phone.
 *
 * Times are entered as HH:MM text rather than a native picker: the server
 * validates the same strings, the values are coarse (a briefing at 08:31 is not
 * a thing anyone wants), and a text field behaves identically on both platforms.
 * Invalid input is caught locally for a fast response, and again server-side —
 * these values build cron triggers, so nothing malformed may reach storage.
 */
import { Feather } from '@expo/vector-icons';
import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from 'react-native';

import { BriefingInfo, saveBriefingSchedule } from '../data/api';
import { useI18n } from '../i18n/LanguageContext';
import { useTheme } from '../theme/ThemeContext';
import { ScreenHeader } from './ScreenHeader';

const HHMM = /^([01]?\d|2[0-3]):[0-5]\d$/;
const MAX_EVERY_HOURS = 12;

const minutes = (hhmm: string) => {
  const [h, m] = hhmm.split(':').map(Number);
  return h * 60 + m;
};

export function BriefingScheduleEditor({
  visible,
  briefing,
  onClose,
  onSaved,
}: {
  visible: boolean;
  briefing: BriefingInfo | null;
  onClose: () => void;
  onSaved: (updated: BriefingInfo) => void;
}) {
  const { colors } = useTheme();
  const { t } = useI18n();

  const [enabled, setEnabled] = useState(true);
  const [morning, setMorning] = useState('08:30');
  const [every, setEvery] = useState('2');
  const [until, setUntil] = useState('16:30');
  const [wrap, setWrap] = useState('18:00');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Refill from the server's values each time the sheet opens.
  useEffect(() => {
    if (!visible || !briefing) return;
    setEnabled(briefing.enabled);
    setMorning(briefing.morningAt);
    setEvery(String(briefing.intradayEveryHours));
    setUntil(briefing.intradayUntil);
    setWrap(briefing.wrapAt);
    setError(null);
  }, [visible, briefing]);

  /** Mirror of the server's rules, so mistakes are caught before a round trip. */
  const validate = (): string | null => {
    for (const [value, label] of [
      [morning, t('brief.morning')],
      [until, t('brief.until')],
      [wrap, t('brief.wrap')],
    ] as const) {
      if (!HHMM.test(value.trim())) return t('brief.errTime', { field: label });
    }
    const n = Number(every);
    if (!Number.isInteger(n) || n < 1 || n > MAX_EVERY_HOURS) {
      return t('brief.errEvery', { max: MAX_EVERY_HOURS });
    }
    if (minutes(until) < minutes(morning)) return t('brief.errUntilBefore');
    if (minutes(wrap) < minutes(morning)) return t('brief.errWrapBefore');
    return null;
  };

  const save = async () => {
    const problem = validate();
    if (problem) {
      setError(problem);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const updated = await saveBriefingSchedule({
        enabled,
        morningAt: morning.trim(),
        intradayEveryHours: Number(every),
        intradayUntil: until.trim(),
        wrapAt: wrap.trim(),
      });
      onSaved(updated);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : t('brief.saveErr'));
    } finally {
      setSaving(false);
    }
  };

  const field = (
    label: string,
    value: string,
    setValue: (v: string) => void,
    hint?: string,
  ) => (
    <View style={styles.field}>
      <Text style={[styles.label, { color: colors.muted }]}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={setValue}
        editable={enabled}
        keyboardType="numbers-and-punctuation"
        maxLength={5}
        placeholder="08:30"
        placeholderTextColor={colors.faint}
        style={[
          styles.input,
          {
            color: enabled ? colors.text : colors.faint,
            backgroundColor: colors.surface,
            borderColor: colors.dividerStrong,
          },
        ]}
      />
      {hint ? <Text style={[styles.hint, { color: colors.faint }]}>{hint}</Text> : null}
    </View>
  );

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <View style={{ flex: 1, backgroundColor: colors.bg }}>
        <ScreenHeader
          kicker={t('report.kicker')}
          title={t('set.briefing')}
          right={
            <Pressable onPress={onClose} hitSlop={10}>
              <Feather name="x" size={22} color={colors.text} />
            </Pressable>
          }
        />
        <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
          <View style={[styles.toggleRow, { borderBottomColor: colors.divider }]}>
            <View style={styles.toggleText}>
              <Text style={[styles.toggleLabel, { color: colors.text }]}>
                {t('brief.enabled')}
              </Text>
              <Text style={[styles.hint, { color: colors.faint }]}>{t('brief.enabledHint')}</Text>
            </View>
            <Switch
              value={enabled}
              onValueChange={setEnabled}
              trackColor={{ true: colors.accent, false: colors.dividerStrong }}
              thumbColor={colors.onAccent}
            />
          </View>

          {field(t('brief.morning'), morning, setMorning, t('brief.morningHint'))}

          <View style={styles.field}>
            <Text style={[styles.label, { color: colors.muted }]}>{t('brief.every')}</Text>
            <TextInput
              value={every}
              onChangeText={setEvery}
              editable={enabled}
              keyboardType="number-pad"
              maxLength={2}
              style={[
                styles.input,
                {
                  color: enabled ? colors.text : colors.faint,
                  backgroundColor: colors.surface,
                  borderColor: colors.dividerStrong,
                },
              ]}
            />
            <Text style={[styles.hint, { color: colors.faint }]}>{t('brief.everyHint')}</Text>
          </View>

          {field(t('brief.until'), until, setUntil, t('brief.untilHint'))}
          {field(t('brief.wrap'), wrap, setWrap, t('brief.wrapHint'))}

          <Text style={[styles.tz, { color: colors.faint }]}>
            {t('brief.timezone', { tz: briefing?.timezone ?? '—' })}
          </Text>

          {error ? (
            <View style={[styles.errorBox, { borderColor: colors.bear }]}>
              <Text style={[styles.errorText, { color: colors.bear }]}>{error}</Text>
            </View>
          ) : null}

          <Pressable
            onPress={save}
            disabled={saving}
            style={[styles.saveBtn, { backgroundColor: colors.accent, opacity: saving ? 0.5 : 1 }]}
          >
            {saving ? (
              <ActivityIndicator size="small" color={colors.onAccent} />
            ) : (
              <Text style={[styles.saveText, { color: colors.onAccent }]}>{t('strat.save')}</Text>
            )}
          </Pressable>
        </ScrollView>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  body: { padding: 16, gap: 4 },
  toggleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingBottom: 14,
    marginBottom: 10,
    borderBottomWidth: 1,
  },
  toggleText: { flex: 1, gap: 2 },
  toggleLabel: { fontSize: 14, fontWeight: '700' },
  field: { gap: 5, marginBottom: 14 },
  label: { fontSize: 10, fontWeight: '900', letterSpacing: 1 },
  input: {
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 15,
    fontWeight: '700',
    fontVariant: ['tabular-nums'],
  },
  hint: { fontSize: 10.5, lineHeight: 15 },
  tz: { fontSize: 10.5, marginTop: 2 },
  errorBox: { borderWidth: 1, padding: 10, marginTop: 12 },
  errorText: { fontSize: 12, fontWeight: '700', lineHeight: 17 },
  saveBtn: { paddingVertical: 14, alignItems: 'center', marginTop: 18 },
  saveText: { fontSize: 14, fontWeight: '800' },
});
