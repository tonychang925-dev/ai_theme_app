/**
 * Julia Agent WebSocket Client
 *
 * Connects ai_theme_app frontend to julia_agent backend at /analyst/chat.
 * Supports WebSocket (primary) with automatic reconnection.
 *
 * Contract: Analyst_Workspace_Context_Binding_v1.0.md (FROZEN)
 */

import type { ContextRequest, JuliaResponse } from "./workspaceContextAdapter";

// ── Config ──

const DEFAULT_WS_URL = "ws://127.0.0.1:8001/analyst/chat";
const RECONNECT_DELAY_MS = 3000;
const MAX_RECONNECT_ATTEMPTS = 5;

// ── Types ──

export type ConnectionState = "disconnected" | "connecting" | "connected" | "error";

export interface JuliaClientOptions {
  wsUrl?: string;
  onStateChange?: (state: ConnectionState) => void;
  onMessage?: (response: JuliaResponse) => void;
  onError?: (error: string) => void;
}

// ── Client ──

export class JuliaClient {
  private ws: WebSocket | null = null;
  private wsUrl: string;
  private state: ConnectionState = "disconnected";
  private pendingRequests: Map<string, (response: JuliaResponse) => void> = new Map();
  private reconnectAttempts = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  private onStateChange?: (state: ConnectionState) => void;
  private onMessage?: (response: JuliaResponse) => void;
  private onError?: (error: string) => void;

  private workspaceOfflineMode: boolean;

  constructor(options: JuliaClientOptions = {}) {
    this.wsUrl = options.wsUrl || DEFAULT_WS_URL;
    this.onStateChange = options.onStateChange;
    this.onMessage = options.onMessage;
    this.onError = options.onError;
    this.workspaceOfflineMode = false;
  }

  // ── Public API ──

  connect(): void {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    this.setState("connecting");

    try {
      this.ws = new WebSocket(this.wsUrl);

      this.ws.onopen = () => {
        this.setState("connected");
        this.reconnectAttempts = 0;
      };

      this.ws.onmessage = (event: MessageEvent) => {
        try {
          const response: JuliaResponse = JSON.parse(event.data);
          this.onMessage?.(response);

          // Deliver to pending request if any
          for (const [_, resolve] of this.pendingRequests) {
            resolve(response);
          }
          this.pendingRequests.clear();
        } catch {
          // Non-JSON message — pass through as text response
          const textResponse: JuliaResponse = {
            intent: "unknown",
            text: event.data,
            evidence_refs: [],
            rendered_evidence_links: [],
            confidence: 0,
            limitations: [],
            status: "shadow",
          };
          this.onMessage?.(textResponse);
        }
      };

      this.ws.onclose = () => {
        this.setState("disconnected");
        this.ws = null;
        this.attemptReconnect();
      };

      this.ws.onerror = () => {
        this.setState("error");
        // Fall back to local/mock if WebSocket fails
        if (this.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
          this.workspaceOfflineMode = true;
          this.onError?.("Julia Agent 服务未连接。使用离线工作区预览模式。");
        }
      };
    } catch {
      this.setState("error");
      this.workspaceOfflineMode = true;
      this.onError?.("无法连接到 Julia Agent。使用离线工作区预览。");
    }
  }

  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.reconnectAttempts = MAX_RECONNECT_ATTEMPTS; // stop reconnect
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.setState("disconnected");
  }

  /**
   * Send a ContextRequest to Julia and return the response.
   */
  async ask(contextRequest: ContextRequest, question: string): Promise<JuliaResponse> {
    if (this.workspaceOfflineMode || !this.ws || this.ws.readyState !== WebSocket.OPEN) {
      return this.generateWorkspaceOfflinePreview(contextRequest, question);
    }

    return new Promise((resolve) => {
      const timeout = setTimeout(() => {
        this.pendingRequests.delete(question);
        resolve(this.generateWorkspaceOfflinePreview(contextRequest, question));
      }, 15000);

      this.pendingRequests.set(question, (response) => {
        clearTimeout(timeout);
        resolve(response);
      });

      this.ws!.send(question);
    });
  }

  getState(): ConnectionState {
    return this.state;
  }

  isConnected(): boolean {
    return this.state === "connected";
  }

  // ── Private ──

  private setState(state: ConnectionState): void {
    this.state = state;
    this.onStateChange?.(state);
  }

  private attemptReconnect(): void {
    if (this.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) return;
    this.reconnectAttempts++;
    this.reconnectTimer = setTimeout(() => {
      this.connect();
    }, RECONNECT_DELAY_MS);
  }

  /**
   * Workspace Offline Preview: display existing workspace fields only.
   *
   * DOES NOT: reason, generate new financial judgments, compute buy/sell logic.
   * ONLY: renders workspace_snapshot fields already present in the ContextRequest.
   */
  private generateWorkspaceOfflinePreview(
    request: ContextRequest,
    _question: string,
  ): JuliaResponse {
    const snap = request.workspace_snapshot;

    const fields: string[] = [];
    if (snap.stage_judgement) fields.push(`阶段判断: ${snap.stage_judgement}`);
    if (snap.attention_level) fields.push(`关注等级: ${snap.attention_level}`);
    if (snap.trader_sentiment) fields.push(`交易情绪: ${snap.trader_sentiment}`);
    if (snap.index_resonance) fields.push(`指数共振: ${snap.index_resonance}`);
    if (snap.yesterday_view) fields.push(`昨日看法: ${snap.yesterday_view}`);
    if (snap.today_actual) fields.push(`今日实际: ${snap.today_actual}`);
    if (snap.analyst_notes) fields.push(`分析师笔记: ${snap.analyst_notes}`);
    if (snap.event_stimuli.length > 0) fields.push(`事件刺激: ${snap.event_stimuli.filter(s => s.trim()).join("、")}`);
    if (snap.old_leaders) fields.push(`老龙头: ${snap.old_leaders}`);
    if (snap.trading_style) fields.push(`交易风格: ${snap.trading_style}`);

    const field_overrides_info = request.field_overrides_summary
      .map(f => `${f.field}: AI→"${f.ai_value}" | 分析师→"${f.analyst_value}"`)
      .join("; ");

    const displayText = fields.length > 0
      ? `[离线工作区预览] ${request.object_name || "当前题材"} 的已有数据：\n\n${fields.join("\n")}${field_overrides_info ? `\n\n分析师覆盖记录: ${field_overrides_info}` : ""}\n\n连接 Julia Agent 后可获取证据驱动的完整分析。`
      : `[离线工作区预览] ${request.object_name || "当前题材"} 暂无工作区数据。选择题材后连接 Julia Agent 获取分析。`;

    const refs: string[] = [];
    if (snap.event_stimuli.length > 0) refs.push("workspace:event_stimuli");
    if (request.field_overrides_summary.length > 0) refs.push("workspace:field_overrides");
    if (snap.analyst_notes) refs.push("workspace:analyst_notes");

    return {
      intent: "unknown",
      text: displayText,
      evidence_refs: refs,
      rendered_evidence_links: refs.map(r => `工作区:${r.replace("workspace:", "")}`),
      confidence: 0,
      limitations: [
        "离线工作区预览模式 — 仅展示已有工作区字段。",
        "不生成新的金融判断、不推理、不计算买卖逻辑。",
        "连接 Julia Agent 后自动切换为在线证据分析。",
      ],
      status: "shadow",
    };
  }
}

// ── Singleton ──

let clientInstance: JuliaClient | null = null;

export function getJuliaClient(): JuliaClient {
  if (!clientInstance) {
    clientInstance = new JuliaClient();
  }
  return clientInstance;
}

export function createJuliaClient(options: JuliaClientOptions): JuliaClient {
  clientInstance?.disconnect();
  clientInstance = new JuliaClient(options);
  return clientInstance;
}
