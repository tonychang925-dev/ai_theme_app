/** 实时采集页日志面板：运行日志 (采集/LLM/匹配) + DOM日志 (JYHF) */
import { Tabs } from "antd";
import type { CSSProperties } from "react";
import type { JyhfAuctionStatus, NewChainRealtimeStatus } from "../../../lib/api";

type LogSection = {
  title: string;
  lines: string[];
};

type JyhfLogGroup = {
  title: string;
  lines: string[];
};

interface Props {
  mergedLogs: string[];
  jyhfLogs: string[];
  stackStatus?: NewChainRealtimeStatus | null;
  auctionStatus?: JyhfAuctionStatus | null;
  auctionLogs?: string[];
  collectorLogWindowLabel?: string;
}

function isSectionHeader(line: string): boolean {
  return /^── .+ ──$/.test(line.trim());
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
  const isHeader = isSectionHeader(line);
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

function renderLifecycleState(stackStatus?: NewChainRealtimeStatus | null) {
  const lines = stackStatus
    ? [
        `realtime: ${stackStatus.running ? (stackStatus.running_verified ? "running" : "degraded") : "stopped"}`,
        `verified: ${stackStatus.running_verified ?? "?"}  source: ${stackStatus.status_source ?? "?"}`,
        `run_id: ${stackStatus.run_id || "-"}`,
        `PID — raw: ${stackStatus.raw_news_pid ?? "-"}  dec: ${stackStatus.decision_pid ?? "-"}  db: ${stackStatus.db_collector_pid ?? "-"}`,
        `started_at: ${stackStatus.started_at ?? "-"}`,
        `pending: ${stackStatus.pending_count ?? 0}  dead_letter: ${stackStatus.dead_letter_count ?? 0}`,
      ]
    : ["暂无生命周期状态"];

  return (
    <section className="collection-log-panel" style={{ height: "100%", maxHeight: "none", overflow: "auto", fontFamily: "monospace", fontSize: 11, lineHeight: 1.5 }}>
      <div style={{ marginBottom: 8, color: "#e2e8f0", fontWeight: 700 }}>生命周期状态</div>
      {lines.map((line, idx) => renderLogLine(line, `lifecycle-${idx}`))}
    </section>
  );
}

function renderAuctionState(auctionStatus?: JyhfAuctionStatus | null, auctionLogs?: string[]) {
  const statusLines = auctionStatus
    ? [
        `running: ${auctionStatus.running}`,
        `state: ${auctionStatus.state}`,
        `trade_date: ${auctionStatus.trade_date ?? "-"}`,
        `candidate_date: ${auctionStatus.candidate_date ?? "-"}`,
        `rounds: ${auctionStatus.rounds}  points: ${auctionStatus.points}`,
        `pid: ${auctionStatus.pid ?? "-"}`,
        auctionStatus.last_error ? `last_error: ${auctionStatus.last_error}` : null,
      ].filter(Boolean) as string[]
    : ["暂无竞价采集状态"];

  const logLines = auctionLogs?.length ? auctionLogs : [];
  const hasActivity = auctionStatus?.running || logLines.length > 0;

  return (
    <section className="collection-log-panel" style={{ height: "100%", maxHeight: "none", overflow: "auto", fontFamily: "monospace", fontSize: 11, lineHeight: 1.5 }}>
      <div style={{ marginBottom: 8, color: "#e2e8f0", fontWeight: 700 }}>
        JYHF 竞价采集{hasActivity ? ` (${logLines.length} 行)` : ""}
      </div>
      <div style={{ marginBottom: 4, color: "#64748b" }}>── 状态 ──</div>
      {statusLines.map((line, idx) => renderLogLine(line, `auction-status-${idx}`))}
      {logLines.length > 0 && (
        <>
          <div style={{ marginTop: 8, marginBottom: 4, color: "#64748b" }}>── 运行日志 ──</div>
          {logLines.map((line, idx) => renderLogLine(line, `auction-log-${idx}`))}
        </>
      )}
    </section>
  );
}

export default function CollectorLogPanels({ mergedLogs, jyhfLogs, stackStatus, auctionStatus, auctionLogs, collectorLogWindowLabel }: Props) {
  const logSections = splitSections(mergedLogs).filter((section) =>
    !section.title.startsWith("操作日志") &&
    !section.title.startsWith("Redis Stream 指标") &&
    !section.title.startsWith("生命周期状态") &&
    !section.title.startsWith("JYHF 竞价采集")
  );
  const jyhfGroups = splitJyhfGroups(jyhfLogs);

  const collectorLogContent = (
    <section className="collection-log-panel" style={{ height: "100%", maxHeight: "none", overflow: "auto", fontFamily: "monospace", fontSize: 11, lineHeight: 1.5 }}>
      <div style={{ marginBottom: 8, color: "#e2e8f0", fontWeight: 700 }}>
        运行日志 (采集/LLM/匹配){collectorLogWindowLabel ? <span style={{ color: "#64748b", fontWeight: 400 }}> - {collectorLogWindowLabel}</span> : null}
      </div>
      {logSections.length === 0 ? (
        <div className="collection-log-line" style={{ color: "#64748b" }}>暂无运行日志（可切换到更大的时间窗，例如 30 分钟或 24 小时）...</div>
      ) : (
        logSections.map((section, i) => (
          <details key={`section-${i}`} open style={{ marginBottom: 8 }}>
            <summary style={{ cursor: "pointer", color: "#f8fafc", fontWeight: 700, marginBottom: 6 }}>
              {section.title} <span style={{ color: "#64748b", fontWeight: 400 }}>({section.lines.length})</span>
            </summary>
            <div style={{ paddingLeft: 12, borderLeft: "1px solid rgba(148,163,184,0.16)" }}>
              {section.lines.length === 0 ? (
                <div style={{ color: "#64748b" }}>暂无内容</div>
              ) : (
                section.lines.slice(-400).map((line, idx) => renderLogLine(line, `${section.title}-${idx}`))
              )}
            </div>
          </details>
        ))
      )}
    </section>
  );

  const jyhfLogContent = (
    <section className="collection-log-panel" style={{ height: "100%", maxHeight: "none", overflow: "auto", fontFamily: "monospace", fontSize: 11, lineHeight: 1.5 }}>
      <div style={{ marginBottom: 8, color: "#e2e8f0", fontWeight: 700 }}>DOM日志 (JYHF)</div>
      {jyhfGroups.length === 0 ? (
        <div className="collection-log-line" style={{ color: "#64748b" }}>暂无 JYHF DOM 采集日志...</div>
      ) : (
        jyhfGroups.map((group, groupIndex) => (
          <details key={`jyhf-${group.title}-${groupIndex}`} open style={{ marginBottom: 8 }}>
            <summary style={{ cursor: "pointer", color: "#f8fafc", fontWeight: 700, marginBottom: 6 }}>
              {group.title} <span style={{ color: "#64748b", fontWeight: 400 }}>({group.lines.length})</span>
            </summary>
            <div style={{ paddingLeft: 12, borderLeft: "1px solid rgba(148,163,184,0.16)" }}>
              {group.lines.slice(-160).map((line, idx) => (
                <div
                  key={`jyhf-${group.title}-${idx}`}
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
    </section>
  );

  return (
    <Tabs
      size="small"
      defaultActiveKey="collector"
      style={{ height: "100%" }}
      items={[
        { key: "collector", label: "运行日志 (采集/LLM/匹配)", children: collectorLogContent },
        { key: "jyhf", label: "DOM日志 (JYHF)", children: jyhfLogContent },
        { key: "lifecycle", label: "生命周期状态 (6)", children: renderLifecycleState(stackStatus) },
        { key: "auction", label: `JYHF 竞价采集 (${(auctionLogs?.length ?? 0) + 5})`, children: renderAuctionState(auctionStatus, auctionLogs) },
      ]}
    />
  );
}
