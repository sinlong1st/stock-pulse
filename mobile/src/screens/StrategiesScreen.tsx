/**
 * Manage the lens the AI reasons through: pick the active strategy, write your
 * own, edit or retire them.
 *
 * The built-in is read-only and always present — it's the baseline any custom
 * strategy gets compared against, so it can't be edited away.
 */
import { Feather } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ScreenHeader } from '../components/ScreenHeader';
import {
  activateStrategy,
  archiveStrategy,
  createStrategy,
  fetchStrategies,
  StrategiesInfo,
  StrategyItem,
  updateStrategy,
} from '../data/api';
import { notifyActiveStrategy, primeActiveStrategy } from '../data/activeStrategy';
import { useI18n } from '../i18n/LanguageContext';
import { useTheme } from '../theme/ThemeContext';

export function StrategiesScreen() {
  const { colors } = useTheme();
  const { t } = useI18n();
  const navigation = useNavigation();
  const insets = useSafeAreaInsets();

  const [info, setInfo] = useState<StrategiesInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Which card is mid-switch, so a slow tap doesn't look like a dead one.
  const [pendingId, setPendingId] = useState<string | null>(null);
  // null = closed; a StrategyItem = editing it; 'new' = writing a fresh one.
  const [editing, setEditing] = useState<StrategyItem | 'new' | null>(null);

  const load = useCallback(async () => {
    try {
      const fresh = await fetchStrategies();
      setInfo(fresh);
      primeActiveStrategy(fresh.activeId); // baseline, don't wake anyone
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : t('strat.loadErr'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  /** Run a mutation, replacing state with the server's fresh list. */
  const mutate = async (fn: () => Promise<StrategiesInfo>, failKey: string, pending?: string) => {
    if (busy) return;
    setBusy(true);
    setPendingId(pending ?? null);
    try {
      const fresh = await fn();
      setInfo(fresh);
      setEditing(null);
      // Tell the Predict screen its on-screen read is now from an old lens.
      notifyActiveStrategy(fresh.activeId);
    } catch (e) {
      Alert.alert(t(failKey), e instanceof Error ? e.message : '');
    } finally {
      setBusy(false);
      setPendingId(null);
    }
  };

  const confirmArchive = (item: StrategyItem) =>
    Alert.alert(t('strat.removeTitle', { name: item.name }), t('strat.removeBody'), [
      { text: t('common.cancel'), style: 'cancel' },
      {
        text: t('wl.remove'),
        style: 'destructive',
        onPress: () => mutate(() => archiveStrategy(item.id), 'strat.removeErr'),
      },
    ]);

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <ScreenHeader
        kicker={t('strat.kicker')}
        title={t('strat.title')}
        right={
          <Pressable onPress={() => navigation.goBack()} hitSlop={10}>
            <Feather name="x" size={22} color={colors.text} />
          </Pressable>
        }
      />

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator color={colors.accent} />
        </View>
      ) : error ? (
        <View style={styles.center}>
          <Feather name="alert-triangle" size={30} color={colors.accent} />
          <Text style={[styles.centerBody, { color: colors.muted }]}>{error}</Text>
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={[styles.body, { paddingBottom: insets.bottom + 28 }]}
          showsVerticalScrollIndicator={false}
        >
          <Text style={[styles.intro, { color: colors.muted }]}>{t('strat.intro')}</Text>

          {info?.strategies.map((s) => (
            <Pressable
              key={s.id}
              onPress={() =>
                !s.active && mutate(() => activateStrategy(s.id), 'strat.activateErr', s.id)
              }
              style={[
                styles.card,
                {
                  borderColor: s.active ? colors.accent : colors.dividerStrong,
                  backgroundColor: s.active ? colors.accentBg : 'transparent',
                },
              ]}
            >
              <View style={styles.cardTop}>
                <View style={styles.cardTitleWrap}>
                  <Text style={[styles.cardTitle, { color: colors.text }]}>{s.name}</Text>
                  {s.builtin ? (
                    <View style={[styles.tag, { borderColor: colors.dividerStrong }]}>
                      <Text style={[styles.tagText, { color: colors.faint }]}>
                        {t('strat.builtin')}
                      </Text>
                    </View>
                  ) : null}
                </View>
                {pendingId === s.id ? (
                  <ActivityIndicator size="small" color={colors.accent} />
                ) : s.active ? (
                  <View style={[styles.activePill, { backgroundColor: colors.accent }]}>
                    <Text style={[styles.activeText, { color: colors.onAccent }]}>
                      {t('strat.active')}
                    </Text>
                  </View>
                ) : (
                  <Text style={[styles.useText, { color: colors.accentInk }]}>
                    {t('strat.use')}
                  </Text>
                )}
              </View>

              {/* A long strategy would otherwise push the card off-screen. */}
              <Text style={[styles.cardBody, { color: colors.muted }]} numberOfLines={6}>
                {s.body}
              </Text>

              {!s.builtin ? (
                <View style={styles.cardActions}>
                  <Pressable onPress={() => setEditing(s)} hitSlop={8} style={styles.action}>
                    <Feather name="edit-2" size={12} color={colors.accentInk} />
                    <Text style={[styles.actionText, { color: colors.accentInk }]}>
                      {t('strat.edit')}
                    </Text>
                  </Pressable>
                  <Pressable onPress={() => confirmArchive(s)} hitSlop={8} style={styles.action}>
                    <Feather name="trash-2" size={12} color={colors.bear} />
                    <Text style={[styles.actionText, { color: colors.bear }]}>
                      {t('wl.remove')}
                    </Text>
                  </Pressable>
                </View>
              ) : null}
            </Pressable>
          ))}

          <Pressable
            onPress={() => setEditing('new')}
            style={[styles.addBtn, { backgroundColor: colors.accent }]}
          >
            <Feather name="plus" size={16} color={colors.onAccent} />
            <Text style={[styles.addText, { color: colors.onAccent }]}>{t('strat.add')}</Text>
          </Pressable>

          <Text style={[styles.footnote, { color: colors.faint }]}>{t('strat.footnote')}</Text>
        </ScrollView>
      )}

      <EditorModal
        target={editing}
        limits={info?.limits}
        busy={busy}
        onClose={() => setEditing(null)}
        onSave={(name, body) =>
          mutate(
            () =>
              editing && editing !== 'new'
                ? updateStrategy(editing.id, name, body)
                : createStrategy(name, body),
            'strat.saveErr',
          )
        }
      />
    </View>
  );
}

function EditorModal({
  target,
  limits,
  busy,
  onClose,
  onSave,
}: {
  target: StrategyItem | 'new' | null;
  limits?: StrategiesInfo['limits'];
  busy: boolean;
  onClose: () => void;
  onSave: (name: string, body: string) => void;
}) {
  const { colors } = useTheme();
  const { t } = useI18n();
  const [name, setName] = useState('');
  const [body, setBody] = useState('');

  // Refill the fields whenever a different strategy is opened.
  useEffect(() => {
    if (target && target !== 'new') {
      setName(target.name);
      setBody(target.body);
    } else if (target === 'new') {
      setName('');
      setBody('');
    }
  }, [target]);

  const maxBody = limits?.bodyChars ?? 2000;
  const minBody = limits?.minBodyChars ?? 20;
  const canSave = name.trim().length > 0 && body.trim().length >= minBody && !busy;

  return (
    <Modal visible={target !== null} animationType="slide" onRequestClose={onClose}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={{ flex: 1, backgroundColor: colors.bg }}
      >
        <ScreenHeader
          kicker={t('strat.kicker')}
          title={target === 'new' ? t('strat.newTitle') : t('strat.editTitle')}
          right={
            <Pressable onPress={onClose} hitSlop={10}>
              <Feather name="x" size={22} color={colors.text} />
            </Pressable>
          }
        />
        <ScrollView contentContainerStyle={styles.editorBody} keyboardShouldPersistTaps="handled">
          <Text style={[styles.label, { color: colors.muted }]}>{t('strat.nameLabel')}</Text>
          <TextInput
            value={name}
            onChangeText={setName}
            maxLength={limits?.nameChars ?? 60}
            placeholder={t('strat.namePlaceholder')}
            placeholderTextColor={colors.faint}
            style={[
              styles.input,
              { color: colors.text, backgroundColor: colors.surface, borderColor: colors.dividerStrong },
            ]}
          />

          <View style={styles.labelRow}>
            <Text style={[styles.label, { color: colors.muted }]}>{t('strat.bodyLabel')}</Text>
            <Text
              style={[
                styles.counter,
                { color: body.length > maxBody ? colors.bear : colors.faint },
              ]}
            >
              {body.length}/{maxBody}
            </Text>
          </View>
          <TextInput
            value={body}
            onChangeText={setBody}
            maxLength={maxBody}
            multiline
            textAlignVertical="top"
            placeholder={t('strat.bodyPlaceholder')}
            placeholderTextColor={colors.faint}
            style={[
              styles.input,
              styles.textarea,
              { color: colors.text, backgroundColor: colors.surface, borderColor: colors.dividerStrong },
            ]}
          />

          <Text style={[styles.hint, { color: colors.faint }]}>{t('strat.bodyHint')}</Text>

          <Pressable
            onPress={() => onSave(name, body)}
            disabled={!canSave}
            style={[styles.saveBtn, { backgroundColor: colors.accent, opacity: canSave ? 1 : 0.4 }]}
          >
            {busy ? (
              <ActivityIndicator size="small" color={colors.onAccent} />
            ) : (
              <Text style={[styles.saveText, { color: colors.onAccent }]}>{t('strat.save')}</Text>
            )}
          </Pressable>
        </ScrollView>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12, padding: 32 },
  centerBody: { fontSize: 13, textAlign: 'center', lineHeight: 19 },
  body: { padding: 16, gap: 12 },
  intro: { fontSize: 12.5, lineHeight: 18, marginBottom: 2 },
  card: { borderWidth: 2, padding: 13, gap: 8 },
  cardTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  cardTitleWrap: { flexDirection: 'row', alignItems: 'center', gap: 7, flexShrink: 1 },
  cardTitle: { fontSize: 15, fontWeight: '900', letterSpacing: -0.2, flexShrink: 1 },
  tag: { borderWidth: 1, paddingHorizontal: 5, paddingVertical: 1 },
  tagText: { fontSize: 8, fontWeight: '900', letterSpacing: 0.6 },
  activePill: { paddingHorizontal: 8, paddingVertical: 3 },
  activeText: { fontSize: 9, fontWeight: '900', letterSpacing: 0.7 },
  useText: { fontSize: 11, fontWeight: '800' },
  cardBody: { fontSize: 12, lineHeight: 18 },
  cardActions: { flexDirection: 'row', gap: 16, marginTop: 2 },
  action: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  actionText: { fontSize: 11, fontWeight: '800' },
  addBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 7,
    paddingVertical: 13,
    marginTop: 4,
  },
  addText: { fontSize: 14, fontWeight: '800' },
  footnote: { fontSize: 10, lineHeight: 15, fontWeight: '600', marginTop: 6 },
  editorBody: { padding: 16, gap: 8 },
  label: { fontSize: 10, fontWeight: '900', letterSpacing: 1 },
  labelRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'baseline',
    marginTop: 8,
  },
  counter: { fontSize: 10, fontWeight: '700', fontVariant: ['tabular-nums'] },
  input: { borderWidth: 1, paddingHorizontal: 12, paddingVertical: 10, fontSize: 14, fontWeight: '600' },
  textarea: { minHeight: 190, fontWeight: '500', lineHeight: 20 },
  hint: { fontSize: 10.5, lineHeight: 16, marginTop: 2 },
  saveBtn: { paddingVertical: 14, alignItems: 'center', marginTop: 14 },
  saveText: { fontSize: 14, fontWeight: '800' },
});
