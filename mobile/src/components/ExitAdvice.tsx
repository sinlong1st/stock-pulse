/**
 * The Position Exit Advisor result cards.
 *
 * Every number here arrives already computed — the backend sends structured
 * values, never sentences, so this file does the phrasing and the language
 * layer does the words. Nothing is calculated in the UI beyond formatting.
 *
 * The order is the order of the question being asked (§30, §32): what you have
 * → what holding is worth from here → what falling costs → what trimming does
 * → what the cases look like → what the plans are. Anything the backend
 * couldn't compute is null and its card simply doesn't render.
 */
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import {
  ExitAdvice as Advice,
  ExitPlan,
  ExitScenario,
  GivebackLevel,
  HoldRewardRisk,
  PartialSellOption,
} from '../data/api';
import { useI18n } from '../i18n/LanguageContext';
import { useTheme } from '../theme/ThemeContext';
import { ThemeColors } from '../theme/tokens';

/** Signed money, always with its sign — the sign is the message. */
function money(value: number, { sign = true }: { sign?: boolean } = {}) {
  const body = Math.abs(value).toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  if (!sign) return `$${body}`;
  return `${value < 0 ? '−' : '+'}$${body}`;
}

const plain = (value: number) => money(value, { sign: false });

function pnlColor(c: ThemeColors, value: number) {
  if (value > 0) return c.bull;
  if (value < 0) return c.bear;
  return c.neutral;
}

/** Exposure ladder → colour. Holding is green, exiting is red, trimming sits
 *  between: the palette carries the meaning before the words are read. */
function actionColor(c: ThemeColors, action: string) {
  if (action === 'hold' || action === 'wait-for-confirmation') return c.bull;
  if (action === 'exit' || action === 'reduce') return c.bear;
  if (action === 'no-clear-edge') return c.neutral;
  return c.accent;
}

function Card({ title, children }: { title?: string; children: React.ReactNode }) {
  const { colors } = useTheme();
  return (
    <View style={[styles.card, { borderColor: colors.divider }]}>
      {title ? <Text style={[styles.cardTitle, { color: colors.muted }]}>{title}</Text> : null}
      {children}
    </View>
  );
}

function Row({
  label,
  value,
  color,
  strong,
}: {
  label: string;
  value: string;
  color?: string;
  strong?: boolean;
}) {
  const { colors } = useTheme();
  return (
    <View style={styles.row}>
      <Text style={[styles.rowLabel, { color: colors.muted }]}>{label}</Text>
      <Text
        style={[
          styles.rowValue,
          { color: color ?? colors.text, fontSize: strong ? 15 : 13 },
        ]}
      >
        {value}
      </Text>
    </View>
  );
}

// --- position header -------------------------------------------------------

function PositionCard({ data }: { data: Advice }) {
  const { colors } = useTheme();
  const { t } = useI18n();
  const p = data.position!;
  return (
    <Card title={t('exit.position')}>
      <Text style={[styles.holding, { color: colors.text }]}>
        {p.shares.toLocaleString()} {data.ticker} @ {plain(p.averageCost)}
      </Text>
      <Row label={t('exit.costBasis')} value={plain(p.costBasis)} />
      <Row label={t('exit.value')} value={plain(p.currentValue)} />
      <Row
        label={t('exit.pnl')}
        value={`${money(p.unrealizedPnl)} (${p.unrealizedPnlPct > 0 ? '+' : ''}${p.unrealizedPnlPct.toFixed(2)}%)`}
        color={pnlColor(colors, p.unrealizedPnl)}
        strong
      />
    </Card>
  );
}

// --- the headline verdict --------------------------------------------------

function Verdict({ data }: { data: Advice }) {
  const { colors } = useTheme();
  const { t } = useI18n();
  const action = data.advice?.action ?? data.rules?.final;
  if (!action) return null;
  const tone = actionColor(colors, action);
  const overridden = data.rules?.overridden && data.advice;

  return (
    <View style={[styles.verdict, { backgroundColor: tone + '22' }]}>
      <Text style={[styles.verdictKicker, { color: tone }]}>{t('exit.verdict')}</Text>
      <Text style={[styles.verdictText, { color: tone }]}>{t(`exit.action.${action}`)}</Text>
      {data.advice ? (
        <Text style={[styles.verdictConf, { color: colors.muted }]}>
          {t(`predict.conf.${data.advice.confidence}`)}
          {data.advice.provider ? ` · ${data.advice.provider}` : ''}
        </Text>
      ) : null}
      {/* The model's own call, when the rules moved it. Showing both is the
          honest version: it says a machine disagreed with a machine. */}
      {overridden ? (
        <Text style={[styles.verdictNote, { color: colors.muted }]}>
          {t('exit.overridden', { ai: t(`exit.action.${data.advice!.aiAction}`) })}
        </Text>
      ) : null}
    </View>
  );
}

// --- hold vs sell (§30's regret-minimisation card) -------------------------

function HoldVsSell({ data }: { data: Advice }) {
  const { colors } = useTheme();
  const { t } = useI18n();
  const p = data.position!;
  const hold = data.holdRewardRisk;
  const noisy =
    data.levels?.distance?.supportAtrs != null && data.levels.distance.supportAtrs < 0.5;

  return (
    <Card title={t('exit.holdVsSell')}>
      <Row
        label={t('exit.lockNow')}
        value={money(p.unrealizedPnl)}
        color={pnlColor(colors, p.unrealizedPnl)}
        strong
      />
      {hold ? (
        <>
          <Row
            label={t('exit.upsideTo', { level: plain(hold.target) })}
            value={money(hold.additionalProfit)}
            color={colors.bull}
          />
          <Row
            label={t('exit.givebackTo', { level: plain(hold.support) })}
            value={money(-hold.profitGiveback)}
            color={colors.bear}
          />
          <View style={[styles.ratioRow, { borderTopColor: colors.divider }]}>
            <Text style={[styles.rowLabel, { color: colors.muted }]}>{t('exit.rr')}</Text>
            <Text style={[styles.ratio, { color: colors.text }]}>{hold.ratio.toFixed(2)}</Text>
            <Text style={[styles.ratioLabel, { color: colors.faint }]}>
              {t(`exit.rr.${hold.label}`)}
            </Text>
          </View>
          {/* A floor inside one ordinary day's move makes the ratio above look
              better than it is. Say so where the ratio is, not in a footnote. */}
          {noisy ? (
            <Text style={[styles.caveat, { color: colors.bear }]}>
              {t('exit.noisySupport', {
                atrs: data.levels!.distance.supportAtrs!.toFixed(2),
              })}
            </Text>
          ) : null}
        </>
      ) : (
        <Text style={[styles.caveat, { color: colors.faint }]}>{t('exit.noRr')}</Text>
      )}
      {data.atYourTarget ? (
        <Text style={[styles.yourTarget, { color: colors.muted }]}>
          {t('exit.yourTarget', {
            level: plain(data.atYourTarget.target),
            profit: money(data.atYourTarget.additionalProfit),
            ratio: data.atYourTarget.ratio.toFixed(2),
          })}
        </Text>
      ) : null}
    </Card>
  );
}

// --- what falling costs ----------------------------------------------------

function Giveback({ levels }: { levels: GivebackLevel[] }) {
  const { colors } = useTheme();
  const { t } = useI18n();
  if (!levels.length) return null;
  return (
    <Card title={t('exit.giveback')}>
      {levels.slice(0, 4).map((level) => (
        <View key={level.support} style={styles.giveRow}>
          <Text style={[styles.giveLevel, { color: colors.text }]}>{plain(level.support)}</Text>
          <Text style={[styles.givePct, { color: colors.faint }]}>{level.pctMove.toFixed(1)}%</Text>
          <Text style={[styles.giveBack, { color: colors.bear }]}>{money(-level.giveback)}</Text>
          <Text
            style={[styles.giveKeep, { color: pnlColor(colors, level.remainingPnl) }]}
          >
            {/* Below cost this is a loss, not profit kept — the wording changes
                because calling it "profit remaining" would be false. */}
            {level.belowCostBasis
              ? t('exit.wouldLose', { amount: money(level.remainingPnl) })
              : t('exit.keeps', { amount: money(level.remainingPnl) })}
          </Text>
        </View>
      ))}
    </Card>
  );
}

// --- trimming --------------------------------------------------------------

function PartialSell({ options }: { options: PartialSellOption[] }) {
  const { colors } = useTheme();
  const { t } = useI18n();
  const usable = options.filter((o) => o.possible);
  if (!usable.length) return null;
  return (
    <Card title={t('exit.partial')}>
      {usable.map((o) => (
        <View key={o.pctRequested} style={[styles.partRow, { borderTopColor: colors.divider }]}>
          <Text style={[styles.partPct, { color: colors.text }]}>{o.pctRequested.toFixed(0)}%</Text>
          <Text style={[styles.partShares, { color: colors.muted }]}>
            {t('exit.shares.n', { n: o.sharesSold.toLocaleString() })}
          </Text>
          <Text style={[styles.partMoney, { color: colors.text }]}>{plain(o.proceeds)}</Text>
          <Text style={[styles.partRealized, { color: pnlColor(colors, o.realizedPnl) }]}>
            {money(o.realizedPnl)}
          </Text>
        </View>
      ))}
      <Text style={[styles.partHint, { color: colors.faint }]}>{t('exit.partialHint')}</Text>
    </Card>
  );
}

// --- scenarios -------------------------------------------------------------

function Scenarios({ scenarios }: { scenarios: ExitScenario[] }) {
  const { colors } = useTheme();
  const { t } = useI18n();
  if (!scenarios.length) return null;
  const tone = (name: string) =>
    name === 'bull' ? colors.bull : name === 'bear' ? colors.bear : colors.neutral;

  return (
    <Card title={t('exit.scenarios')}>
      {scenarios.map((s) => (
        <View key={s.name} style={[styles.scenario, { borderTopColor: colors.divider }]}>
          <View style={styles.scenarioHead}>
            <Text style={[styles.scenarioName, { color: tone(s.name) }]}>
              {t(`exit.scenario.${s.name}`)}
            </Text>
            <Text style={[styles.scenarioProb, { color: colors.text }]}>{s.probability}%</Text>
            <Text style={[styles.scenarioRange, { color: colors.muted }]}>
              {plain(s.priceRange.low)} – {plain(s.priceRange.high)}
            </Text>
          </View>
          <Text style={[styles.scenarioPnl, { color: colors.muted }]}>
            {t('exit.fromHere')}{' '}
            <Text style={{ color: pnlColor(colors, s.additionalPnlFromCurrentRange.low) }}>
              {money(s.additionalPnlFromCurrentRange.low)}
            </Text>{' '}
            →{' '}
            <Text style={{ color: pnlColor(colors, s.additionalPnlFromCurrentRange.high) }}>
              {money(s.additionalPnlFromCurrentRange.high)}
            </Text>
          </Text>
          {s.trigger ? (
            <Text style={[styles.scenarioTrigger, { color: colors.faint }]}>{s.trigger}</Text>
          ) : null}
        </View>
      ))}
    </Card>
  );
}

// --- the three plans -------------------------------------------------------

function Plans({ plans }: { plans: ExitPlan[] }) {
  const { colors } = useTheme();
  const { t } = useI18n();
  if (!plans.length) return null;
  return (
    <Card title={t('exit.plans')}>
      {plans.map((plan) => (
        <View key={plan.name} style={[styles.plan, { borderTopColor: colors.divider }]}>
          <View style={styles.planHead}>
            <Text style={[styles.planName, { color: colors.text }]}>
              {t(`exit.plan.${plan.name}`)}
            </Text>
            <Text style={[styles.planAction, { color: actionColor(colors, plan.action) }]}>
              {plan.sellPctNow
                ? t('exit.sellPct', { pct: plan.sellPctNow })
                : t('exit.holdAll')}
            </Text>
          </View>
          {plan.explanation ? (
            <Text style={[styles.planWhy, { color: colors.muted }]}>{plan.explanation}</Text>
          ) : null}
          <View style={styles.planLevels}>
            {plan.stop != null ? (
              <Text style={[styles.planLevel, { color: colors.faint }]}>
                {t('exit.stop')} {plain(plan.stop)}
              </Text>
            ) : null}
            {plan.firstTarget != null ? (
              <Text style={[styles.planLevel, { color: colors.faint }]}>
                {t('exit.target')} {plain(plan.firstTarget)}
              </Text>
            ) : null}
            {plan.invalidation != null ? (
              <Text style={[styles.planLevel, { color: colors.faint }]}>
                {t('exit.invalidation')} {plain(plan.invalidation)}
              </Text>
            ) : null}
          </View>
        </View>
      ))}
    </Card>
  );
}

// --- why -------------------------------------------------------------------

function Reasons({ data }: { data: Advice }) {
  const { colors } = useTheme();
  const { t } = useI18n();
  const advice = data.advice;
  const findings = data.rules?.findings ?? [];
  if (!advice && !findings.length) return null;

  return (
    <Card title={t('exit.why')}>
      {advice?.thesis ? (
        <Text style={[styles.thesis, { color: colors.text }]}>{advice.thesis}</Text>
      ) : null}
      {advice?.reasonsToHold?.map((r, i) => (
        <Text key={`h${i}`} style={[styles.reason, { color: colors.bull }]}>
          + {r}
        </Text>
      ))}
      {advice?.reasonsToSell?.map((r, i) => (
        <Text key={`s${i}`} style={[styles.reason, { color: colors.bear }]}>
          − {r}
        </Text>
      ))}
      {/* Deterministic findings, phrased here from codes + numbers. */}
      {findings.map((f, i) => (
        <Text key={`r${i}`} style={[styles.finding, { color: colors.muted }]}>
          ▪ {t(`exit.rule.${f.code}`, f.params as Record<string, string | number>)}
        </Text>
      ))}
      {advice?.warnings?.map((w, i) => (
        <Text key={`w${i}`} style={[styles.finding, { color: colors.bear }]}>
          ! {w}
        </Text>
      ))}
    </Card>
  );
}

// --- context ---------------------------------------------------------------

function Context({ data }: { data: Advice }) {
  const { colors } = useTheme();
  const { t } = useI18n();
  const tech = data.technicals;
  if (!tech) return null;
  const rsi = tech.indicators?.rsi14 as number | null;
  const market = tech.market;

  return (
    <Card title={t('exit.context')}>
      <View style={styles.chips}>
        <View style={[styles.chip, { borderColor: colors.divider }]}>
          <Text style={[styles.chipText, { color: colors.muted }]}>
            {t('predict.trend')} {tech.trend?.toUpperCase()}
          </Text>
        </View>
        {rsi != null ? (
          <View style={[styles.chip, { borderColor: colors.divider }]}>
            <Text style={[styles.chipText, { color: colors.muted }]}>RSI {rsi.toFixed(0)}</Text>
          </View>
        ) : null}
        {data.extension?.aboveSma20Atrs != null ? (
          <View style={[styles.chip, { borderColor: colors.divider }]}>
            <Text style={[styles.chipText, { color: colors.muted }]}>
              {t('exit.vsSma20', { atrs: data.extension.aboveSma20Atrs.toFixed(1) })}
            </Text>
          </View>
        ) : null}
        {data.relativeVolume != null ? (
          <View style={[styles.chip, { borderColor: colors.divider }]}>
            <Text style={[styles.chipText, { color: colors.muted }]}>
              {t('exit.relVol', { x: data.relativeVolume.toFixed(2) })}
            </Text>
          </View>
        ) : null}
        {data.earningsInDays != null && data.earningsInDays >= 0 ? (
          <View style={[styles.chip, { borderColor: colors.divider }]}>
            <Text style={[styles.chipText, { color: colors.muted }]}>
              {t('exit.earningsIn', { days: data.earningsInDays })}
            </Text>
          </View>
        ) : null}
      </View>
      {market?.marketTrend ? (
        <Text style={[styles.market, { color: colors.muted }]}>
          {t('exit.market', {
            trend: market.marketTrend,
            vix: market.vix != null ? market.vix.toFixed(1) : '—',
            regime: market.vixRegime ?? '—',
          })}
          {market.relative20d != null
            ? ` · ${t('exit.vsMarket', { pts: market.relative20d.toFixed(1) })}`
            : ''}
        </Text>
      ) : null}
    </Card>
  );
}

// --- the whole thing -------------------------------------------------------

export function ExitAdviceView({ data }: { data: Advice }) {
  const { colors } = useTheme();
  const { t } = useI18n();
  if (!data.position) return null;

  return (
    <View style={styles.wrap}>
      <View style={styles.head}>
        <Text style={[styles.ticker, { color: colors.text }]}>{data.ticker}</Text>
        <Text style={[styles.name, { color: colors.muted }]}>{data.name}</Text>
        {data.price ? (
          <Text style={[styles.price, { color: colors.text }]}>
            ${data.price}{' '}
            <Text style={{ color: colors.faint, fontSize: 10 }}>{data.priceFresh}</Text>
          </Text>
        ) : null}
      </View>

      {/* §28 RULE-EXIT-001: a stale quote can't support a sell decision, so it
          is said at the top rather than buried with the other findings. */}
      {data.rules?.refreshRequired ? (
        <View style={[styles.refresh, { borderColor: colors.bear }]}>
          <Text style={[styles.refreshText, { color: colors.bear }]}>{t('exit.refresh')}</Text>
        </View>
      ) : null}

      <Verdict data={data} />
      <PositionCard data={data} />
      <HoldVsSell data={data} />
      <Reasons data={data} />
      <Giveback levels={data.giveback ?? []} />
      {data.allowPartialSell ? <PartialSell options={data.partialSell ?? []} /> : null}
      <Scenarios scenarios={data.scenarios ?? []} />
      <Plans plans={data.plans ?? []} />
      <Context data={data} />

      <Text style={[styles.disclaimer, { color: colors.faint }]}>{data.disclaimer}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 12 },
  head: {},
  ticker: { fontSize: 26, fontWeight: '900', letterSpacing: -0.5 },
  name: { fontSize: 12, marginTop: 1 },
  price: { fontSize: 15, fontWeight: '800', marginTop: 6, fontVariant: ['tabular-nums'] },
  refresh: { borderWidth: 1, borderStyle: 'dashed', padding: 10 },
  refreshText: { fontSize: 11, fontWeight: '800', lineHeight: 16 },
  verdict: { paddingVertical: 14, paddingHorizontal: 16 },
  verdictKicker: { fontSize: 10, fontWeight: '900', letterSpacing: 1 },
  verdictText: { fontSize: 28, fontWeight: '900', letterSpacing: -0.8, marginTop: 2 },
  verdictConf: { fontSize: 10, fontWeight: '700', marginTop: 2, textTransform: 'uppercase' },
  verdictNote: { fontSize: 11, marginTop: 6, lineHeight: 16 },
  card: { borderWidth: 1, padding: 14, gap: 6 },
  cardTitle: { fontSize: 10, fontWeight: '900', letterSpacing: 1, marginBottom: 2 },
  holding: { fontSize: 15, fontWeight: '800', marginBottom: 4 },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  rowLabel: { flex: 1, fontSize: 12 },
  rowValue: { fontWeight: '800', fontVariant: ['tabular-nums'] },
  ratioRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderTopWidth: 1,
    paddingTop: 8,
    marginTop: 4,
  },
  ratio: { fontSize: 20, fontWeight: '900', fontVariant: ['tabular-nums'] },
  ratioLabel: { fontSize: 9, fontWeight: '900', letterSpacing: 0.6 },
  caveat: { fontSize: 11, lineHeight: 16, marginTop: 4 },
  yourTarget: { fontSize: 11, lineHeight: 16, marginTop: 6 },
  giveRow: { flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  giveLevel: { fontSize: 13, fontWeight: '800', fontVariant: ['tabular-nums'], width: 74 },
  givePct: { fontSize: 10, fontWeight: '700', width: 46 },
  giveBack: { fontSize: 12, fontWeight: '800', fontVariant: ['tabular-nums'] },
  giveKeep: { flexBasis: '100%', fontSize: 11, marginTop: -2, marginBottom: 2 },
  partRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderTopWidth: 1,
    paddingVertical: 7,
  },
  partPct: { fontSize: 13, fontWeight: '900', width: 40 },
  partShares: { flex: 1, fontSize: 11 },
  partMoney: { fontSize: 12, fontWeight: '800', fontVariant: ['tabular-nums'] },
  partRealized: { fontSize: 12, fontWeight: '800', fontVariant: ['tabular-nums'], width: 84, textAlign: 'right' },
  partHint: { fontSize: 10, lineHeight: 15, marginTop: 6 },
  scenario: { borderTopWidth: 1, paddingTop: 8, marginTop: 2, gap: 3 },
  scenarioHead: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  scenarioName: { fontSize: 11, fontWeight: '900', letterSpacing: 0.6, width: 52 },
  scenarioProb: { fontSize: 13, fontWeight: '900', fontVariant: ['tabular-nums'], width: 40 },
  scenarioRange: { flex: 1, fontSize: 11, fontVariant: ['tabular-nums'], textAlign: 'right' },
  scenarioPnl: { fontSize: 11, lineHeight: 16 },
  scenarioTrigger: { fontSize: 10, lineHeight: 15 },
  plan: { borderTopWidth: 1, paddingTop: 8, marginTop: 2, gap: 3 },
  planHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  planName: { fontSize: 12, fontWeight: '900', letterSpacing: 0.4 },
  planAction: { fontSize: 12, fontWeight: '900' },
  planWhy: { fontSize: 11.5, lineHeight: 17 },
  planLevels: { flexDirection: 'row', gap: 12, flexWrap: 'wrap' },
  planLevel: { fontSize: 10, fontWeight: '700', fontVariant: ['tabular-nums'] },
  thesis: { fontSize: 13.5, lineHeight: 20, fontWeight: '600', marginBottom: 4 },
  reason: { fontSize: 12, lineHeight: 18 },
  finding: { fontSize: 11.5, lineHeight: 17 },
  chips: { flexDirection: 'row', gap: 6, flexWrap: 'wrap' },
  chip: { borderWidth: 1, paddingHorizontal: 8, paddingVertical: 3 },
  chipText: { fontSize: 10, fontWeight: '800' },
  market: { fontSize: 11, lineHeight: 16, marginTop: 6 },
  disclaimer: { fontSize: 10, fontWeight: '600', marginTop: 4 },
});
