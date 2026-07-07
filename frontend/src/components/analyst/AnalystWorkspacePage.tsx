import React, { useState, useEffect, useCallback } from "react";

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
}

interface Workspace {
  trade_date: string;
  is_ai_draft: boolean;
  analyst_finalized: boolean;
  themes: ThemeEntry[];
  watch_groups: WatchGroup[];
  override_count: number;
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
  themes, selectedIdx, onSelect, onAdd, onDelete, onLevelChange,
  watchGroups, onAddGroup, onUpdateGroup, onDeleteGroup, onAddThemeToGroup,
  allThemes,
}: {
  themes: ThemeEntry[]; selectedIdx: number; onSelect: (i: number) => void;
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
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 12px", borderBottom: "1px solid #e2e8f0" }}>
        <strong style={{ fontSize: 14 }}>观察方向</strong>
        <button onClick={onAddGroup}
          style={{ fontSize: 11, padding: "2px 8px", background: "#38a169", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer" }}>
          + 新增方向
        </button>
      </div>

      {/* Watch Groups */}
      <div style={{ padding: "4px 0", borderBottom: "1px solid #e2e8f0" }}>
        {watchGroups.map((g, gi) => (
          <div key={g.id} style={{ padding: "4px 12px", borderBottom: "1px solid #f0f0f0" }}>
            {editingGroup === g.id ? (
              <input autoFocus value={g.name} onChange={(e) => onUpdateGroup({ ...g, name: e.target.value })}
                onBlur={() => setEditingGroup(null)} onKeyDown={(e) => { if (e.key === "Enter") setEditingGroup(null); }}
                style={{ width: "100%", padding: 4, fontSize: 13, fontWeight: 600, borderRadius: 3, border: `2px solid ${g.color}`, background: g.color + "10" }} />
            ) : (
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span onClick={() => setEditingGroup(g.id)}
                  style={{ fontSize: 13, fontWeight: 600, cursor: "pointer", color: g.color, padding: "2px 0" }}>
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
                    style={{ fontSize: 10, color: "#a0aec0", background: "none", border: "none", cursor: "pointer" }}>✕</button>
                </div>
              </div>
            )}
            {/* Show themes in this group */}
            {g.subject_ids.map(sid => {
              const t = allThemes.find(x => x.subject_id === sid);
              if (!t) return null;
              return (
                <div key={sid} onClick={() => { const idx = themes.findIndex(x => x.subject_id === sid); if (idx >= 0) onSelect(idx); }}
                  style={{ fontSize: 11, marginLeft: 12, padding: "2px 6px", cursor: "pointer", color: "#4a5568" }}>
                  · {t.subject_name}
                </div>
              );
            })}
          </div>
        ))}
      </div>

      {/* Ungrouped themes header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 12px", borderBottom: "1px solid #e2e8f0" }}>
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
              background: realIdx === selectedIdx ? "#ebf8ff" : inGroup ? inGroup.color + "08" : "#fff",
              borderLeft: realIdx === selectedIdx ? "3px solid #3182ce" : inGroup ? `3px solid ${inGroup.color}` : "3px solid transparent",
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
      <label style={{ fontSize: 12, fontWeight: 600, color: "#4a5568", display: "block", marginBottom: 3 }}>
        {label} <span style={{ color: statusColor(field), fontSize: 10 }}>{s(field) === "ai" ? "(AI)" : s(field) === "modified" ? "(已修改)" : ""}</span>
      </label>
      {rows > 1 ? (
        <textarea value={(theme as any)[field] || ""} onChange={(e) => update(field, e.target.value)} rows={rows}
          style={{ width: "100%", padding: 6, fontSize: 13, borderRadius: 4, border: `1px solid ${statusColor(field)}`, resize: "vertical" }} />
      ) : (
        <input value={(theme as any)[field] || ""} onChange={(e) => update(field, e.target.value)}
          style={{ width: "100%", padding: 6, fontSize: 13, borderRadius: 4, border: `1px solid ${statusColor(field)}` }} />
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
          <label style={{ fontSize: 12, fontWeight: 600, color: "#4a5568", display: "block", marginBottom: 3 }}>炒作风格</label>
          <select value={theme.trading_style || ""} onChange={(e) => update("trading_style", e.target.value)}
            style={{ width: "100%", padding: 6, fontSize: 13, borderRadius: 4, border: `1px solid ${statusColor("trading_style")}` }}>
            <option value="">—</option>
            {TRADING_STYLES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div>
          <label style={{ fontSize: 12, fontWeight: 600, color: "#4a5568", display: "block", marginBottom: 3 }}>
            多头辨识度 {theme.long_identifiability.toFixed(1)}
          </label>
          <input type="range" min="0" max="1" step="0.1" value={theme.long_identifiability}
            onChange={(e) => update("long_identifiability", parseFloat(e.target.value))}
            style={{ width: "100%" }} />
        </div>
        <div>
          <label style={{ fontSize: 12, fontWeight: 600, color: "#4a5568", display: "block", marginBottom: 3 }}>
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
        <label style={{ fontSize: 12, fontWeight: 600, color: "#4a5568", display: "block", marginBottom: 3 }}>事件刺激</label>
        {(theme.event_stimuli.length === 0 ? [""] : theme.event_stimuli).map((ev: string, i: number) => (
          <div key={i} style={{ display: "flex", gap: 4, marginBottom: 4 }}>
            <input value={ev} onChange={(e) => {
              const arr = [...theme.event_stimuli];
              arr[i] = e.target.value;
              update("event_stimuli", arr);
            }} placeholder="事件描述"
              style={{ flex: 1, padding: 4, fontSize: 13, borderRadius: 4, border: "1px solid #e2e8f0" }} />
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
  const updatePool = (poolType: "leaders" | "bull_pool" | "bear_pool", stocks: StockEntry[]) => {
    onChange({ ...theme, [poolType]: stocks, is_ai_draft: false });
  };

  const PoolSection = ({ title, poolType, color }: { title: string; poolType: "leaders" | "bull_pool" | "bear_pool"; color: string }) => {
    const stocks: StockEntry[] = theme[poolType];
    return (
      <div style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <label style={{ fontSize: 13, fontWeight: 600, color }}>{title} ({stocks.length})</label>
          <button onClick={() => updatePool(poolType, [...stocks, newStock()])}
            style={{ fontSize: 11, padding: "2px 8px", background: color, color: "#fff", border: "none", borderRadius: 3, cursor: "pointer" }}>+</button>
        </div>
        {stocks.map((s, i) => (
          <div key={i} style={{ padding: 8, marginBottom: 6, background: "#f7fafc", borderRadius: 4, border: "1px solid #e2e8f0" }}>
            <div style={{ display: "flex", gap: 6, marginBottom: 4 }}>
              <input value={s.stock_code} onChange={(e) => {
                const arr = [...stocks]; arr[i] = { ...arr[i], stock_code: e.target.value, analyst_modified: true };
                updatePool(poolType, arr);
              }} placeholder="代码" style={{ width: 70, padding: 4, fontSize: 12, borderRadius: 3, border: "1px solid #e2e8f0" }} />
              <input value={s.stock_name} onChange={(e) => {
                const arr = [...stocks]; arr[i] = { ...arr[i], stock_name: e.target.value, analyst_modified: true };
                updatePool(poolType, arr);
              }} placeholder="名称" style={{ width: 80, padding: 4, fontSize: 12, borderRadius: 3, border: "1px solid #e2e8f0" }} />
              <select value={s.role} onChange={(e) => {
                const arr = [...stocks]; arr[i] = { ...arr[i], role: e.target.value, analyst_modified: true };
                updatePool(poolType, arr);
              }} style={{ flex: 1, padding: 4, fontSize: 12, borderRadius: 3, border: "1px solid #e2e8f0" }}>
                {STOCK_ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
              <button onClick={() => updatePool(poolType, stocks.filter((_: any, j: number) => j !== i))}
                style={{ fontSize: 12, color: "#e53e3e", background: "none", border: "none", cursor: "pointer" }}>✕</button>
            </div>
            {/* Reasons */}
            {(s.reasons.length === 0 ? [""] : s.reasons).map((r: string, j: number) => (
              <div key={j} style={{ display: "flex", gap: 4, marginBottom: 2 }}>
                <input value={r} onChange={(e) => {
                  const arr = [...stocks];
                  const reasons = [...arr[i].reasons];
                  reasons[j] = e.target.value;
                  arr[i] = { ...arr[i], reasons, analyst_modified: true };
                  updatePool(poolType, arr);
                }} placeholder={`理由 ${j + 1}`}
                  style={{ flex: 1, padding: 3, fontSize: 11, borderRadius: 3, border: "1px solid #e2e8f0" }} />
                <button onClick={() => {
                  const arr = [...stocks];
                  arr[i] = { ...arr[i], reasons: arr[i].reasons.filter((_: any, k: number) => k !== j), analyst_modified: true };
                  updatePool(poolType, arr);
                }} style={{ fontSize: 11, color: "#a0aec0", background: "none", border: "none", cursor: "pointer" }}>✕</button>
              </div>
            ))}
            {s.reasons.length < 5 && (
              <button onClick={() => {
                const arr = [...stocks];
                arr[i] = { ...arr[i], reasons: [...arr[i].reasons, ""], analyst_modified: true };
                updatePool(poolType, arr);
              }} style={{ fontSize: 10, color: "#3182ce", background: "none", border: "none", cursor: "pointer" }}>
                + 添加理由 ({s.reasons.length}/5)
              </button>
            )}
          </div>
        ))}
      </div>
    );
  };

  return (
    <div style={{ padding: 12, overflow: "auto", height: "100%" }}>
      <PoolSection title="龙头 / 潜在龙头 / 中军" poolType="leaders" color="#e53e3e" />
      <PoolSection title="多头池 Bull Pool" poolType="bull_pool" color="#38a169" />
      <PoolSection title="空头池 Bear Pool" poolType="bear_pool" color="#dd6b20" />
    </div>
  );
}

// ── Main Page ──

export function AnalystWorkspacePage() {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [saving, setSaving] = useState(false);
  const [savedMsg, setSavedMsg] = useState("");

  const tradeDate = new Date().toISOString().slice(0, 10);
  const [dateInput, setDateInput] = useState(tradeDate);

  const fetchWorkspace = useCallback(async (d: string) => {
    setLoading(true);
    try {
      const resp = await fetch(`/api/v1/analyst-workspace/${d}`);
      if (!resp.ok) throw new Error(`${resp.status}`);
      const data = await resp.json();
      setWorkspace(data);
      setSelectedIdx(0);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchWorkspace(dateInput); }, [dateInput, fetchWorkspace]);

  const handleSave = async () => {
    if (!workspace) return;
    setSaving(true);
    try {
      const resp = await fetch(`/api/v1/analyst-workspace/${dateInput}/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(workspace),
      });
      if (!resp.ok) throw new Error(`${resp.status}`);
      const result = await resp.json();
      setSavedMsg(`已保存 (${result.overrides_recorded} 条修改记录)`);
      setTimeout(() => setSavedMsg(""), 3000);
    } catch { /* ignore */ } finally { setSaving(false); }
  };

  if (loading) return <div style={{ padding: 24 }}>加载中…</div>;
  if (error) return <div style={{ padding: 24, color: "#e53e3e" }}>Error: {error} <button onClick={() => fetchWorkspace(dateInput)}>重试</button></div>;
  if (!workspace) return <div style={{ padding: 24 }}>无数据</div>;

  const theme = workspace.themes[selectedIdx] || newTheme();

  const updateTheme = (t: ThemeEntry) => {
    const themes = [...workspace.themes];
    themes[selectedIdx] = t;
    setWorkspace({ ...workspace, themes, is_ai_draft: false });
  };

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column" }}>
      {/* Top bar */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 16px", borderBottom: "1px solid #e2e8f0", background: "#f7fafc" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <h2 style={{ margin: 0, fontSize: 18 }}>📊 分析师工作台</h2>
          <input type="date" value={dateInput} onChange={(e) => setDateInput(e.target.value)}
            style={{ padding: "4px 8px", fontSize: 14, borderRadius: 4, border: "1px solid #cbd5e0" }} />
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontSize: 13, color: "#718096" }}>
            {workspace.themes.length} 题材
            {workspace.override_count > 0 && ` · ${workspace.override_count} 修改`}
            {workspace.analyst_finalized && " · 已定稿"}
          </span>
          {savedMsg && <span style={{ fontSize: 12, color: "#38a169" }}>{savedMsg}</span>}
          <button onClick={handleSave} disabled={saving}
            style={{ padding: "8px 20px", fontSize: 14, fontWeight: 600, background: saving ? "#a0aec0" : "#3182ce", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer" }}>
            {saving ? "保存中…" : "保存"}
          </button>
        </div>
      </div>

      {/* Three-panel body */}
      <div style={{ flex: 1, display: "grid", gridTemplateColumns: "220px 1fr 340px", overflow: "hidden" }}>
        {/* Left: Theme list */}
        <div style={{ borderRight: "1px solid #e2e8f0", overflow: "hidden" }}>
          <ThemeWatchList
            themes={workspace.themes}
            allThemes={workspace.themes}
            selectedIdx={selectedIdx}
            onSelect={setSelectedIdx}
            onAdd={() => {
              const themes = [...workspace.themes, newTheme()];
              setWorkspace({ ...workspace, themes, is_ai_draft: false });
              setSelectedIdx(themes.length - 1);
            }}
            onDelete={(i) => {
              const themes = workspace.themes.filter((_, j) => j !== i);
              setWorkspace({ ...workspace, themes });
              setSelectedIdx(Math.min(selectedIdx, themes.length - 1));
            }}
            onLevelChange={(i, lvl) => {
              const themes = [...workspace.themes];
              themes[i] = { ...themes[i], attention_level: lvl, is_ai_draft: false };
              setWorkspace({ ...workspace, themes });
            }}
            watchGroups={workspace.watch_groups || []}
            onAddGroup={() => {
              const groups = [...(workspace.watch_groups || [])];
              const colors = ["#e53e3e", "#3182ce", "#38a169", "#dd6b20", "#805ad5", "#d69e2e"];
              groups.push({
                id: `group_${Date.now()}`, name: "新观察方向", subject_ids: [],
                color: colors[groups.length % colors.length],
              });
              setWorkspace({ ...workspace, watch_groups: groups, is_ai_draft: false });
            }}
            onUpdateGroup={(g) => {
              const groups = (workspace.watch_groups || []).map(x => x.id === g.id ? g : x);
              setWorkspace({ ...workspace, watch_groups: groups, is_ai_draft: false });
            }}
            onDeleteGroup={(id) => {
              const groups = (workspace.watch_groups || []).filter(x => x.id !== id);
              setWorkspace({ ...workspace, watch_groups: groups });
            }}
            onAddThemeToGroup={(groupId, subjectId) => {
              const groups = (workspace.watch_groups || []).map(g =>
                g.id === groupId ? { ...g, subject_ids: [...g.subject_ids, subjectId] } : g
              );
              setWorkspace({ ...workspace, watch_groups: groups, is_ai_draft: false });
            }}
          />
        </div>

        {/* Center: Cognition Editor */}
        <div style={{ borderRight: "1px solid #e2e8f0", overflow: "hidden" }}>
          <div style={{ padding: "8px 12px", borderBottom: "1px solid #e2e8f0", background: theme.is_ai_draft ? "#fefcbf" : "#f0fff4" }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>
              {theme.is_ai_draft ? "🤖 AI 草稿" : "✎ 分析师编辑中"}
            </span>
            {theme.analyst_added && <span style={{ marginLeft: 8, fontSize: 12, color: "#d69e2e" }}>分析师新增</span>}
            {theme.ai_recommended && <span style={{ marginLeft: 8, fontSize: 12, color: "#3182ce" }}>AI 推荐</span>}
          </div>
          <CognitionEditor theme={theme} onChange={updateTheme} />
        </div>

        {/* Right: Stock Pool Editor */}
        <div style={{ overflow: "hidden" }}>
          <div style={{ padding: "8px 12px", borderBottom: "1px solid #e2e8f0" }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>股票池审核</span>
          </div>
          <StockPoolEditor theme={theme} onChange={updateTheme} />
        </div>
      </div>
    </div>
  );
}
