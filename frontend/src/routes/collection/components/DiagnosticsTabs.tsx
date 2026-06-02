/** P4-1A: 诊断详情 Tab 面板 — 日志/DOM/Stream。Review Queue 已迁移到独立 tab。 */
import { Descriptions, Space, Table, Tabs, Tag } from "antd";
import type { CSSProperties } from "react";
import type { NewChainRealtimeStatus } from "../../../lib/api";

interface Props {
  mergedLogs: string[];
  jyhfLogs: string[];
  showLogPanels?: boolean;
  stackStatus: NewChainRealtimeStatus | null;
}

type LogSection = {
  title: string;
  lines: string[];
};

type LogFileGroup = {
  fileName: string;
  category: "采集" | "LLM" | "匹配" | "其他";
  lines: string[];
};

type JyhfLogGroup = {
  title: string;
  lines: string[];
};

function isSectionHeader(line: string): boolean {
  return /^── .+ ──$/.test(line.trim());
}

function isFileHeader(line: string): boolean {
  return /^──\s+.+\s+──$/.test(line.trim()) && !line.includes("运行日志 (");
}

function classifyCollectorFile(fileName: string): LogFileGroup["category"] {
  const name = fileName.toLowerCase();
  if (name.includes("akshare") || name.includes("raw_news") || name.includes("db_collector")) return "采集";
  if (name.includes("decision") || name.includes("brief_rebuild")) return "LLM";
  if (name.includes("intel")) return "匹配";
  return "其他";
}

function severityStyle(line: string): CSSProperties {
  const text = line.toLowerCase();
  if (
    text.includes("[error]") ||
    text.includes("error") ||
    text.includes("exception") ||
    text.includes("traceback") ||
    text.includes("failed") ||
    text.includes("timeout") ||
    text.includes("404") ||
    text.includes("blocked")
  ) {
    return { color: "#fca5a5", background: "rgba(239,68,68,0.08)" };
  }
  if (
    text.includes("[warn]") ||
    text.includes(" warning") ||
    text.includes("warn ") ||
    text.includes("stale") ||
    text.includes("retry") ||
    text.includes("degraded")
  ) {
    return { color: "#fcd34d", background: "rgba(245,158,11,0.08)" };
  }
  if (
    text.includes("ok") ||
    text.includes("success") ||
    text.includes("running") ||
    text.includes("正常") ||
    text.includes("就绪") ||
    text.includes("通过")
  ) {
    return { color: "#86efac" };
  }
  return { color: "#cbd5e1" };
}

function splitSections(lines: string[]): LogSection[] {
  const sections: LogSection[] = [];
  let currentTitle = "日志";
  let currentLines: string[] = [];
  for (const line of lines) {
    if (isSectionHeader(line)) {
      if (currentLines.length || currentTitle !== "日志") {
        sections.push({ title: currentTitle, lines: currentLines });
      }
      currentTitle = line.trim().slice(2, -2).trim();
      currentLines = [];
      continue;
    }
    if (!line && currentLines.length === 0) continue;
    currentLines.push(line);
  }
  if (currentLines.length || currentTitle !== "日志") {
    sections.push({ title: currentTitle, lines: currentLines });
  }
  return sections;
}

function splitCollectorFiles(lines: string[]): LogFileGroup[] {
  const groups: LogFileGroup[] = [];
  let currentFileName = "";
  let currentLines: string[] = [];
  for (const line of lines) {
    if (isFileHeader(line)) {
      if (currentFileName) {
        groups.push({
          fileName: currentFileName,
          category: classifyCollectorFile(currentFileName),
          lines: currentLines,
        });
      }
      currentFileName = line.trim().slice(2, -2).trim();
      currentLines = [];
      continue;
    }
    if (!currentFileName) continue;
    if (line !== "") {
      currentLines.push(line);
    }
  }
  if (currentFileName) {
    groups.push({
      fileName: currentFileName,
      category: classifyCollectorFile(currentFileName),
      lines: currentLines,
    });
  }
  return groups;
}

function classifyJyhfLine(line: string): string {
  const text = line.toLowerCase();
  if (text.includes("[error]") || text.includes("error") || text.includes("exception") || text.includes("traceback") || text.includes("failed")) {
    return "异常";
  }
  if (text.includes("[warn]") || text.includes("warn") || text.includes("retry") || text.includes("stale") || text.includes("degraded")) {
    return "告警";
  }
  if (text.includes("cdp") || text.includes("9223") || text.includes("browser") || text.includes("连接") || text.includes("service")) {
    return "连接";
  }
  if (text.includes("collector") || text.includes("采集") || text.includes("capture") || text.includes("event")) {
    return "采集";
  }
  if (text.includes("llm") || text.includes("decision") || text.includes("match") || text.includes("theme")) {
    return "LLM/匹配";
  }
  return "其他";
}

function splitJyhfGroups(lines: string[]): JyhfLogGroup[] {
  const order = ["异常", "告警", "连接", "采集", "LLM/匹配", "其他"];
  const buckets = new Map<string, string[]>();
  for (const line of lines) {
    const group = classifyJyhfLine(line);
    const arr = buckets.get(group) ?? [];
    arr.push(line);
    buckets.set(group, arr);
  }
  return order
    .filter((title) => (buckets.get(title)?.length ?? 0) > 0)
    .map((title) => ({ title, lines: buckets.get(title) ?? [] }));
}

function renderLogLine(line: string, key: string) {
  const style = severityStyle(line);
  const isHeader = isSectionHeader(line) || isFileHeader(line);
  return (
    <div
      key={key}
      className="collection-log-line"
      style={{
        ...style,
        fontWeight: isHeader ? 700 : 400,
        padding: isHeader ? "2px 0" : undefined,
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
      }}
    >
      {line}
    </div>
  );
}

function renderSection(section: LogSection, sectionIndex: number) {
  if (section.title.startsWith("运行日志 (采集/LLM/匹配")) {
    const fileGroups = splitCollectorFiles(section.lines);
    const categoryOrder: Array<LogFileGroup["category"]> = ["采集", "LLM", "匹配", "其他"];
    const grouped = categoryOrder
      .map((category) => ({
        category,
        files: fileGroups.filter((group) => group.category === category),
      }))
      .filter((group) => group.files.length > 0);

    return (
      <details key={`section-${sectionIndex}`} open style={{ marginBottom: 8 }}>
        <summary style={{ cursor: "pointer", color: "#f8fafc", fontWeight: 700, marginBottom: 6 }}>
          {section.title} <span style={{ color: "#64748b", fontWeight: 400 }}>({fileGroups.length} 个来源)</span>
        </summary>
        <div style={{ paddingLeft: 12, borderLeft: "1px solid rgba(148,163,184,0.16)" }}>
          {grouped.map((group) => (
            <details key={group.category} open style={{ marginBottom: 8 }}>
              <summary style={{ cursor: "pointer", color: "#cbd5e1", fontWeight: 600, marginBottom: 4 }}>
                {group.category} <span style={{ color: "#64748b", fontWeight: 400 }}>({group.files.length})</span>
              </summary>
              <div style={{ paddingLeft: 12 }}>
                {group.files.map((file) => (
                  <details key={file.fileName} open style={{ marginBottom: 6 }}>
                    <summary style={{ cursor: "pointer", color: "#94a3b8", fontWeight: 600, marginBottom: 2 }}>
                      {file.fileName} <span style={{ color: "#64748b", fontWeight: 400 }}>({file.lines.length})</span>
                    </summary>
                    <div style={{ paddingLeft: 12 }}>
                      {file.lines.length === 0 ? (
                        <div style={{ color: "#64748b" }}>暂无内容</div>
                      ) : (
                        file.lines.slice(-120).map((line, i) => renderLogLine(line, `${file.fileName}-${i}`))
                      )}
                    </div>
                  </details>
                ))}
              </div>
            </details>
          ))}
        </div>
      </details>
    );
  }

  return (
    <details key={`section-${sectionIndex}`} open={sectionIndex === 0} style={{ marginBottom: 8 }}>
      <summary style={{ cursor: "pointer", color: "#f8fafc", fontWeight: 700, marginBottom: 6 }}>
        {section.title} <span style={{ color: "#64748b", fontWeight: 400 }}>({section.lines.length})</span>
      </summary>
      <div style={{ paddingLeft: 12, borderLeft: "1px solid rgba(148,163,184,0.16)" }}>
        {section.lines.length === 0 ? (
          <div style={{ color: "#64748b" }}>暂无内容</div>
        ) : (
          section.lines.slice(-160).map((line, i) => renderLogLine(line, `${section.title}-${i}`))
        )}
      </div>
    </details>
  );
}

export default function DiagnosticsTabs(props: Props) {
  const {
    mergedLogs, jyhfLogs, showLogPanels = true, stackStatus,
  } = props;

  const streams = stackStatus?.redis_streams ?? {};
  const logSections = splitSections(mergedLogs);
  const jyhfGroups = splitJyhfGroups(jyhfLogs);

  const logTabs = showLogPanels ? [
    {
      key: "run-log",
      label: "运行日志 (采集/LLM/匹配)",
      children: (
        <div className="collection-log-panel" style={{ height: "100%", maxHeight: "none", overflow: "auto", fontFamily: "monospace", fontSize: 11, lineHeight: 1.5 }}>
          {logSections.length === 0 ? (
            <div className="collection-log-line" style={{ color: "#64748b" }}>暂无运行日志...</div>
          ) : (
            logSections.map((section, i) => renderSection(section, i))
          )}
        </div>
      ),
    },
    {
      key: "dom-log",
      label: "DOM日志 (JYHF)",
      children: (
        <div className="collection-log-panel" style={{ height: "100%", maxHeight: "none", overflow: "auto", fontFamily: "monospace", fontSize: 11, lineHeight: 1.5 }}>
          {jyhfGroups.length === 0 ? (
            <div className="collection-log-line" style={{ color: "#64748b" }}>暂无 JYHF DOM 采集日志...</div>
          ) : (
            jyhfGroups.map((group, groupIndex) => (
              <details key={`jyhf-${group.title}-${groupIndex}`} open style={{ marginBottom: 8 }}>
                <summary style={{ cursor: "pointer", color: "#f8fafc", fontWeight: 700, marginBottom: 6 }}>
                  {group.title} <span style={{ color: "#64748b", fontWeight: 400 }}>({group.lines.length})</span>
                </summary>
                <div style={{ paddingLeft: 12, borderLeft: "1px solid rgba(148,163,184,0.16)" }}>
                  {group.lines.slice(-160).map((line, i) => (
                    <div
                      key={`jyhf-${group.title}-${i}`}
                      className="collection-log-line"
                      style={{
                        ...severityStyle(line),
                        whiteSpace: "pre-wrap",
                        wordBreak: "break-word",
                      }}
                    >
                      {line}
                    </div>
                  ))}
                </div>
              </details>
            ))
          )}
        </div>
      ),
    },
  ] : [];

  const tabItems = [
    ...logTabs,
    {
      key: "redis-stream",
      label: "Redis Stream",
      children: (() => {
          const pendingCount = stackStatus?.pending_count ?? 0;
          const deadCount = stackStatus?.dead_letter_count ?? 0;
          const decisionCount = stackStatus?.decision_stream_count ?? 0;
          return (
        <div>
          {/* ── 关键数据流指标 ── */}
          <div style={{
            display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))",
            gap: 8, marginBottom: 10,
          }}>
            <div style={{
              padding: "8px 10px", borderRadius: 6,
              background: pendingCount > 0 ? "rgba(245,158,11,0.08)" : "rgba(255,255,255,0.03)",
              border: pendingCount > 0 ? "1px solid rgba(245,158,11,0.3)" : "1px solid rgba(255,255,255,0.06)",
            }}>
              <div style={{ fontSize: 10, color: "#64748b" }}>📥 Pending</div>
              <div style={{ fontSize: 20, fontWeight: 700, color: pendingCount > 0 ? "#f59e0b" : "#e2e8f0" }}>
                {stackStatus ? pendingCount : "?"}
              </div>
              <div style={{ fontSize: 10, color: "#64748b", marginTop: 1 }}>待导入</div>
            </div>
            <div style={{
              padding: "8px 10px", borderRadius: 6,
              background: deadCount > 0 ? "rgba(239,68,68,0.08)" : "rgba(255,255,255,0.03)",
              border: deadCount > 0 ? "1px solid rgba(239,68,68,0.3)" : "1px solid rgba(255,255,255,0.06)",
            }}>
              <div style={{ fontSize: 10, color: "#64748b" }}>💀 Dead Letter</div>
              <div style={{ fontSize: 20, fontWeight: 700, color: deadCount > 0 ? "#ef4444" : "#e2e8f0" }}>
                {stackStatus ? deadCount : "?"}
              </div>
              <div style={{ fontSize: 10, color: "#64748b", marginTop: 1 }}>死信</div>
            </div>
            <div style={{
              padding: "8px 10px", borderRadius: 6,
              background: "rgba(255,255,255,0.03)",
              border: "1px solid rgba(255,255,255,0.06)",
            }}>
              <div style={{ fontSize: 10, color: "#64748b" }}>📊 Decision</div>
              <div style={{ fontSize: 20, fontWeight: 700, color: "#e2e8f0" }}>
                {stackStatus ? (decisionCount >= 0 ? decisionCount : "?") : "?"}
              </div>
              <div style={{ fontSize: 10, color: "#64748b", marginTop: 1 }}>流长度</div>
            </div>
          </div>

          {/* ── 管道诊断面板 ── */}
          <div style={{
            marginTop: 8, padding: "6px 10px", borderRadius: 6,
            background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.06)",
            fontSize: 12,
          }}>
            <div style={{ fontWeight: 600, marginBottom: 4, color: "#e2e8f0" }}>🔍 管道状态诊断</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "2px 12px" }}>
              {/* Row 1: Collector */}
              <span style={{ color: "#94a3b8" }}>采集进程:</span>
              <span>
                {stackStatus?.raw_news_pid ? (
                  <Tag color="green" style={{ fontSize: 10 }}>PID {stackStatus.raw_news_pid}</Tag>
                ) : (
                  <Tag color="red" style={{ fontSize: 10 }}>未运行</Tag>
                )}
              </span>
              {/* Row 2: Raw Stream */}
              <span style={{ color: "#94a3b8" }}>原始新闻流:</span>
              <span style={{ color: (stackStatus?.redis_streams?.["stream:news:raw"]?.length ?? 0) > 0 ? "#22c55e" : "#ef4444", fontWeight: 600 }}>
                {(stackStatus?.redis_streams?.["stream:news:raw"]?.length ?? 0) > 0 ? "有数据" : "空"}
              </span>
              {/* Row 3: Structured Stream */}
              <span style={{ color: "#94a3b8" }}>结构化事件:</span>
              <span style={{ color: (stackStatus?.redis_streams?.["stream:events:structured"]?.length ?? 0) > 0 ? "#22c55e" : "#ef4444", fontWeight: 600 }}>
                {(stackStatus?.redis_streams?.["stream:events:structured"]?.length ?? 0) > 0 ? "有数据" : "空"}
              </span>
              {/* Row 4: Qwen Dedup */}
              <span style={{ color: "#94a3b8" }}>Qwen 去重:</span>
              <span>
                {stackStatus?.qwen_dedup_ready ? (
                  <Tag color="green" style={{ fontSize: 10 }}>就绪 ({stackStatus.qwen_dedup_calls ?? 0} calls)</Tag>
                ) : (
                  <Tag color="orange" style={{ fontSize: 10 }}>预热中 / 未就绪</Tag>
                )}
              </span>
              {/* Row 5: Dedup Rate */}
              <span style={{ color: "#94a3b8" }}>去重过滤:</span>
              <span style={{ color: "#e2e8f0" }}>
                硬保护:{stackStatus?.hard_protect_count ?? 0} · 语义去重:{stackStatus?.semantic_dedup_count ?? 0} · 去重skip:{stackStatus?.news_dedup_skipped ?? 0}
              </span>
              {/* Row 6: LLM Filter */}
              <span style={{ color: "#94a3b8" }}>LLM 预过滤:</span>
              <span style={{ color: (stackStatus?.prefilter_skipped ?? 0) > 0 ? "#f59e0b" : "#22c55e" }}>
                跳过:{stackStatus?.prefilter_skipped ?? 0} · 通过:{stackStatus?.news_published_total ?? 0}
              </span>
              {/* Row 7: Overall status */}
              <span style={{ color: "#94a3b8" }}>整体状态:</span>
              <span>
                {(() => {
                  const rawLen = stackStatus?.redis_streams?.["stream:news:raw"]?.length ?? 0;
                  const structLen = stackStatus?.redis_streams?.["stream:events:structured"]?.length ?? 0;
                  const collectorRunning = Boolean(stackStatus?.raw_news_pid);
                  if (!collectorRunning) return <Tag color="red" style={{ fontSize: 10 }}>采集未启动</Tag>;
                  if (rawLen === 0) return <Tag color="orange" style={{ fontSize: 10 }}>无原始新闻</Tag>;
                  if (structLen === 0) return <Tag color="orange" style={{ fontSize: 10 }}>过滤中/未产出</Tag>;
                  return <Tag color="green" style={{ fontSize: 10 }}>正常产出</Tag>;
                })()}
              </span>
            </div>
          </div>

          <Descriptions size="small" column={2} style={{ marginTop: 8 }}>
            <Descriptions.Item label="Qwen Dedup">
              {stackStatus?.qwen_dedup_ready ? <Tag color="green">就绪</Tag> : <Tag>未就绪</Tag>}
            </Descriptions.Item>
            <Descriptions.Item label="Qwen Calls">{stackStatus?.qwen_dedup_calls ?? 0}</Descriptions.Item>
            <Descriptions.Item label="Prefilter Skipped">{stackStatus?.prefilter_skipped ?? 0}</Descriptions.Item>
            <Descriptions.Item label="Dedup Skipped">{stackStatus?.news_dedup_skipped ?? 0}</Descriptions.Item>
            <Descriptions.Item label="Hard Protect">{stackStatus?.hard_protect_count ?? 0}</Descriptions.Item>
            <Descriptions.Item label="News Published">{stackStatus?.news_published_total ?? 0}</Descriptions.Item>
          </Descriptions>
          <div style={{ marginTop: 8 }}>
            <span className="metric-label section-title">Stream 长度</span>
            {Object.keys(streams).length === 0 ? (
              <div style={{ color: "#64748b", fontSize: 12 }}>暂无数据</div>
            ) : (
              Object.entries(streams).map(([name, info]) => {
                const len = info?.length ?? 0;
                const color = len > 5000 ? "#ef4444" : len > 1000 ? "#eab308" : "#22c55e";
                return (
                  <div key={name} style={{ fontSize: 12, marginBottom: 2 }}>
                    <span style={{ color: "#64748b" }}>{name}</span>
                    {" "}<strong style={{ color }}>{len}</strong>
                    {" groups="}<span style={{ color: "#94a3b8" }}>{info?.groups ?? 0}</span>
                  </div>
                );
              })
            )}
          </div>
        </div>
          );
        })(),
    },
  ];

  return <Tabs items={tabItems} size="small" />;
}
