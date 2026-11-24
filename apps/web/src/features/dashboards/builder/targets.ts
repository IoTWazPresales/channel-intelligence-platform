/**
 * Personal KPI target status (Dashboard V2 s.4 "Personal target tiles", s.6).
 *
 * A target belongs to one KPI widget and is measured over that widget's own window, so the
 * actual value is the widget's existing answer. Nothing here invents data or defaults: a widget
 * without `display.target` has no target, and a missing actual has no status.
 */
import type { WidgetDisplay } from './types';

export type WidgetTarget = NonNullable<WidgetDisplay['target']>;
export type TargetStatus = 'on_track' | 'at_risk' | 'behind';

export type TargetProgress = {
  status: TargetStatus;
  /** actual / target for "at least" targets with a positive target; otherwise null (not meaningful). */
  attainment: number | null;
  /** actual - target: positive is above target, negative is below. */
  gap: number;
};

export const TARGET_STATUS_LABEL: Record<TargetStatus, string> = {
  on_track: 'On track',
  at_risk: 'At risk',
  behind: 'Behind',
};

export function targetProgress(actual: number | null | undefined, target: WidgetTarget | undefined): TargetProgress | null {
  if (!target || actual == null || !Number.isFinite(actual) || !Number.isFinite(target.value)) return null;
  const margin = target.risk_margin != null && target.risk_margin > 0 ? target.risk_margin : 0;
  const gap = actual - target.value;
  let status: TargetStatus;
  if (target.direction === 'at_most') {
    status = actual <= target.value ? 'on_track' : actual <= target.value + margin ? 'at_risk' : 'behind';
  } else {
    status = actual >= target.value ? 'on_track' : actual >= target.value - margin ? 'at_risk' : 'behind';
  }
  const attainment = target.direction === 'at_least' && target.value > 0 ? actual / target.value : null;
  return { status, attainment, gap };
}

/** Plain-language target line, e.g. "Target ≥ 30,000 · 83% · 5,140 short". */
export function targetLine(p: TargetProgress, target: WidgetTarget, fmt: (n: number) => string): string {
  const op = target.direction === 'at_most' ? '≤' : '≥';
  const parts = [`Target ${op} ${fmt(target.value)}`];
  if (p.attainment != null) parts.push(`${Math.round(p.attainment * 100)}%`);
  if (p.gap !== 0) {
    const under = p.gap < 0;
    const good = target.direction === 'at_most' ? under : !under;
    parts.push(`${fmt(Math.abs(p.gap))} ${good ? 'headroom' : under ? 'short' : 'over'}`);
  }
  return parts.join(' · ');
}