import React, { useState, useEffect, useCallback } from "react";
import { EmotionDashboard } from "./EmotionDashboard";
import { ReviewDocumentSections } from "../review-document/ReviewDocumentSections";

// ── Types ──

interface StockEntry {
  stock_code: string;
  stock_name: string;
  role: string;
  reasons: string[];
  ai_recommended: boolean;
  analyst_confirmed: boolean;
  analyst_modified: boolean;
}

interface ThemeEntry {
  subject_id: string;
  subject_name: string;
  attention_level: string;
  attention_score: number;
  attention_reasons: string[];
  ai_recommended: boolean;
  analyst_added: boolean;
  trading_style: string;
  long_identifiability: number;
  short_identifiability: number;
  old_leaders: string;
  event_stimuli: string[];
  yesterday_view: string;
  today_actual: string;
  stage_judgement: string;
  intraday_understanding: string;
  trader_sentiment: string;
  index_resonance: string;
  tomorrow_view: string;
  analyst_notes: string;
  is_ai_draft: boolean;
  analyst_reviewed: boolean;
  field_overrides: Record<string, { ai_value: string; analyst_value: string; reason: string }>;
  leaders: StockEntry[];
  bull_pool: StockEntry[];
  bear_pool: StockEntry[];
}

interface WatchGroup {
  id: string;
  name: string;
  subject_ids: string[];
  color: string;
  // Group-level cognition fields — these belong to the observation direction
  trading_style: string;
  long_identifiability: number;
  short_identifiability: number;
  old_leaders: string;
  event_stimuli: string[];
  yesterday_view: string;
  today_actual: string;
  stage_judgement: string;
  intraday_understanding: string;
  trader_sentiment: string;
  index_resonance: string;
  tomorrow_view: string;
  analyst_notes: string;
  // Group-level stock pools
  leaders: StockEntry[];
  bull_pool: StockEntry[];
  bear_pool: StockEntry[];
  field_overrides: Record<string, { ai_value: string; analyst_value: string; reason: string }>;
}

interface Workspace {
  trade_date: string;
  is_ai_draft: boolean;
  analyst_finalized: boolean;
  themes: ThemeEntry[];
  watch_groups: WatchGroup[];
  override_count: number;
  review_document?: Record<string, any> | null;
}

function newWatchGroup(color: string): WatchGroup {
  return {
    id: `group_${Date.now()}`, name: "新观察方向", subject_ids: [], color,
    trading_style: "", long_identifiability: 0.5, short_identifiability: 0.3,
    old_leaders: "", event_stimuli: [""],
    yesterday_view: "", today_actual: "", stage_judgement: "",
    intraday_understanding: "", trader_sentiment: "", index_resonance: "",
    tomorrow_view: "", analyst_notes: "", field_overrides: {},
    leaders: [], bull_pool: [], bear_pool: [],
  };
}

// ── Constants ──

const LEVEL_STARS: Record<string, string> = { CRITICAL: "★★★★★", HIGH: "★★★★☆", MEDIUM: "★★★☆☆", LOW: "★★☆☆☆" };
const LEVEL_COLORS: Record<string, string> = { CRITICAL: "#e53e3e", HIGH: "#dd6b20", MEDIUM: "#d69e2e", LOW: "#38a169" };
const STOCK_ROLES = ["龙头", "潜在龙头", "中军", "助攻", "跟风", "补涨", "穿越龙"];
const TRADING_STYLES = ["机构趋势", "游资接力", "机游合力", "量化主导", "混合轮动", "无明确风格"];

// ── Helpers ──

function newTheme(name = "", id = ""): ThemeEntry {
  return {
    subject_id: id || `manual_${Date.now()}`,
    subject_name: name,
    attention_level: "MEDIUM", attention_score: 50, attention_reasons: [],
    ai_recommended: false, analyst_added: true, is_ai_draft: false, analyst_reviewed: false,
    trading_style: "", long_identifiability: 0.5, short_identifiability: 0.3,
    old_leaders: "", event_stimuli: [""],
    yesterday_view: "", today_actual: "", stage_judgement: "",
    intraday_understanding: "", trader_sentiment: "", index_resonance: "",
    tomorrow_view: "", analyst_notes: "", field_overrides: {},
    leaders: [], bull_pool: [], bear_pool: [],
  };
}

function newStock(): StockEntry {
  return {
    stock_code: "", stock_name: "", role: "跟风",
    reasons: [""], ai_recommended: false, analyst_confirmed: false, analyst_modified: true,
  };
}

// ── Sub-components ──

function ThemeWatchList({
  themes, selectedIdx, selectedGroupId, onSelect, onSelectGroup, onAdd, onDelete, onLevelChange,
  watchGroups, onAddGroup, onUpdateGroup, onDeleteGroup, onAddThemeToGroup,
  allThemes,
}: {
  themes: ThemeEntry[]; selectedIdx: number; selectedGroupId: string | null;
  onSelect: (i: number) => void; onSelectGroup: (id: string | null) => void;
  onAdd: () => void; onDelete: (i: number) => void; onLevelChange: (i: number, level: string) => void;
  watchGroups: WatchGroup[]; onAddGroup: () => void; onUpdateGroup: (g: WatchGroup) => void;
  onDeleteGroup: (id: string) => void; onAddThemeToGroup: (groupId: string, subjectId: string) => void;
  allThemes: ThemeEntry[];
}) {
  const [editingGroup, setEditingGroup] = useState<string | null>(null);
  const [showIgnored, setShowIgnored] = useState(false);

  const GROUP_COLORS = ["#e53e3e", "#3182ce", "#38a169", "#dd6b20", "#805ad5", "#d69e2e"];

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 12px", borderBottom: "1px solid #243040" }}>
        <strong style={{ fontSize: 14 }}>观察方向</strong>
        <button onClick={onAddGroup}
          style={{ fontSize: 11, padding: "2px 8px", background: "#38a169", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer" }}>
          + 新增方向
        </button>
      </div>

      {/* Watch Groups */}
      <div style={{ padding: "4px 0", borderBottom: "1px solid #243040" }}>
        {watchGroups.map((g, gi) => (
          <div key={g.id} style={{ padding: "4px 12px", borderBottom: "1px solid #243040" }}>
            {editingGroup === g.id ? (
              <input autoFocus value={g.name} onChange={(e) => onUpdateGroup({ ...g, name: e.target.value })}
                onBlur={() => setEditingGroup(null)} onKeyDown={(e) => { if (e.key === "Enter") { setEditingGroup(null); e.preventDefault(); } }}
                style={{ width: "100%", padding: "4px 6px", fontSize: 13, fontWeight: 600, borderRadius: 3, border: `2px solid ${g.color}`, background: g.color + "10", outline: "none" }} />
            ) : (
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span onClick={() => onSelectGroup(g.id)}
                  onDoubleClick={() => setEditingGroup(g.id)}
                  title="双击修改名称"
                  style={{ fontSize: 13, fontWeight: 600, cursor: "pointer", color: g.color, padding: "2px 0", background: selectedGroupId === g.id ? g.color + "20" : "transparent", borderRadius: 3, paddingLeft: 4, paddingRight: 4 }}>
                  {g.name} ({g.subject_ids.length})
                </span>
                <div style={{ display: "flex", gap: 2 }}>
                  <select size={1}
                    onChange={(e) => { if (e.target.value) onAddThemeToGroup(g.id, e.target.value); e.target.value = ""; }}
                    style={{ fontSize: 10, maxWidth: 80, padding: 0 }}>
                    <option value="">+</option>
                    {allThemes.filter(t => !g.subject_ids.includes(t.subject_id) && t.subject_name !== "(新题材)").map(t => (
                      <option key={t.subject_id} value={t.subject_id}>{t.subject_name.slice(0, 10)}</option>
                    ))}
                  </select>
                  <button onClick={() => onDeleteGroup(g.id)}
                    style={{ fontSize: 10, color: "#5a7a8a", background: "none", border: "none", cursor: "pointer" }}>✕</button>
                </div>
              </div>
            )}
            {/* Show themes in this group */}
            {g.subject_ids.map(sid => {
              const t = allThemes.find(x => x.subject_id === sid);
              if (!t) return null;
              return (
                <div key={sid} onClick={() => { const idx = themes.findIndex(x => x.subject_id === sid); if (idx >= 0) onSelect(idx); }}
                  style={{ fontSize: 11, marginLeft: 12, padding: "2px 6px", cursor: "pointer", color: "#8ddcff" }}>
                  · {t.subject_name}
                </div>
              );
            })}
          </div>
        ))}
      </div>

      {/* Ungrouped themes header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 12px", borderBottom: "1px solid #243040" }}>
        <strong style={{ fontSize: 14 }}>重点题材</strong>
        <div style={{ display: "flex", gap: 4 }}>
          <label style={{ fontSize: 10, cursor: "pointer", display: "flex", alignItems: "center", gap: 2 }}>
            <input type="checkbox" checked={showIgnored} onChange={(e) => setShowIgnored(e.target.checked)} /> 显示全部
          </label>
          <button onClick={onAdd}
            style={{ fontSize: 11, padding: "2px 8px", background: "#3182ce", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer" }}>
            + 新增
          </button>
        </div>
      </div>

      {/* Theme list — only CRITICAL/HIGH by default */}
      <div style={{ flex: 1, overflow: "auto" }}>
        {themes.filter(t => showIgnored || t.attention_level === "CRITICAL" || t.attention_level === "HIGH" || t.analyst_added).map((t, i) => {
          const realIdx = themes.indexOf(t);
          const inGroup = watchGroups.find(g => g.subject_ids.includes(t.subject_id));
          return (
          <div key={t.subject_id}
            onClick={() => onSelect(realIdx)}
            style={{
              padding: "8px 12px", cursor: "pointer", borderBottom: "1px solid #edf2f7",
              background: realIdx === selectedIdx ? "#1a2a3a" : inGroup ? inGroup.color + "10" : "transparent",
              borderLeft: realIdx === selectedIdx ? "3px solid #66d9ef" : inGroup ? `3px solid ${inGroup.color}` : "3px solid transparent",
            }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: 13, fontWeight: realIdx === selectedIdx ? 700 : 400 }}>
                {t.analyst_added ? "✎ " : ""}{t.subject_name || "(新题材)"}
                {inGroup && <span style={{ marginLeft: 4, fontSize: 9, color: inGroup.color, background: inGroup.color + "20", padding: "1px 4px", borderRadius: 3 }}>{inGroup.name}</span>}
              </span>
              <span style={{ fontSize: 11, color: LEVEL_COLORS[t.attention_level] || "#a0aec0" }}>
                {LEVEL_STARS[t.attention_level] || "★★★☆☆"}
              </span>
            </div>
            <div style={{ display: "flex", gap: 4, marginTop: 3 }}>
              {(["CRITICAL", "HIGH", "MEDIUM", "LOW"] as const).map((lvl) => (
                <span key={lvl}
                  onClick={(e) => { e.stopPropagation(); onLevelChange(realIdx, lvl); }}
                  style={{
                    fontSize: 10, cursor: "pointer", padding: "1px 4px", borderRadius: 3,
                    background: t.attention_level === lvl ? LEVEL_COLORS[lvl] + "30" : "transparent",
                    border: `1px solid ${t.attention_level === lvl ? LEVEL_COLORS[lvl] : "#e2e8f0"}`,
                  }}>
                  {lvl[0]}
                </span>
              ))}
              <span style={{ flex: 1 }} />
              <button onClick={(e) => { e.stopPropagation(); onDelete(realIdx); }}
                style={{ fontSize: 10, color: "#e53e3e", background: "none", border: "none", cursor: "pointer" }}>
                ✕
              </button>
            </div>
          </div>
        )})}
      </div>
    </div>
  );
}

function CognitionEditor({
  theme, onChange,
}: {
  theme: ThemeEntry; onChange: (t: ThemeEntry) => void;
}) {
  const update = (field: string, value: any) => {
    const prev = (theme as any)[field];
    const newTheme = { ...theme, [field]: value, is_ai_draft: false };
    if (prev !== value && theme.is_ai_draft) {
      newTheme.field_overrides = {
        ...theme.field_overrides,
        [field]: { ai_value: String(prev || ""), analyst_value: String(value), reason: "" },
      };
    }
    onChange(newTheme);
  };

  const fieldStatus = (field: string): string => {
    const ov = theme.field_overrides[field];
    return ov ? (ov.analyst_value !== ov.ai_value ? "modified" : "confirmed") : theme.is_ai_draft ? "ai" : "analyst";
  };

  const s = fieldStatus;
  const statusColor = (f: string) =>
    s(f) === "ai" ? "#a0aec0" : s(f) === "modified" ? "#d69e2e" : s(f) === "confirmed" ? "#38a169" : "#1a202c";

  const TextField = ({ label, field, rows = 2 }: { label: string; field: string; rows?: number }) => (
    <div style={{ marginBottom: 10 }}>
      <label style={{ fontSize: 12, fontWeight: 600, color: "#8ddcff", display: "block", marginBottom: 3 }}>
        {label} <span style={{ color: statusColor(field), fontSize: 10 }}>{s(field) === "ai" ? "(AI)" : s(field) === "modified" ? "(已修改)" : ""}</span>
      </label>
      {rows > 1 ? (
        <textarea value={(theme as any)[field] || ""} onChange={(e) => update(field, e.target.value)} rows={rows}
          style={{ width: "100%", padding: 6, fontSize: 13, borderRadius: 4, border: `1px solid ${statusColor(field)}`, resize: "vertical", background: "#1a1a1a", color: "#f5f5f5" }} />
      ) : (
        <input value={(theme as any)[field] || ""} onChange={(e) => update(field, e.target.value)}
          style={{ width: "100%", padding: 6, fontSize: 13, borderRadius: 4, border: `1px solid ${statusColor(field)}`, background: "#1a1a1a", color: "#f5f5f5" }} />
      )}
    </div>
  );

  return (
    <div style={{ padding: 12, overflow: "auto", height: "100%" }}>
      {/* Subject name */}
      <TextField label="题材名称" field="subject_name" rows={1} />

      {/* Style + identifiability row */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginBottom: 10 }}>
        <div>
          <label style={{ fontSize: 12, fontWeight: 600, color: "#8ddcff", display: "block", marginBottom: 3 }}>炒作风格</label>
          <select value={theme.trading_style || ""} onChange={(e) => update("trading_style", e.target.value)}
            style={{ width: "100%", padding: 6, fontSize: 13, borderRadius: 4, border: `1px solid ${statusColor("trading_style")}` }}>
            <option value="">—</option>
            {TRADING_STYLES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div>
          <label style={{ fontSize: 12, fontWeight: 600, color: "#8ddcff", display: "block", marginBottom: 3 }}>
            多头辨识度 {theme.long_identifiability.toFixed(1)}
          </label>
          <input type="range" min="0" max="1" step="0.1" value={theme.long_identifiability}
            onChange={(e) => update("long_identifiability", parseFloat(e.target.value))}
            style={{ width: "100%" }} />
        </div>
        <div>
          <label style={{ fontSize: 12, fontWeight: 600, color: "#8ddcff", display: "block", marginBottom: 3 }}>
            空头辨识度 {theme.short_identifiability.toFixed(1)}
          </label>
          <input type="range" min="0" max="1" step="0.1" value={theme.short_identifiability}
            onChange={(e) => update("short_identifiability", parseFloat(e.target.value))}
            style={{ width: "100%" }} />
        </div>
      </div>

      <TextField label="老龙头 / 题材锚定" field="old_leaders" rows={1} />

      {/* Events */}
      <div style={{ marginBottom: 10 }}>
        <label style={{ fontSize: 12, fontWeight: 600, color: "#8ddcff", display: "block", marginBottom: 3 }}>事件刺激</label>
        {(theme.event_stimuli.length === 0 ? [""] : theme.event_stimuli).map((ev: string, i: number) => (
          <div key={i} style={{ display: "flex", gap: 4, marginBottom: 4 }}>
            <input value={ev} onChange={(e) => {
              const arr = [...theme.event_stimuli];
              arr[i] = e.target.value;
              update("event_stimuli", arr);
            }} placeholder="事件描述"
              style={{ flex: 1, padding: 4, fontSize: 13, borderRadius: 4, border: "1px solid #243040" }} />
            <button onClick={() => update("event_stimuli", theme.event_stimuli.filter((_: any, j: number) => j !== i))}
              style={{ fontSize: 12, color: "#e53e3e", background: "none", border: "none", cursor: "pointer" }}>✕</button>
          </div>
        ))}
        <button onClick={() => update("event_stimuli", [...theme.event_stimuli, ""])}
          style={{ fontSize: 11, color: "#3182ce", background: "none", border: "none", cursor: "pointer" }}>+ 添加事件</button>
      </div>

      <TextField label="昨日思路" field="yesterday_view" rows={2} />
      <TextField label="今日实际" field="today_actual" rows={2} />
      <TextField label="阶段研判" field="stage_judgement" rows={2} />
      <TextField label="日内理解" field="intraday_understanding" rows={2} />
      <TextField label="交易者心态" field="trader_sentiment" rows={1} />
      <TextField label="与指数共振" field="index_resonance" rows={1} />
      <TextField label="隔日思考" field="tomorrow_view" rows={2} />
      <TextField label="分析师备注" field="analyst_notes" rows={3} />
    </div>
  );
}

function StockPoolEditor({
  theme, onChange,
}: {
  theme: ThemeEntry; onChange: (t: ThemeEntry) => void;
}) {
  const [localLeaders, setLocalLeaders] = useState<StockEntry[]>([]);
  const [localBull, setLocalBull] = useState<StockEntry[]>([]);
  const [localBear, setLocalBear] = useState<StockEntry[]>([]);
  const [init, setInit] = useState(false);
  if (!init) { setLocalLeaders(theme.leaders||[]); setLocalBull(theme.bull_pool||[]); setLocalBear(theme.bear_pool||[]); setInit(true); }

  const sync = (leaders: StockEntry[], bull: StockEntry[], bear: StockEntry[]) => {
    onChange({ ...theme, leaders, bull_pool: bull, bear_pool: bear, is_ai_draft: false });
  };

  return (
    <div style={{ padding: 12, overflow: "auto", height: "100%" }}>
      <PoolSection title="龙头 / 潜在龙头 / 中军" color="#e53e3e" stocks={localLeaders} setStocks={(s) => { setLocalLeaders(s); sync(s, localBull, localBear); }} />
      <PoolSection title="多头池 Bull Pool" color="#38a169" stocks={localBull} setStocks={(s) => { setLocalBull(s); sync(localLeaders, s, localBear); }} />
      <PoolSection title="空头池 Bear Pool" color="#dd6b20" stocks={localBear} setStocks={(s) => { setLocalBear(s); sync(localLeaders, localBull, s); }} />
    </div>
  );
}

// ── Main Page ──

export function AnalystWorkspacePage() {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedMsg, setSavedMsg] = useState("");
  const [activeTab, setActiveTab] = useState<"emotion" | "watch">("emotion");
  const [generating, setGenerating] = useState(false);
  const [genProgress, setGenProgress] = useState<{ show: boolean; step: string; steps: string[]; current: number; error?: string }>({ show: false, step: "", steps: [], current: 0 });
  const [genKey, setGenKey] = useState(0);
  const [tomorrowOutlook, setTomorrowOutlook] = useState("");
  const [tomorrowWatchpoints, setTomorrowWatchpoints] = useState<string[]>([]);
  const [tomorrowForbidden, setTomorrowForbidden] = useState<string[]>([]);
  const [calibrating, setCalibrating] = useState(false);
  const [calMsg, setCalMsg] = useState("");
  const [importDialog, setImportDialog] = useState<{ show: boolean; step: "select" | "parsing" | "imported" | "calibrating" | "done" | "error"; msg: string; result?: any }>({ show: false, step: "select", msg: "" });
  const [fileInputKey, setFileInputKey] = useState(0);
  const [readinessDialog, setReadinessDialog] = useState<{ show: boolean; chart: boolean; emotion: boolean; reference: boolean; mode: "generate" | "calibrate" } | null>(null);

  const qs = new URLSearchParams(window.location.search);
  const tradeDate = qs.get("trade_date") || new Date().toISOString().slice(0, 10);
  const [dateInput, setDateInput] = useState(tradeDate);

  const fetchWorkspace = useCallback(async (d: string) => {
    setLoading(true);
    try {
      const resp = await fetch(`/api/v1/analyst-workspace/${d}`);
      if (!resp.ok) throw new Error(`${resp.status}`);
      const data = await resp.json();

      // ── Map new API response (review_document-centric) to Workspace interface ──
      const rd = data.review_document || {};
      const meta = data.metadata || {};
      const mode = meta.mode || "not_started";

      const themes: ThemeEntry[] = (rd.themes || []).map((t: any) => {
        const name = (typeof t.name === "object" && t.name !== null)
          ? (t.name.final_value || t.name.ai_value || "")
          : (t.name || "");
        const level = t.role === "MAINLINE" ? "CRITICAL" : t.role === "SECONDARY" ? "HIGH" : "MEDIUM";
        return {
          subject_id: t.theme_key || `rd_${Math.random().toString(36).slice(2)}`,
          subject_name: name || t.theme_key || "(未命名)",
          attention_level: level,
          attention_score: typeof t.strength_score === "number" ? Math.round(t.strength_score * 100) : 50,
          attention_reasons: [],
          ai_recommended: true,
          analyst_added: false,
          trading_style: "",
          long_identifiability: 0.5,
          short_identifiability: 0.3,
          old_leaders: "",
          event_stimuli: [""],
          yesterday_view: "",
          today_actual: "",
          stage_judgement: t.stage || "",
          intraday_understanding: "",
          trader_sentiment: "",
          index_resonance: "",
          tomorrow_view: "",
          analyst_notes: "",
          is_ai_draft: mode === "draft",
          analyst_reviewed: mode === "approved",
          field_overrides: {},
          leaders: [],
          bull_pool: [],
          bear_pool: [],
        };
      });

      // Load watch directions from API
      let watchGroups: WatchGroup[] = [];
      try {
        const wdResp = await fetch(`/api/v1/analyst-workspace/${d}/watch-directions`);
        if (wdResp.ok) {
          const wdData = await wdResp.json();
          watchGroups = (wdData.watch_directions || []).map((ad: any) => ({
            id: ad.direction_key,
            name: ad.direction_name,
            subject_ids: [...new Set((ad.themes || []).map((t: any) => t.subject_key))] as string[],
            color: ad.color || "#66d9ef",
            trading_style: ad.trading_style || "",
            long_identifiability: ad.snapshot?.long_identifiability ?? 0.5,
            short_identifiability: ad.snapshot?.short_identifiability ?? 0.3,
            old_leaders: ad.snapshot?.old_leaders || "",
            event_stimuli: ad.snapshot?.event_stimuli || [""],
            yesterday_view: ad.snapshot?.yesterday_view || "",
            today_actual: ad.snapshot?.today_actual || "",
            stage_judgement: ad.snapshot?.stage_judgement || "",
            intraday_understanding: ad.snapshot?.intraday_understanding || "",
            trader_sentiment: ad.snapshot?.trader_sentiment || "",
            index_resonance: ad.snapshot?.index_resonance || "",
            tomorrow_view: ad.snapshot?.tomorrow_view || "",
            analyst_notes: ad.snapshot?.analyst_notes || "",
            leaders: (ad.snapshot?.leaders || []).map((l: any) => ({ ...l, is_ai_draft: false, analyst_reviewed: true })),
            bull_pool: (ad.snapshot?.bull_pool || []).map((s: any) => ({ ...s, is_ai_draft: false, analyst_reviewed: true })),
            bear_pool: (ad.snapshot?.bear_pool || []).map((s: any) => ({ ...s, is_ai_draft: false, analyst_reviewed: true })),
            field_overrides: {},
          } as WatchGroup));
        }
      } catch { /* non-fatal */ }

      setWorkspace({
        trade_date: meta.trade_date || d,
        is_ai_draft: mode === "draft",
        analyst_finalized: mode === "approved",
        themes,
        watch_groups: watchGroups,
        override_count: (rd.audit?.explicit_overrides || []).length,
        review_document: rd,
      });
      setSelectedIdx(0);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchWorkspace(dateInput); fetchTomorrow(dateInput); }, [dateInput, fetchWorkspace]);

  const handleSave = async () => {
    if (!workspace) return;
    setSaving(true);
    setSavedMsg("");
    const steps: string[] = [];

    try {
      // Step 1: Save workspace overrides (old save endpoint)
      const saveResp = await fetch(`/api/v1/analyst-workspace/${dateInput}/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(workspace),
      });
      if (!saveResp.ok) throw new Error(`保存失败: HTTP ${saveResp.status}`);
      const saveResult = await saveResp.json();
      steps.push(`已保存 ${saveResult.overrides_recorded || 0} 条修改`);

      // Step 1.5: Save watch directions
      try {
        const wdPayload = {
          watch_directions: (workspace.watch_groups || []).map((g: WatchGroup) => ({
            direction_key: g.id,
            direction_name: g.name,
            direction_type: "ANALYST_WATCH",
            trading_style: g.trading_style || "",
            color: g.color || "",
            sort_order: 0,
            snapshot: {
              stage_judgement: g.stage_judgement || "",
              old_leaders: g.old_leaders || "",
              yesterday_view: g.yesterday_view || "",
              today_actual: g.today_actual || "",
              tomorrow_view: g.tomorrow_view || "",
              analyst_notes: g.analyst_notes || "",
              leaders: g.leaders || [],
              bull_pool: g.bull_pool || [],
              bear_pool: g.bear_pool || [],
            },
            themes: (g.subject_ids || []).map((sk: string) => ({
              subject_key: sk,
              relevance_weight: 1.0,
              capital_weight: 1.0,
            })),
          })),
        };
        const wdResp = await fetch(`/api/v1/analyst-workspace/${dateInput}/watch-directions`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(wdPayload),
        });
        if (wdResp.ok) {
          const wdResult = await wdResp.json();
          steps.push(`已保存 ${wdResult.saved_count || 0} 个观察方向`);
        }
      } catch { /* non-fatal */ }

      // Step 2: Save review → transition DRAFT_READY → IN_REVIEW
      const reviewResp = await fetch(`/api/v1/analyst-workbench/${dateInput}/save-review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ overrides: { analyst_reviewed: true, saved_at: new Date().toISOString() } }),
      });
      if (reviewResp.ok) {
        const reviewResult = await reviewResp.json();
        steps.push(`审核状态: ${reviewResult.session_status}`);
      }

      // Step 3: Auto-approve → create snapshot (analyst clicking Save = approved)
      if (reviewResp.ok) {
        const approveResp = await fetch(`/api/v1/analyst-workbench/${dateInput}/approve`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ approved_by: "analyst" }),
        });
        if (approveResp.ok) {
          const approveResult = await approveResp.json();
          steps.push(`已审核通过 · snapshot_v${approveResult.snapshot_version}`);
        } else {
          // If already APPROVED, that's OK
          const errData = await approveResp.json().catch(() => ({}));
          if ((errData as any).detail?.includes("Invalid transition")) {
            steps.push("(已审核通过)");
          }
        }
      }

      setSavedMsg(steps.join(" · "));
      // Refresh workspace data to reflect new status
      fetchWorkspace(dateInput);
    } catch (e: any) {
      setSavedMsg(`❌ ${e.message || "保存失败"}`);
    } finally {
      setSaving(false);
      setTimeout(() => setSavedMsg(""), 5000);
    }
  };

  const handleGenerate = async () => {
    setGenerating(true);
    const steps = ["生成复盘动态数据…", "生成图表证据…", "生成情绪分析…", "构建 AI Draft…", "完成"];
    setGenProgress({ show: true, step: steps[0], steps, current: 0 });

    const stepIndex: Record<string, number> = {
      derived_data: 0,
      charts: 1,
      emotion: 2,
      draft: 3,
      workbench: 3,
    };
    const failedStatuses = new Set(["failed", "timeout", "failed_precondition"]);
    let pollTimer: ReturnType<typeof setInterval> | null = null;

    const applyGenerationProgress = (payload: any) => {
      const generationSteps = Array.isArray(payload?.generation_steps) ? payload.generation_steps : [];
      let current = 0;
      let activeStep = steps[0];
      let errorMsg = "";

      for (const item of generationSteps) {
        const idx = stepIndex[String(item?.step || "")];
        if (idx === undefined) continue;
        const status = String(item?.status || "");
        if (status === "success") {
          current = Math.max(current, idx + 1);
          activeStep = idx + 1 < steps.length ? steps[idx + 1] : steps[steps.length - 1];
        } else if (status === "running") {
          current = Math.max(current, idx);
          activeStep = steps[idx];
        } else if (failedStatuses.has(status)) {
          current = idx;
          activeStep = `${steps[idx].replace("…", "")}失败`;
          errorMsg = item?.error || `${item?.step || "generation"} ${status}`;
        }
      }

      if (payload?.status === "DRAFT_READY" || payload?.session_status === "DRAFT_READY" || payload?.status === "success") {
        current = steps.length - 1;
        activeStep = "✅ 分析完成";
      }

      setGenProgress(p => ({
        ...p,
        step: activeStep,
        current: Math.min(current, steps.length - 1),
        error: errorMsg || p.error,
      }));
    };

    const pollSession = async () => {
      try {
        const sessResp = await fetch(`/api/v1/analyst-workbench/${dateInput}/session`);
        if (!sessResp.ok) return;
        const sess = await sessResp.json();
        applyGenerationProgress(sess);
      } catch {
        // Polling is diagnostic only. The generate request remains the source of truth.
      }
    };

    try {
      pollTimer = setInterval(pollSession, 1000);
      await pollSession();

      const resp = await fetch(`/api/v1/analyst-workbench/${dateInput}/generate`, { method: "POST", signal: AbortSignal.timeout(180000) });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

      const r = await resp.json();
      applyGenerationProgress(r);

      // Handle truthful status from backend
      if (r.status === "failed" || r.status === "failed_precondition") {
        const failedStep = Array.isArray(r.generation_steps)
          ? r.generation_steps.find((s: any) => failedStatuses.has(String(s?.status || "")))
          : null;
        throw new Error(failedStep?.error || r.error || "启动分析失败");
      }

      // Refresh workspace to pick up the newly generated draft
      await fetchWorkspace(dateInput);
      setGenKey(k => k + 1);

      if (r.status === "partial") {
        const missing = r.missing_fields?.join(", ") || "未知";
        setGenProgress(p => ({
          ...p,
          step: `⚠ 部分完成 (缺少: ${missing})`,
          current: 3,
          error: undefined,
        }));
      } else {
        setGenProgress(p => ({ ...p, step: "✅ 分析完成", current: steps.length - 1 }));
      }
      await new Promise(r => setTimeout(r, 1000));
      setGenProgress({ show: false, step: "", steps: [], current: 0 });
    } catch (e: any) {
      const msg = e?.name === "TimeoutError"
        ? "启动分析超过 180 秒，后端应已记录具体失败步骤，请查看 generation_steps"
        : e.message || "请求失败";
      setGenProgress(p => ({ ...p, error: msg, step: "❌ 启动分析失败" }));
    } finally {
      if (pollTimer) clearInterval(pollTimer);
      setGenerating(false);
    }
  };

  const resetImportDialog = (step: typeof importDialog.step = "select") => {
    setFileInputKey(k => k + 1);
    setImportDialog({ show: true, step, msg: "" });
  };

  const closeImportDialog = () => {
    setFileInputKey(k => k + 1);
    setImportDialog({ show: false, step: "select", msg: "" });
  };

  const fetchTomorrow = async (d: string) => {
    try {
      const resp = await fetch(`/api/v2/daily-review-v2?date=${encodeURIComponent(d)}`);
      if (resp.ok) {
        const dr = await resp.json();
        const er = dr.emotion_review || {};
        setTomorrowOutlook((er as any).tomorrow_outlook || "");
        setTomorrowWatchpoints((er as any).tomorrow_watchpoints || []);
        setTomorrowForbidden((er as any).tomorrow_forbidden || []);
      }
    } catch {}
  };

  const handleImportAnalyst = () => {
    // Open import dialog — user selects .md file first, then we parse + store + calibrate
    resetImportDialog("select");
  };

  const handleFileSelected = async (file: File) => {
    setImportDialog({ show: true, step: "parsing", msg: "读取文件中…" });

    let content: string;
    try {
      content = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result as string);
        reader.onerror = () => reject(new Error("文件读取失败"));
        reader.readAsText(file);
      });
    } catch {
      setImportDialog({ show: true, step: "error", msg: "文件读取失败，请重试" });
      return;
    }

    // Step 1: Import reference
    setImportDialog({ show: true, step: "parsing", msg: "解析分析师复盘文件…" });
    try {
      const importResp = await fetch("/api/v1/analyst-reference/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ trade_date: dateInput, content }),
      });
      if (!importResp.ok) {
        const err = await importResp.json().catch(() => ({}));
        throw new Error((err as any).detail || `HTTP ${importResp.status}`);
      }
      const importResult = await importResp.json();
      setImportDialog({
        show: true, step: "imported", msg: "解析完成",
        result: { import: importResult },
      });
    } catch (e: any) {
      setImportDialog({ show: true, step: "error", msg: e.message || "导入失败" });
      return;
    }

    // Step 2: Check AI draft exists before calibration
    try {
      const sessResp = await fetch(`/api/v1/analyst-workbench/${dateInput}/session`);
      const sess = sessResp.ok ? await sessResp.json() : {};
      if (!sess.has_draft) {
        setImportDialog({
          show: true, step: "error",
          msg: "请先生成 AI 草稿！点击工作台顶部「▶ 启动分析」按钮，等 AI 草稿生成完成后，再导入分析师数据进行校准。",
        });
        return;
      }
    } catch {
      // proceed anyway
    }

    // Step 3: Run alignment
    setImportDialog(p => ({ ...p, step: "calibrating", msg: "AI↔分析师校准中…" }));
    try {
      const alignResp = await fetch(`/api/v1/analyst-alignment/${dateInput}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reference_dir: "tmp/analyst_reference" }),
      });
      if (!alignResp.ok) throw new Error(`HTTP ${alignResp.status}`);
      const ar = await alignResp.json();
      if (ar.status === "error") throw new Error(ar.error || "校准失败");

      // Step 3: Persist calibration
      try {
        await fetch(`/api/v1/analyst-workbench/${dateInput}/calibrate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(ar),
        });
      } catch { /* non-fatal */ }

      // Fetch AI vs Analyst comparison for display
      let comparison = null;
      try {
        const cmpResp = await fetch(`/api/v1/analyst-workbench/${dateInput}/comparison`);
        if (cmpResp.ok) comparison = await cmpResp.json();
      } catch {}

      setImportDialog(p => ({
        ...p, step: "done", msg: "校准完成",
        result: { ...p.result, alignment: ar, comparison },
      }));
    } catch (e: any) {
      setImportDialog(p => ({
        ...p, step: "error",
        msg: `校准失败: ${e.message || "请求失败"}`,
      }));
    }
  };

  const emptyWorkspace: Workspace = {
    trade_date: dateInput,
    is_ai_draft: false,
    analyst_finalized: false,
    themes: [],
    watch_groups: [],
    override_count: 0,
  };
  const ws = workspace || emptyWorkspace;
  const theme = ws.themes[selectedIdx] || newTheme();
  const activeGroup = (ws.watch_groups || []).find(g => g.id === selectedGroupId);
  const groupedThemeIds = new Set((ws.watch_groups || []).flatMap(g => g.subject_ids));

  const updateTheme = (t: ThemeEntry) => {
    const themes = [...ws.themes];
    themes[selectedIdx] = t;
    setWorkspace({ ...ws, themes, is_ai_draft: false });
  };

  const updateGroup = (g: WatchGroup) => {
    const groups = (ws.watch_groups || []).map(x => x.id === g.id ? g : x);
    setWorkspace({ ...ws, watch_groups: groups, is_ai_draft: false });
  };

  return (
    <div className="workspace-page recap-dark-theme" style={{ display: "flex", flexDirection: "column", height: "100vh", padding: 0 }}>
      {/* Top bar — matching system dark theme */}
      <section className="strong-watch-toolbar" style={{ padding: "10px 16px", borderBottom: "1px solid #243040" }}>
        <img src="/assets/recap-icon-B0VZ9YED.png" alt="" style={{ height: 40, width: 40, flexShrink: 0 }} onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }} />
        <h1 className="strong-watch-title" style={{ fontSize: 20, margin: 0 }}>分析师工作台</h1>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginLeft: "auto" }}>
          <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 12, color: "#66d9ef" }}>交易日</span>
            <input type="date" value={dateInput} max={new Date().toISOString().slice(0, 10)} onChange={(e) => { const v = e.target.value; setDateInput(v); window.history.replaceState(null, '', `?trade_date=${v}`); }}
              style={{ border: "1px solid #2a2a2a", borderRadius: 6, background: "#1a1a1a", color: "#f5f5f5", padding: "4px 8px" }} />
          </label>
          <button className="tag tag-button" type="button" style={{ fontSize: 12, padding: "5px 12px", background: "#1a3a5c", color: "#66d9ef", border: "1px solid #243040", borderRadius: 6, cursor: "pointer" }}
            disabled={generating} onClick={handleGenerate}>
            {generating ? "⏳" : "▶"} 启动分析
          </button>
          <button className="tag tag-button" type="button" style={{ fontSize: 12, padding: "5px 12px", background: "#1a3a2c", color: "#39ff14", border: "1px solid #243040", borderRadius: 6, cursor: "pointer" }}
            disabled={calibrating} onClick={handleImportAnalyst}>
            {calibrating ? "⏳" : "☰"} 导入分析师数据
          </button>
          {calMsg && <span style={{ fontSize: 11, color: "#39ff14" }}>{calMsg}</span>}
          {activeGroup && <span style={{ fontSize: 13, color: activeGroup.color, fontWeight: 600 }}>{activeGroup.name}</span>}
          <span style={{ fontSize: 12, color: "#66d9ef" }}>
            {ws.themes.length} 题材 · {(ws.watch_groups || []).length} 方向
          </span>
          {savedMsg && <span style={{ fontSize: 12, color: "#39ff14" }}>{savedMsg}</span>}
          <button className="tag tag-button is-pass" type="button" style={{ fontSize: 14, padding: "6px 16px" }}
            disabled={saving} onClick={handleSave}>
            {saving ? "保存中…" : "保存"}
          </button>
        </div>
        <button className="back-button" type="button" onClick={() => { window.history.back(); }}>
          返回
        </button>
      </section>

      {/* Tab bar */}
      <div style={{ display: "flex", gap: 0, padding: "0 16px", background: "#0c1118", borderBottom: "1px solid #243040" }}>
        {(["emotion", "watch"] as const).map(tab => (
          <div key={tab} onClick={() => setActiveTab(tab)}
            style={{ padding: "8px 16px", cursor: "pointer", fontSize: 13, fontWeight: 600,
              color: activeTab === tab ? "#ffd85e" : "#5a7a8a",
              borderBottom: activeTab === tab ? "2px solid #ffd85e" : "2px solid transparent" }}>
            {tab === "emotion" ? "情绪与图表" : "观察方向"}
          </div>
        ))}
      </div>

      {/* Tab 1: Emotion Dashboard */}
      <div style={{ flex: 1, overflow: "auto", background: "#0c1118", display: activeTab === "emotion" ? "block" : "none" }}>
        <EmotionDashboard key={`${dateInput}-${genKey}`} tradeDate={dateInput} tomorrowOutlook={tomorrowOutlook} tomorrowWatchpoints={tomorrowWatchpoints} tomorrowForbidden={tomorrowForbidden} reviewDocument={ws.review_document} />
        <ReviewDocumentSections document={ws.review_document} />
      </div>

      {/* Tab 2: Three-panel body — dark theme */}
      {activeTab === "watch" && loading && <div style={{ padding: 24, flex: 1, background: "#0c1118", color: "#5a7a8a" }}>加载主题数据…</div>}
      <div style={{ flex: 1, display: (activeTab === "watch" && !loading) ? "grid" : "none", gridTemplateColumns: "240px 1fr 340px", overflow: "hidden", background: "#0c1118" }}>
        {/* Left: Theme list */}
        <div style={{ borderRight: "1px solid #243040", overflow: "hidden", background: "#111720" }}>
          <ThemeWatchList
            themes={ws.themes}
            allThemes={ws.themes}
            selectedIdx={selectedIdx}
            selectedGroupId={selectedGroupId}
            onSelect={(i) => { setSelectedGroupId(null); setSelectedIdx(i); }}
            onSelectGroup={(id) => { setSelectedGroupId(id); }}
            onAdd={() => {
              const themes = [...ws.themes, newTheme()];
              setWorkspace({ ...ws, themes, is_ai_draft: false });
              setSelectedIdx(themes.length - 1);
            }}
            onDelete={(i) => {
              const themes = ws.themes.filter((_, j) => j !== i);
              setWorkspace({ ...ws, themes });
              setSelectedIdx(Math.min(selectedIdx, themes.length - 1));
            }}
            onLevelChange={(i, lvl) => {
              const themes = [...ws.themes];
              themes[i] = { ...themes[i], attention_level: lvl, is_ai_draft: false };
              setWorkspace({ ...ws, themes });
            }}
            watchGroups={ws.watch_groups || []}
            onAddGroup={() => {
              const groups = [...(ws.watch_groups || [])];
              const colors = ["#e53e3e", "#3182ce", "#38a169", "#dd6b20", "#805ad5", "#d69e2e"];
              groups.push(newWatchGroup(colors[groups.length % colors.length]));
              setWorkspace({ ...ws, watch_groups: groups, is_ai_draft: false });
            }}
            onUpdateGroup={(g) => {
              const groups = (ws.watch_groups || []).map(x => x.id === g.id ? g : x);
              setWorkspace({ ...ws, watch_groups: groups, is_ai_draft: false });
            }}
            onDeleteGroup={(id) => {
              const groups = (ws.watch_groups || []).filter(x => x.id !== id);
              setWorkspace({ ...ws, watch_groups: groups });
            }}
            onAddThemeToGroup={(groupId, subjectId) => {
              const groups = (ws.watch_groups || []).map(g =>
                g.id === groupId ? { ...g, subject_ids: [...g.subject_ids, subjectId] } : g
              );
              setWorkspace({ ...ws, watch_groups: groups, is_ai_draft: false });
            }}
          />
        </div>

        {/* Center: Group Cognition or Individual Theme */}
        <div style={{ borderRight: "1px solid #243040", overflow: "hidden", background: "#0c1118" }}>
          {activeGroup ? (
            <>
              <div style={{ padding: "10px 14px", borderBottom: "1px solid #243040", background: activeGroup.color + "20" }}>
                <span className="recap-panel-title" style={{ fontSize: 15, color: activeGroup.color }}>{activeGroup.name}</span>
                <span style={{ marginLeft: 8, fontSize: 12, color: "#5a7a8a" }}>
                  {activeGroup.subject_ids.length} 个子题材
                </span>
                <div style={{ marginTop: 6, display: "flex", flexWrap: "wrap", gap: 4 }}>
                  {activeGroup.subject_ids.map(sid => {
                    const t = ws.themes.find(x => x.subject_id === sid);
                    return t ? <span key={sid} style={{ fontSize: 11, padding: "2px 8px", background: "#1a2a3a", borderRadius: 10, color: "#8ddcff" }}>{t.subject_name}</span> : null;
                  })}
                </div>
              </div>
              <GroupCognitionEditor group={activeGroup} onChange={updateGroup} />
            </>
          ) : theme ? (
            <>
              <div style={{ padding: "10px 14px", borderBottom: "1px solid #243040", background: theme.is_ai_draft ? "#1a2a1a" : "#1a2a3a" }}>
                <span style={{ fontSize: 14, fontWeight: 600, color: "#8ddcff" }}>
                  {theme.is_ai_draft ? "AI 草稿" : "分析师编辑中"} — <span style={{ color: "#ffd85e" }}>{theme.subject_name}</span>
                </span>
              </div>
              <CognitionEditor theme={theme} onChange={updateTheme} />
            </>
          ) : (
            <div style={{ padding: 60, textAlign: "center", color: "#5a7a8a", fontSize: 14 }}>
              选择一个观察方向或题材开始编辑
            </div>
          )}
        </div>

        {/* Right: Stock Pool */}
        <div style={{ overflow: "hidden", background: "#0c1118" }}>
          <div style={{ padding: "10px 14px", borderBottom: "1px solid #243040" }}>
            <span className="recap-panel-title" style={{ fontSize: 14 }}>
              {activeGroup ? `${activeGroup.name} — 股票池` : "股票池审核"}
            </span>
          </div>
          {activeGroup ? (
            <GroupStockPoolEditor group={activeGroup} onChange={updateGroup} />
          ) : (
            <StockPoolEditor theme={theme} onChange={updateTheme} />
          )}
        </div>
      </div>

      {/* ── Generate Progress Dialog ── */}
      {genProgress.show && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", zIndex: 9999, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ background: "#162230", border: genProgress.error ? "1px solid #d4380d" : "1px solid #66d9ef", borderRadius: 12, padding: 28, maxWidth: 440, width: "90%", textAlign: "center" }}>
            <h3 style={{ color: genProgress.error ? "#d4380d" : "#66d9ef", margin: "0 0 20px 0", fontSize: 16 }}>
              {genProgress.error ? "⚠ 分析失败" : "⚙ 正在启动分析"}
            </h3>
            <div style={{ background: "#0c1118", borderRadius: 8, padding: 16, marginBottom: 16 }}>
              {genProgress.steps.map((s, i) => {
                const done = i < genProgress.current;
                const active = i === genProgress.current;
                const failed = genProgress.error && i === genProgress.current;
                return (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, padding: "4px 0", fontSize: 13,
                    color: failed ? "#d4380d" : done ? "#39ff14" : active ? "#66d9ef" : "#3a5060" }}>
                    <span style={{ width: 18, textAlign: "center" }}>
                      {failed ? "✗" : done ? "✓" : active ? "●" : "○"}
                    </span>
                    <span>{s}</span>
                  </div>
                );
              })}
            </div>
            {/* Progress bar */}
            {!genProgress.error && (
              <div style={{ background: "#0c1118", borderRadius: 4, height: 6, marginBottom: 16, overflow: "hidden" }}>
                <div style={{ background: "linear-gradient(90deg, #66d9ef, #39ff14)", height: "100%",
                  width: `${Math.max(5, ((genProgress.current + 1) / genProgress.steps.length) * 100)}%`,
                  transition: "width 0.4s ease" }} />
              </div>
            )}
            {genProgress.error && (
              <div>
                <div style={{ background: "#2a1410", border: "1px solid #5a2416", borderRadius: 6, color: "#ff9b7a", fontSize: 12, lineHeight: 1.6, padding: "8px 10px", marginBottom: 14, textAlign: "left", wordBreak: "break-word" }}>
                  {genProgress.error}
                </div>
                <div style={{ display: "flex", gap: 10, justifyContent: "center" }}>
                  <button onClick={() => setGenProgress({ show: false, step: "", steps: [], current: 0 })}
                    style={{ padding: "8px 20px", background: "#243040", color: "#8da6b8", border: "1px solid #3a5060", borderRadius: 6, cursor: "pointer", fontSize: 13 }}>
                    关闭
                  </button>
                  <button onClick={() => { setGenProgress({ show: false, step: "", steps: [], current: 0 }); handleGenerate(); }}
                    style={{ padding: "8px 20px", background: "#d4380d", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 13 }}>
                    重试
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Import Analyst Reference Dialog ── */}
      {importDialog.show && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", zIndex: 9999, display: "flex", alignItems: "center", justifyContent: "center" }}
          onClick={() => { if (importDialog.step === "done" || importDialog.step === "error") closeImportDialog(); }}>
          <div style={{ background: "#162230", border: importDialog.step === "error" ? "1px solid #d4380d" : "1px solid #66d9ef", borderRadius: 12, padding: 24, maxWidth: 480, width: "90%" }}
            onClick={e => e.stopPropagation()}>
            <h3 style={{ color: importDialog.step === "error" ? "#d4380d" : "#66d9ef", margin: "0 0 16px 0", fontSize: 16 }}>
              {importDialog.step === "select" ? "导入分析师复盘数据" :
               importDialog.step === "parsing" ? "正在解析…" :
               importDialog.step === "imported" ? "解析完成" :
               importDialog.step === "calibrating" ? "AI↔分析师校准" :
               importDialog.step === "done" ? "校准完成" : "导入失败"}
            </h3>

            {/* Step: Select file */}
            {importDialog.step === "select" && (
              <div style={{ textAlign: "center" }}>
                <p style={{ color: "#8da6b8", fontSize: 13, marginBottom: 16 }}>
                  选择分析师的 DeepSeek 复盘 .md 文件，系统将自动解析并导入为参考数据。
                </p>
                <input
                  key={`file-input-${fileInputKey}`}
                  type="file" accept=".md,.txt,.markdown"
                  onChange={(e: any) => {
                    const f = e.target?.files?.[0];
                    if (f) handleFileSelected(f);
                  }}
                  style={{ display: "block", margin: "0 auto 16px", color: "#8ddcff", fontSize: 13 }} />
                <div style={{ fontSize: 11, color: "#5a7a8a", marginTop: 12 }}>
                  数据流：导入 .md → 解析为结构化参考 → AI↔分析师校准 → 回写 draft
                </div>
              </div>
            )}

            {/* Step: Parsing / Importing / Calibrating — progress */}
            {(importDialog.step === "parsing" || importDialog.step === "imported" || importDialog.step === "calibrating") && (
              <div style={{ textAlign: "center" }}>
                <div style={{ marginBottom: 12 }}>
                  <div style={{
                    width: 40, height: 40, margin: "0 auto 12px",
                    border: "4px solid #1a2a3a", borderTop: "4px solid #66d9ef",
                    borderRadius: "50%", animation: "spin 0.8s linear infinite",
                  }} />
                </div>
                <p style={{ color: "#8ddcff", fontSize: 13 }}>{importDialog.msg}</p>
                {importDialog.step === "imported" && importDialog.result?.import && (
                  <div style={{ marginTop: 12, padding: 10, background: "#0c1118", borderRadius: 6, fontSize: 11, color: "#5a7a8a", textAlign: "left" }}>
                    {/* Format warning — prominent */}
                    {importDialog.result.import.validation_issues?.length > 0 && (
                      <div style={{ marginBottom: 10, padding: "8px 12px", background: "#ffd85e15", border: "1px solid #ffd85e40", borderRadius: 4, fontSize: 11, color: "#ffd85e", lineHeight: 1.5 }}>
                        {(importDialog.result.import.validation_issues as string[]).map((issue, i) => (
                          <div key={i}>{issue}</div>
                        ))}
                      </div>
                    )}
                    <div>提取状态: <span style={{ color: importDialog.result.import.extraction_status === "full_complete" ? "#39ff14" : "#ffd85e" }}>{importDialog.result.import.extraction_status}</span></div>
                    <div>核心覆盖率: {importDialog.result.import.coverage?.core_coverage != null ? `${(importDialog.result.import.coverage.core_coverage * 100).toFixed(0)}%` : "—"} / 完整覆盖率: {importDialog.result.import.coverage?.full_coverage != null ? `${(importDialog.result.import.coverage.full_coverage * 100).toFixed(0)}%` : "—"}</div>
                    <div>市场阶段: <span style={{ color: "#8ddcff" }}>{importDialog.result.import.market_phase || "—"}</span></div>
                    <div>风险等级: <span style={{ color: "#8ddcff" }}>{{LOW:"低风险",MEDIUM:"中等风险",HIGH:"高风险",EXTREME:"极高风险",MEDIUM_HIGH:"中高风险",CRITICAL:"危险"}[importDialog.result.import.risk_level as string] || importDialog.result.import.risk_level || "—"}</span></div>
                    <div>涨停数: {importDialog.result.import.limit_up_count ?? "—"} / 最高板: {importDialog.result.import.max_board_height ?? "—"}</div>
                    {importDialog.result.import.missing_fields?.length > 0 && (
                      <div style={{ marginTop: 4, fontSize: 10, color: "#e53e3e" }}>
                        缺失字段: {(importDialog.result.import.missing_fields as string[]).join(", ")}
                      </div>
                    )}
                  </div>
                )}
                {importDialog.step === "calibrating" && <p style={{ fontSize: 11, color: "#5a7a8a", marginTop: 8 }}>正在对比 AI 生成数据与分析师参考数据…</p>}
              </div>
            )}

            {/* Step: Done */}
            {importDialog.step === "done" && importDialog.result?.alignment && (
              <div style={{ textAlign: "center" }}>
                {/* Show import validation warnings prominently at top */}
                {importDialog.result?.import?.validation_issues?.length > 0 && (
                  <div style={{ marginBottom: 12, padding: "10px 14px", background: "#ff4d4f15", border: "1px solid #ff4d4f40", borderRadius: 6, textAlign: "left" }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: "#ff4d4f", marginBottom: 4 }}>❌ 文件格式不匹配</div>
                    {(importDialog.result.import.validation_issues as string[]).map((issue, i) => (
                      <div key={i} style={{ fontSize: 12, color: "#ffa940", lineHeight: 1.5 }}>{issue}</div>
                    ))}
                  </div>
                )}
                {/* Show clean import confirmation */}
                {(!importDialog.result?.import?.validation_issues || importDialog.result.import.validation_issues.length === 0) && (
                  <div style={{ marginBottom: 12, padding: "8px 14px", background: "#38a16915", border: "1px solid #38a16940", borderRadius: 6, fontSize: 12, color: "#38a169" }}>
                    ✅ 文件格式正确 · 提取状态: {importDialog.result?.import?.extraction_status || "—"} · 核心覆盖率: {importDialog.result?.import?.coverage?.core_coverage != null ? `${(importDialog.result.import.coverage.core_coverage * 100).toFixed(0)}%` : "—"}
                  </div>
                )}
                <div style={{ fontSize: 48, marginBottom: 8 }}>
                  {importDialog.result.alignment.grade === "A" ? "✅" :
                   importDialog.result.alignment.grade === "B" ? "👍" :
                   importDialog.result.alignment.grade === "F" ? "⚠️" : "📊"}
                </div>
                <div style={{ fontSize: 28, fontWeight: 800, color: "#66d9ef", marginBottom: 4 }}>
                  ATS {(importDialog.result.alignment.overall_score * 100).toFixed(1)}%
                </div>
                <div style={{ fontSize: 14, color: "#8ddcff", marginBottom: 12 }}>
                  Grade {importDialog.result.alignment.grade}
                </div>
                {/* AI vs Analyst Comparison Table */}
                {importDialog.result?.comparison?.rows && (
                  <div style={{ marginBottom: 12, textAlign: "left" }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: "#ffd85e", marginBottom: 8 }}>
                      AI vs 分析师 逐项对比
                    </div>
                    {(importDialog.result.comparison.rows as any[]).map((row: any) => {
                      const pct = (row.score * 100).toFixed(0);
                      const color = row.score < 0.3 ? "#e53e3e" : row.score < 0.7 ? "#d69e2e" : "#38a169";
                      const icon = row.score < 0.3 ? "❌" : row.score < 0.7 ? "⚠️" : "✅";
                      return (
                        <div key={row.key} style={{
                          padding: "8px 10px", marginBottom: 4,
                          background: "#0c1118", borderRadius: 4,
                          borderLeft: `3px solid ${color}`,
                        }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                            <span style={{ fontSize: 14 }}>{icon}</span>
                            <span style={{ fontSize: 12, fontWeight: 600, color: "#8ddcff", minWidth: 70 }}>{row.label}</span>
                            <span style={{ color, fontWeight: 700, fontSize: 12, marginLeft: "auto" }}>{pct}% 匹配</span>
                          </div>
                          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 11 }}>
                            <div>
                              <span style={{ color: "#5a7a8a" }}>AI：</span>
                              <span style={{ color: row.score < 0.5 ? "#e53e3e" : "#8ddcff" }}>{row.ai_value || "—"}</span>
                            </div>
                            <div>
                              <span style={{ color: "#5a7a8a" }}>分析师：</span>
                              <span style={{ color: "#39ff14" }}>{row.analyst_value || "—"}</span>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
                <div style={{ display: "flex", gap: 10, justifyContent: "center", marginTop: 16 }}>
                  <button onClick={async () => {
                    setImportDialog(p => ({ ...p, step: "calibrating", msg: "应用校准修正…" }));
                    try {
                      const resp = await fetch(`/api/v1/analyst-workbench/${dateInput}/apply-calibration`, { method: "POST" });
                      if (resp.ok) {
                        const r = await resp.json();
                        const emotionReview = r.emotion_review || {};
                        setImportDialog(p => ({
                          ...p, step: "done",
                          msg: `已应用 ${r.corrections.length} 项修正`,
                          result: { ...p.result, applied: r },
                        }));
                        setTomorrowOutlook(emotionReview.tomorrow_outlook || "");
                        setTomorrowWatchpoints(emotionReview.tomorrow_watchpoints || []);
                        setTomorrowForbidden(emotionReview.tomorrow_forbidden || []);
                        setGenKey(k => k + 1);
                        await fetchWorkspace(dateInput);
                      } else {
                        const err = await resp.json().catch(() => ({}));
                        throw new Error((err as any).detail || "应用失败");
                      }
                    } catch (e: any) {
                      setImportDialog(p => ({ ...p, step: "error", msg: e.message || "应用校准失败" }));
                    }
                  }}
                    style={{ padding: "8px 20px", background: "#ff4d4f", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 13, fontWeight: 600 }}>
                    ⚡ 应用校准修正
                  </button>
                  <button onClick={() => closeImportDialog()}
                    style={{ padding: "8px 20px", background: "#38a169", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 13 }}>
                    完成
                  </button>
                </div>
                {importDialog.result?.applied && (
                  <div style={{ marginTop: 10, padding: 8, background: "#38a16915", borderRadius: 4, fontSize: 11, textAlign: "left", color: "#38a169" }}>
                    {(importDialog.result.applied as any).corrections?.map((c: string, i: number) => (
                      <div key={i}>✓ {c}</div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Step: Error */}
            {importDialog.step === "error" && (
              <div style={{ textAlign: "center" }}>
                <div style={{ color: "#d4380d", fontSize: 13, marginBottom: 12 }}>{importDialog.msg}</div>
                <div style={{ display: "flex", gap: 10, justifyContent: "center" }}>
                  <button onClick={() => resetImportDialog("select")}
                    style={{ padding: "8px 20px", background: "#243040", color: "#8da6b8", border: "1px solid #3a5060", borderRadius: 6, cursor: "pointer", fontSize: 13 }}>
                    重试
                  </button>
                  <button onClick={() => closeImportDialog()}
                    style={{ padding: "8px 20px", background: "#d4380d", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 13 }}>
                    关闭
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Data Readiness Dialog ── */}
      {readinessDialog?.show && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", zIndex: 9999, display: "flex", alignItems: "center", justifyContent: "center" }}
          onClick={() => setReadinessDialog(null)}>
          <div style={{ background: "#162230", border: "1px solid #ffd85e", borderRadius: 12, padding: 24, maxWidth: 420, width: "90%" }}
            onClick={e => e.stopPropagation()}>
            <h3 style={{ color: "#ffd85e", margin: "0 0 12px 0", fontSize: 16 }}>⚠ 数据未就绪</h3>
            <p style={{ color: "#8da6b8", fontSize: 13, marginBottom: 16 }}>
              当前日期 <b>{dateInput}</b> 缺少以下数据，校准分析无法进行：
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 16 }}>
              <DataStatusRow label="图表证据 (由「启动分析」生成)" ok={readinessDialog.chart}
                hint={!readinessDialog.chart ? "请先点击「启动分析」" : undefined} />
              <DataStatusRow label="情绪分析 (由「启动分析」生成)" ok={readinessDialog.emotion}
                hint={!readinessDialog.emotion ? "请先点击「启动分析」" : undefined} />
              <DataStatusRow label="AI Draft (由「启动分析」生成)" ok={readinessDialog.reference}
                hint={!readinessDialog.reference ? "请先点击「启动分析」生成 AI 草稿" : undefined} />
            </div>
            <p style={{ color: "#5a7a8a", fontSize: 12, marginBottom: 16 }}>
              数据流：盘后数据采集 → <b>启动分析</b>（复盘动态数据 + 图表证据 + 情绪分析 + AI Draft）→ <b>导入分析师数据</b>（AI vs 分析师校准评分）
            </p>
            <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
              <button onClick={() => setReadinessDialog(null)}
                style={{ padding: "8px 20px", background: "#243040", color: "#8da6b8", border: "1px solid #3a5060", borderRadius: 6, cursor: "pointer", fontSize: 13 }}>
                知道了
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function DataStatusRow({ label, ok, hint }: { label: string; ok: boolean; hint?: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
      <span style={{ color: ok ? "#39ff14" : "#d4380d", fontWeight: 700 }}>{ok ? "✓" : "✗"}</span>
      <span style={{ color: ok ? "#8da6b8" : "#d4886b" }}>{label}</span>
      {!ok && hint && <span style={{ fontSize: 11, color: "#ffa940" }}>→ {hint}</span>}
    </div>
  );
}

// ── Group-level cognition editor ──

function GroupCognitionEditor({ group, onChange }: { group: WatchGroup; onChange: (g: WatchGroup) => void }) {
  const update = (field: string, value: any) => {
    const g = { ...group, [field]: value };
    g.field_overrides = { ...g.field_overrides, [field]: { ai_value: "", analyst_value: String(value), reason: "" } };
    onChange(g);
  };
  const TF = ({ label, field, rows = 2 }: { label: string; field: string; rows?: number }) => (
    <div style={{ marginBottom: 10 }}>
      <label style={{ fontSize: 12, fontWeight: 600, color: "#8ddcff", display: "block", marginBottom: 3 }}>{label}</label>
      {rows > 1 ? (
        <textarea value={(group as any)[field] || ""} onChange={(e) => update(field, e.target.value)} rows={rows}
          style={{ width: "100%", padding: 6, fontSize: 13, borderRadius: 4, border: "1px solid #243040", resize: "vertical", background: "#1a1a1a", color: "#f5f5f5" }} />
      ) : (
        <input value={(group as any)[field] || ""} onChange={(e) => update(field, e.target.value)}
          style={{ width: "100%", padding: 6, fontSize: 13, borderRadius: 4, border: "1px solid #243040", background: "#1a1a1a", color: "#f5f5f5" }} />
      )}
    </div>
  );
  return (
    <div style={{ padding: 12, overflow: "auto", height: "100%" }}>
      <TF label="炒作风格" field="trading_style" rows={1} />
      <TF label="老龙头 / 锚定" field="old_leaders" rows={1} />
      <TF label="昨日思路" field="yesterday_view" rows={2} />
      <TF label="今日实际" field="today_actual" rows={2} />
      <TF label="阶段研判" field="stage_judgement" rows={2} />
      <TF label="日内理解" field="intraday_understanding" rows={2} />
      <TF label="交易者心态" field="trader_sentiment" rows={1} />
      <TF label="指数共振" field="index_resonance" rows={1} />
      <TF label="隔日思考" field="tomorrow_view" rows={2} />
      <TF label="分析师备注" field="analyst_notes" rows={3} />
    </div>
  );
}

// ── Group-level stock pool editor (local state to prevent input focus loss) ──

function GroupStockPoolEditor({ group, onChange }: { group: WatchGroup; onChange: (g: WatchGroup) => void }) {
  const [localLeaders, setLocalLeaders] = useState<StockEntry[]>([]);
  const [localBull, setLocalBull] = useState<StockEntry[]>([]);
  const [localBear, setLocalBear] = useState<StockEntry[]>([]);
  const [init, setInit] = useState(false);

  // Init from props once
  if (!init) { setLocalLeaders(group.leaders||[]); setLocalBull(group.bull_pool||[]); setLocalBear(group.bear_pool||[]); setInit(true); }

  const sync = (leaders: StockEntry[], bull: StockEntry[], bear: StockEntry[]) => {
    onChange({ ...group, leaders, bull_pool: bull, bear_pool: bear });
  };

  return (
    <div style={{ padding: 12, overflow: "auto", height: "100%" }}>
      <PoolSection title="龙头 / 中军" color="#e53e3e" stocks={localLeaders} setStocks={(s) => { setLocalLeaders(s); sync(s, localBull, localBear); }} />
      <PoolSection title="多头池 Bull Pool" color="#38a169" stocks={localBull} setStocks={(s) => { setLocalBull(s); sync(localLeaders, s, localBear); }} />
      <PoolSection title="空头池 Bear Pool" color="#dd6b20" stocks={localBear} setStocks={(s) => { setLocalBear(s); sync(localLeaders, localBull, s); }} />
    </div>
  );
}

const ROLES = ["龙头","潜在龙头","中军","助攻","跟风","补涨","穿越龙"];
const newEmptyStock = (): StockEntry => ({ stock_code: "", stock_name: "", role: "跟风", reasons: [""], ai_recommended: false, analyst_confirmed: false, analyst_modified: true });

function PoolSection({ title, color, stocks, setStocks }: { title: string; color: string; stocks: StockEntry[]; setStocks: (s: StockEntry[]) => void }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
        <label style={{ fontSize: 13, fontWeight: 600, color }}>{title} ({stocks.length})</label>
        <button onClick={() => setStocks([...stocks, newEmptyStock()])}
          style={{ fontSize: 11, padding: "2px 8px", background: color, color: "#fff", border: "none", borderRadius: 3, cursor: "pointer" }}>+</button>
      </div>
      {stocks.map((s, i) => (
        <div key={i} style={{ padding: 8, marginBottom: 6, background: "#111720", borderRadius: 4, border: "1px solid #243040" }}>
          <div style={{ display: "flex", gap: 6, marginBottom: 4 }}>
            <input value={s.stock_code} onChange={e => { const a = [...stocks]; a[i] = { ...a[i], stock_code: e.target.value, analyst_modified: true }; setStocks(a); }} placeholder="代码" style={{ width: 70, padding: 4, fontSize: 12, borderRadius: 3, border: "1px solid #2a2a2a", background: "#1a1a1a", color: "#f5f5f5" }} />
            <input value={s.stock_name} onChange={e => { const a = [...stocks]; a[i] = { ...a[i], stock_name: e.target.value, analyst_modified: true }; setStocks(a); }} placeholder="名称" style={{ width: 80, padding: 4, fontSize: 12, borderRadius: 3, border: "1px solid #2a2a2a", background: "#1a1a1a", color: "#f5f5f5" }} />
            <select value={s.role} onChange={e => { const a = [...stocks]; a[i] = { ...a[i], role: e.target.value, analyst_modified: true }; setStocks(a); }}
              style={{ flex: 1, padding: 4, fontSize: 12, borderRadius: 3, border: "1px solid #2a2a2a", background: "#1a1a1a", color: "#f5f5f5" }}>
              {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
            <button onClick={() => setStocks(stocks.filter((_, j) => j !== i))}
              style={{ fontSize: 12, color: "#e53e3e", background: "none", border: "none", cursor: "pointer" }}>✕</button>
          </div>
          {(s.reasons.length === 0 ? [""] : s.reasons).map((r, j) => (
            <div key={j} style={{ display: "flex", gap: 4, marginBottom: 2 }}>
              <input value={r} onChange={e => { const a = [...stocks]; const rs = [...a[i].reasons]; rs[j] = e.target.value; a[i] = { ...a[i], reasons: rs, analyst_modified: true }; setStocks(a); }} placeholder={`理由 ${j + 1}`}
                style={{ flex: 1, padding: 3, fontSize: 11, borderRadius: 3, border: "1px solid #2a2a2a", background: "#1a1a1a", color: "#f5f5f5" }} />
              <button onClick={() => { const a = [...stocks]; a[i] = { ...a[i], reasons: a[i].reasons.filter((_, k) => k !== j), analyst_modified: true }; setStocks(a); }}
                style={{ fontSize: 11, color: "#5a7a8a", background: "none", border: "none", cursor: "pointer" }}>✕</button>
            </div>
          ))}
          {s.reasons.length < 5 && (
            <button onClick={() => { const a = [...stocks]; a[i] = { ...a[i], reasons: [...a[i].reasons, ""], analyst_modified: true }; setStocks(a); }}
              style={{ fontSize: 10, color: "#3182ce", background: "none", border: "none", cursor: "pointer" }}>+ 理由</button>
          )}
        </div>
      ))}
    </div>
  );
}
