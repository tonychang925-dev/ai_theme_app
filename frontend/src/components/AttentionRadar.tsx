import React, { useEffect, useState, useCallback } from "react";

// ── Types ──

interface SubjectAttentionData {
  subject_id: string;
  subject_name: string;
  attention_score: number;
  level: string;
  ai_level: string;
  event_signals: number;
  price_signals: number;
  capital_signals: number;
  external_signals: number;
  sentiment_signals: number;
  reasons: string[];
  evidence_refs: string[];
  is_analyst_modified: boolean;
}

interface AttentionState {
  trade_date: string;
  subjects: SubjectAttentionData[];
  ignored_subjects: string[];
  override_count: number;
  analyst_reviewed: boolean;
}

// ── Helpers ──

const LEVEL_STARS: Record<string, string> = {
  CRITICAL: "★★★★★",
  HIGH: "★★★★☆",
  MEDIUM: "★★★☆☆",
  LOW: "★★☆☆☆",
  IGNORE: "★☆☆☆☆",
};

const LEVEL_COLORS: Record<string, string> = {
  CRITICAL: "#e53e3e",
  HIGH: "#dd6b20",
  MEDIUM: "#d69e2e",
  LOW: "#38a169",
  IGNORE: "#a0aec0",
};

function formatName(name: string): string {
  // Truncate overly long names
  if (name.length > 30) return name.slice(0, 28) + "…";
  return name;
}

// ── Component ──

export function AttentionRadar() {
  const [state, setState] = useState<AttentionState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tradeDate, setTradeDate] = useState<string>(
    () => new Date().toISOString().slice(0, 10)
  );
  const [expandedSubject, setExpandedSubject] = useState<string | null>(null);
  const [overrides, setOverrides] = useState<Record<string, string>>({});

  const fetchAttention = useCallback(async (date: string) => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`http://127.0.0.1:8090/api/v1/attention/${date}`);
      if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`);
      const data = await resp.json();
      setState(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAttention(tradeDate);
  }, [tradeDate, fetchAttention]);

  const handleOverride = async (
    subjectId: string,
    newLevel: string,
    aiLevel: string
  ) => {
    const prevLevel = overrides[subjectId] || aiLevel;
    setOverrides((prev) => ({ ...prev, [subjectId]: newLevel }));

    try {
      await fetch(`http://127.0.0.1:8090/api/v1/attention/${tradeDate}/override`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          subject_id: subjectId,
          field: "level",
          ai_value: aiLevel,
          analyst_value: newLevel,
          reason: `Analyst changed from ${aiLevel} to ${newLevel}`,
        }),
      });
    } catch {
      // Revert on failure
      setOverrides((prev) => ({ ...prev, [subjectId]: prevLevel }));
    }
  };

  const effectiveLevel = (s: SubjectAttentionData): string => {
    return overrides[s.subject_id] || s.level;
  };

  // ── Filter: show CRITICAL + HIGH default, toggle to show all ──
  const [showAll, setShowAll] = useState(false);
  const subjects = state?.subjects || [];
  const visibleSubjects = showAll
    ? subjects
    : subjects.filter((s) =>
        ["CRITICAL", "HIGH", "MEDIUM"].includes(effectiveLevel(s))
      );

  const ignoredCount = state?.ignored_subjects?.length || 0;

  if (loading) {
    return (
      <div className="attention-radar" style={{ padding: 24 }}>
        <p>Loading attention data…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="attention-radar" style={{ padding: 24, color: "#e53e3e" }}>
        <p>Error: {error}</p>
        <button onClick={() => fetchAttention(tradeDate)}>Retry</button>
      </div>
    );
  }

  return (
    <div className="attention-radar" style={{ padding: 16, maxWidth: 720 }}>
      {/* Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 16,
        }}
      >
        <h2 style={{ margin: 0 }}>Attention Radar</h2>
        <input
          type="date"
          value={tradeDate}
          onChange={(e) => setTradeDate(e.target.value)}
          style={{ padding: "4px 8px", fontSize: 14 }}
        />
      </div>

      {/* Summary bar */}
      {state && (
        <div
          style={{
            display: "flex",
            gap: 16,
            marginBottom: 16,
            fontSize: 13,
            color: "#718096",
          }}
        >
          <span>{subjects.length} subjects scored</span>
          <span>{state.override_count} analyst overrides</span>
          {ignoredCount > 0 && <span>{ignoredCount} ignored</span>}
          <label style={{ cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={showAll}
              onChange={(e) => setShowAll(e.target.checked)}
            />{" "}
            Show all levels
          </label>
        </div>
      )}

      {/* Subject list */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {visibleSubjects.map((s) => {
          const level = effectiveLevel(s);
          const isExpanded = expandedSubject === s.subject_id;
          const isOverridden = overrides[s.subject_id] !== undefined;

          return (
            <div
              key={s.subject_id}
              style={{
                border: `1px solid ${isOverridden ? "#d69e2e" : "#e2e8f0"}`,
                borderRadius: 8,
                padding: 12,
                background: isOverridden ? "#fffff0" : "#fff",
                cursor: "pointer",
              }}
              onClick={() =>
                setExpandedSubject(isExpanded ? null : s.subject_id)
              }
            >
              {/* Main row */}
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                }}
              >
                <div style={{ flex: 1 }}>
                  <span
                    style={{
                      fontSize: 16,
                      color: LEVEL_COLORS[level] || "#a0aec0",
                      marginRight: 8,
                    }}
                  >
                    {LEVEL_STARS[level] || "★☆☆☆☆"}
                  </span>
                  <strong>{formatName(s.subject_name)}</strong>
                  {isOverridden && (
                    <span
                      style={{
                        marginLeft: 8,
                        fontSize: 11,
                        color: "#d69e2e",
                        background: "#fefcbf",
                        padding: "1px 6px",
                        borderRadius: 4,
                      }}
                    >
                      analyst: {level}
                    </span>
                  )}
                </div>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 12,
                    fontSize: 14,
                  }}
                >
                  <span style={{ fontWeight: 600 }}>{s.attention_score}</span>
                  <span style={{ color: "#718096", fontSize: 12 }}>
                    {level}
                  </span>
                </div>
              </div>

              {/* Reasons */}
              {s.reasons.length > 0 && (
                <div
                  style={{
                    marginTop: 6,
                    display: "flex",
                    gap: 8,
                    flexWrap: "wrap",
                  }}
                >
                  {s.reasons.map((r, i) => (
                    <span
                      key={i}
                      style={{
                        fontSize: 12,
                        color: "#4a5568",
                        background: "#edf2f7",
                        padding: "2px 8px",
                        borderRadius: 12,
                      }}
                    >
                      {r}
                    </span>
                  ))}
                </div>
              )}

              {/* Expanded: signal details + override actions */}
              {isExpanded && (
                <div
                  style={{
                    marginTop: 12,
                    padding: 12,
                    background: "#f7fafc",
                    borderRadius: 6,
                  }}
                >
                  {/* Signal bars */}
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "120px 1fr 40px",
                      gap: "4px 8px",
                      fontSize: 13,
                      alignItems: "center",
                    }}
                  >
                    <span>Event</span>
                    <SignalBar value={s.event_signals} />
                    <span style={{ textAlign: "right" }}>{s.event_signals}</span>

                    <span>Price</span>
                    <SignalBar value={s.price_signals} />
                    <span style={{ textAlign: "right" }}>{s.price_signals}</span>

                    <span>Capital</span>
                    <SignalBar value={s.capital_signals} />
                    <span style={{ textAlign: "right" }}>
                      {s.capital_signals}
                    </span>

                    <span>External</span>
                    <SignalBar value={s.external_signals} />
                    <span style={{ textAlign: "right" }}>
                      {s.external_signals}
                    </span>

                    <span>Sentiment</span>
                    <SignalBar value={s.sentiment_signals} />
                    <span style={{ textAlign: "right" }}>
                      {s.sentiment_signals}
                    </span>
                  </div>

                  {/* Override buttons */}
                  <div
                    style={{
                      marginTop: 10,
                      display: "flex",
                      gap: 6,
                      flexWrap: "wrap",
                    }}
                  >
                    <span style={{ fontSize: 12, color: "#718096", marginRight: 4 }}>
                      Override level:
                    </span>
                    {["CRITICAL", "HIGH", "MEDIUM", "LOW", "IGNORE"].map(
                      (lvl) => (
                        <button
                          key={lvl}
                          onClick={(e) => {
                            e.stopPropagation();
                            handleOverride(s.subject_id, lvl, s.ai_level);
                          }}
                          style={{
                            fontSize: 12,
                            padding: "2px 8px",
                            border:
                              level === lvl
                                ? `2px solid ${LEVEL_COLORS[lvl]}`
                                : "1px solid #e2e8f0",
                            borderRadius: 4,
                            background:
                              level === lvl ? LEVEL_COLORS[lvl] + "20" : "#fff",
                            cursor: "pointer",
                            fontWeight: level === lvl ? 600 : 400,
                          }}
                        >
                          {lvl}
                        </button>
                      )
                    )}
                    {isOverridden && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setOverrides((prev) => {
                            const next = { ...prev };
                            delete next[s.subject_id];
                            return next;
                          });
                        }}
                        style={{
                          fontSize: 12,
                          padding: "2px 8px",
                          border: "1px solid #e53e3e",
                          borderRadius: 4,
                          background: "#fff",
                          color: "#e53e3e",
                          cursor: "pointer",
                        }}
                      >
                        Reset
                      </button>
                    )}
                  </div>

                  {/* Evidence refs */}
                  {s.evidence_refs.length > 0 && (
                    <div style={{ marginTop: 10, fontSize: 12, color: "#718096" }}>
                      Evidence: {s.evidence_refs.join(", ")}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {visibleSubjects.length === 0 && (
        <p style={{ color: "#718096" }}>No subjects to display.</p>
      )}
    </div>
  );
}

// ── Mini signal bar ──

function SignalBar({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(100, value));
  const color = pct >= 70 ? "#38a169" : pct >= 40 ? "#d69e2e" : "#e53e3e";
  return (
    <div
      style={{
        height: 8,
        background: "#e2e8f0",
        borderRadius: 4,
        overflow: "hidden",
      }}
    >
      <div
        style={{
          width: `${pct}%`,
          height: "100%",
          background: color,
          borderRadius: 4,
          transition: "width 0.3s",
        }}
      />
    </div>
  );
}
