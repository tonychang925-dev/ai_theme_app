import React, { useState, useRef, useEffect, useCallback } from "react";
import JuliaMessage from "./JuliaMessage";
import {
  getJuliaClient,
  type JuliaClient,
  type ConnectionState,
} from "../../services/julia/juliaClient";
import {
  contextRequestToQuestion,
  type ContextRequest,
  type JuliaResponse,
} from "../../services/julia/workspaceContextAdapter";

// ── Props ──

interface JuliaCopilotProps {
  /** Current context request to send to Julia */
  contextRequest?: ContextRequest | null;
  /** Whether the parent has requested an analysis */
  isAnalyzing?: boolean;
  /** Called when analysis is complete */
  onAnalysisComplete?: () => void;
}

interface ChatMessage {
  role: "tony" | "julia";
  text: string;
  evidenceRefs?: string[];
  renderedEvidenceLinks?: string[];
  confidence?: number;
  limitations?: string[];
  status?: string;
  timestamp: number;
}

// ── Component ──

export const JuliaCopilot: React.FC<JuliaCopilotProps> = ({
  contextRequest,
  isAnalyzing = false,
  onAnalysisComplete,
}) => {
  const [messages, setMessages] = useState<ChatMessage[]>(() => [
    {
      role: "julia",
      text: "你好 Tony。我是 Julia，你的首席分析师。选择一个题材或观察方向，点击\"为什么关注\"、\"风险评估\"或\"对比变化\"，我会基于工作区数据给出证据驱动的分析。",
      timestamp: Date.now(),
    },
  ]);
  const [inputText, setInputText] = useState("");
  const [connState, setConnState] = useState<ConnectionState>("disconnected");
  const [sending, setSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const clientRef = useRef<JuliaClient | null>(null);

  // ── Init client ──

  useEffect(() => {
    const client = getJuliaClient();
    clientRef.current = client;

    const handleState = (s: ConnectionState) => setConnState(s);
    const handleError = (e: string) => {
      setMessages((prev) => [
        ...prev,
        {
          role: "julia",
          text: e,
          timestamp: Date.now(),
        },
      ]);
    };

    // Re-create with callbacks
    const c = new (client.constructor as any)({
      onStateChange: handleState,
      onError: handleError,
    });
    clientRef.current = c;
    c.connect();

    return () => {
      c.disconnect();
    };
  }, []);

  // ── Auto-scroll ──

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ── Handle incoming context request from parent ──

  useEffect(() => {
    if (!isAnalyzing || !contextRequest) return;

    const question = contextRequestToQuestion(contextRequest);
    handleAsk(question, contextRequest);
  }, [isAnalyzing, contextRequest]);

  // ── Send message ──

  const handleAsk = useCallback(
    async (question: string, req?: ContextRequest | null) => {
      const ctxReq = req || contextRequest;
      if (!question.trim() || sending) return;

      // Add Tony's message
      setMessages((prev) => [
        ...prev,
        { role: "tony", text: question, timestamp: Date.now() },
      ]);
      setSending(true);

      try {
        const client = clientRef.current || getJuliaClient();
        const response: JuliaResponse = await client.ask(
          ctxReq || {
            action: "why",
            object_type: "theme",
            object_id: "",
            object_name: "",
            workspace_snapshot: {
              stage_judgement: "",
              yesterday_view: "",
              today_actual: "",
              event_stimuli: [],
              analyst_notes: "",
            },
            field_overrides_summary: [],
            source: "analyst_workspace",
          },
          question,
        );

        setMessages((prev) => [
          ...prev,
          {
            role: "julia",
            text: response.text,
            evidenceRefs: response.evidence_refs,
            renderedEvidenceLinks: response.rendered_evidence_links,
            confidence: response.confidence,
            limitations: response.limitations,
            status: response.status,
            timestamp: Date.now(),
          },
        ]);
      } catch (err: any) {
        setMessages((prev) => [
          ...prev,
          {
            role: "julia",
            text: `分析请求失败: ${err?.message || "未知错误"}`,
            timestamp: Date.now(),
          },
        ]);
      } finally {
        setSending(false);
        onAnalysisComplete?.();
      }
    },
    [contextRequest, sending, onAnalysisComplete],
  );

  // ── Send from input ──

  const handleSend = () => {
    if (!inputText.trim()) return;
    handleAsk(inputText.trim());
    setInputText("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // ── Render ──

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        background: "#0c1118",
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "8px 14px",
          borderBottom: "1px solid #243040",
          background: "#111720",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: "#66d9ef" }}>
            Julia Copilot
          </span>
          <span
            style={{
              fontSize: 10,
              padding: "1px 6px",
              borderRadius: 3,
              background:
                connState === "connected" ? "#1a3a2c" : "#2a1a1a",
              color:
                connState === "connected" ? "#39ff14" : connState === "connecting" ? "#d69e2e" : "#5a7a8a",
            }}
          >
            {connState === "connected"
              ? "在线"
              : connState === "connecting"
                ? "连接中"
                : "本地分析"}
          </span>
          {sending && (
            <span style={{ fontSize: 10, color: "#d69e2e" }}>分析中...</span>
          )}
        </div>
      </div>

      {/* Messages */}
      <div
        style={{
          flex: 1,
          overflow: "auto",
          padding: "10px 14px",
          display: "flex",
          flexDirection: "column",
        }}
      >
        {messages.map((msg, i) => (
          <JuliaMessage
            key={i}
            role={msg.role}
            text={msg.text}
            evidenceRefs={msg.evidenceRefs}
            renderedEvidenceLinks={msg.renderedEvidenceLinks}
            confidence={msg.confidence}
            limitations={msg.limitations}
            status={msg.status}
          />
        ))}
        {sending && (
          <div style={{ fontSize: 11, color: "#5a7a8a", padding: "8px 0" }}>
            Julia 正在分析...
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div
        style={{
          display: "flex",
          gap: 6,
          padding: "8px 14px",
          borderTop: "1px solid #243040",
          background: "#111720",
        }}
      >
        <input
          type="text"
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="直接问 Julia..."
          disabled={sending}
          style={{
            flex: 1,
            padding: "6px 10px",
            background: "#0c1118",
            border: "1px solid #243040",
            borderRadius: 6,
            color: "#c8d6e5",
            fontSize: 12,
            outline: "none",
          }}
        />
        <button
          onClick={handleSend}
          disabled={sending || !inputText.trim()}
          style={{
            padding: "6px 14px",
            background: sending ? "#1a3a5c" : "#1a3a5c",
            color: sending ? "#5a7a8a" : "#66d9ef",
            border: "1px solid #243040",
            borderRadius: 6,
            cursor: sending ? "default" : "pointer",
            fontSize: 12,
            fontWeight: 600,
            whiteSpace: "nowrap",
          }}
        >
          发送
        </button>
      </div>
    </div>
  );
};

export default JuliaCopilot;
