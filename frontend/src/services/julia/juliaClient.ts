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

const DEFAULT_WS_URL = "ws://127.0.0.1:8000/analyst/chat";
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

  private localFallback: boolean;

  constructor(options: JuliaClientOptions = {}) {
    this.wsUrl = options.wsUrl || DEFAULT_WS_URL;
    this.onStateChange = options.onStateChange;
    this.onMessage = options.onMessage;
    this.onError = options.onError;
    this.localFallback = false;
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
          this.localFallback = true;
          this.onError?.("Julia Agent 服务未连接。使用本地分析模式。");
        }
      };
    } catch {
      this.setState("error");
      this.localFallback = true;
      this.onError?.("无法连接到 Julia Agent。");
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
    if (this.localFallback || !this.ws || this.ws.readyState !== WebSocket.OPEN) {
      return this.generateLocalResponse(contextRequest, question);
    }

    return new Promise((resolve) => {
      const timeout = setTimeout(() => {
        this.pendingRequests.delete(question);
        resolve(this.generateLocalResponse(contextRequest, question));
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
   * Local fallback: generate analyst-style responses when Julia Agent is unavailable.
   * Preserves the same JuliaResponse shape so the UI works identically.
   */
  private generateLocalResponse(
    _request: ContextRequest,
    question: string,
  ): JuliaResponse {
    const q = question.toLowerCase();

    if (q.includes("为什么") || q.includes("why")) {
      return {
        intent: "deep_dive",
        text:
          `[本地分析] 基于工作区已有数据，该题材的当前阶段判断与事件刺激基本一致。` +
          `建议关注因果链的完整性——是否所有事件都已反映在盘面，以及是否存在未被纳入分析的反向证据。` +
          `V0.1 本地分析模式，连接 Julia Agent 后可获取完整 EvidenceRef。`,
        evidence_refs: ["workspace:field_overrides", "workspace:event_stimuli"],
        rendered_evidence_links: [
          "工作区:分析师覆盖记录",
          "工作区:事件刺激列表",
        ],
        confidence: 0.55,
        limitations: ["本地分析模式，未连接 Julia Agent。", "仅基于工作区已有数据。", "不包含实时市场证据。"],
        status: "shadow",
      };
    }

    if (q.includes("风险") || q.includes("risk")) {
      return {
        intent: "morning_brief",
        text:
          `[本地分析] 根据当前交易情绪与指数共振判断，主要风险来自：\n` +
          `1. 题材扩散阶段的资金结构变化\n` +
          `2. 事件刺激消退后的认知修正\n` +
          `3. 大盘情绪转向时的流动性压力\n` +
          `具体风险阈值需连接 Julia Agent 获取实时市场状态。`,
        evidence_refs: ["workspace:trader_sentiment", "workspace:index_resonance"],
        rendered_evidence_links: [
          "工作区:交易情绪",
          "工作区:指数共振",
        ],
        confidence: 0.50,
        limitations: ["本地分析模式，未连接 Julia Agent。", "风险判断基于工作区静态数据。"],
        status: "shadow",
      };
    }

    if (q.includes("比") || q.includes("compare") || q.includes("昨天")) {
      return {
        intent: "research",
        text:
          `[本地分析] 对比昨天的看法和今天的实际表现：\n` +
          `工作区已记录 yesterday_view 和 today_actual 字段。` +
          `连接 Julia Agent 后可自动提取偏差模式并进行历史案例匹配。`,
        evidence_refs: ["workspace:yesterday_view", "workspace:today_actual"],
        rendered_evidence_links: [
          "工作区:昨日看法",
          "工作区:今日实际",
        ],
        confidence: 0.48,
        limitations: ["本地分析模式，未连接 Julia Agent。", "对比仅基于工作区字段，未做历史案例匹配。"],
        status: "shadow",
      };
    }

    return {
      intent: "unknown",
      text: "请告诉我你想研究的方向——为什么关注、风险在哪里、还是对比变化？",
      evidence_refs: [],
      rendered_evidence_links: [],
      confidence: 0,
      limitations: [],
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
