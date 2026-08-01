/**
 * A5.1 WorkspaceContextAdapter — Workspace State → Julia ContextRequest
 *
 * Converts AnalystWorkspace ThemeEntry/WatchGroup cognitive state
 * into structured ContextRequests that Julia Agent can process.
 *
 * Contract: Analyst_Workspace_Context_Binding_v1.0.md (FROZEN)
 */

// ── Types ──

interface ThemeEntry {
  subject_id: string;
  subject_name: string;
  attention_level: string;
  attention_score: number;
  attention_reasons: string[];
  stage_judgement: string;
  yesterday_view: string;
  today_actual: string;
  intraday_understanding: string;
  trader_sentiment: string;
  index_resonance: string;
  tomorrow_view: string;
  analyst_notes: string;
  event_stimuli: string[];
  old_leaders: string;
  trading_style: string;
  long_identifiability: number;
  short_identifiability: number;
  is_ai_draft: boolean;
  analyst_reviewed: boolean;
  field_overrides: Record<string, { ai_value: string; analyst_value: string; reason: string }>;
}

interface WatchGroup {
  id: string;
  name: string;
  subject_ids: string[];
  color: string;
  stage_judgement: string;
  yesterday_view: string;
  today_actual: string;
  analyst_notes: string;
  trading_style: string;
  event_stimuli: string[];
  old_leaders: string;
  field_overrides: Record<string, { ai_value: string; analyst_value: string; reason: string }>;
}

export interface ContextRequest {
  action: "why" | "risk" | "compare";
  object_type: "theme" | "group";
  object_id: string;
  object_name: string;
  workspace_snapshot: {
    stage_judgement: string;
    attention_level?: string;
    yesterday_view: string;
    today_actual: string;
    intraday_understanding?: string;
    trader_sentiment?: string;
    index_resonance?: string;
    event_stimuli: string[];
    analyst_notes: string;
    old_leaders?: string;
    trading_style?: string;
    long_identifiability?: number;
    short_identifiability?: number;
  };
  field_overrides_summary: Array<{
    field: string;
    ai_value: string;
    analyst_value: string;
  }>;
  source: "analyst_workspace";
}

export interface JuliaResponse {
  intent: "deep_dive" | "morning_brief" | "research" | "unknown";
  text: string;
  evidence_refs: string[];
  rendered_evidence_links: string[];
  confidence: number;
  limitations: string[];
  status: "shadow";
}

// ── Adapter Functions ──

export function themeToContextRequest(
  theme: ThemeEntry,
  action: "why" | "risk" | "compare",
): ContextRequest {
  return {
    action,
    object_type: "theme",
    object_id: theme.subject_id,
    object_name: theme.subject_name,
    workspace_snapshot: {
      stage_judgement: theme.stage_judgement,
      attention_level: theme.attention_level,
      yesterday_view: theme.yesterday_view,
      today_actual: theme.today_actual,
      intraday_understanding: theme.intraday_understanding,
      trader_sentiment: theme.trader_sentiment,
      index_resonance: theme.index_resonance,
      event_stimuli: theme.event_stimuli.filter(s => s.trim()),
      analyst_notes: theme.analyst_notes,
      old_leaders: theme.old_leaders,
      trading_style: theme.trading_style,
      long_identifiability: theme.long_identifiability,
      short_identifiability: theme.short_identifiability,
    },
    field_overrides_summary: Object.entries(theme.field_overrides || {}).map(
      ([field, override]) => ({
        field,
        ai_value: override.ai_value,
        analyst_value: override.analyst_value,
      }),
    ),
    source: "analyst_workspace",
  };
}

export function groupToContextRequest(
  group: WatchGroup,
  action: "why" | "risk" | "compare",
): ContextRequest {
  return {
    action,
    object_type: "group",
    object_id: group.id,
    object_name: group.name,
    workspace_snapshot: {
      stage_judgement: group.stage_judgement,
      yesterday_view: group.yesterday_view,
      today_actual: group.today_actual,
      event_stimuli: group.event_stimuli.filter(s => s.trim()),
      analyst_notes: group.analyst_notes,
      old_leaders: group.old_leaders,
      trading_style: group.trading_style,
    },
    field_overrides_summary: Object.entries(group.field_overrides || {}).map(
      ([field, override]) => ({
        field,
        ai_value: override.ai_value,
        analyst_value: override.analyst_value,
      }),
    ),
    source: "analyst_workspace",
  };
}

/**
 * Convert a ContextRequest into the natural-language question
 * that the Julia Agent interaction layer expects.
 */
export function contextRequestToQuestion(request: ContextRequest): string {
  const name = request.object_name || "此题材";

  switch (request.action) {
    case "why":
      return `为什么关注${name}？当前阶段是${request.workspace_snapshot.stage_judgement || "未知"}，依据是什么事件？`;

    case "risk":
      return `${name}目前的风险在哪里？交易情绪是${request.workspace_snapshot.trader_sentiment || "未知"}，指数共振${request.workspace_snapshot.index_resonance || "未知"}，什么情况会破坏逻辑？`;

    case "compare":
      return `对比${name}的昨天判断和今天实际变化。昨天看法：${request.workspace_snapshot.yesterday_view || "无"}，今天实际：${request.workspace_snapshot.today_actual || "无"}`;

    default:
      return `分析${name}。`;
  }
}
