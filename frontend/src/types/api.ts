/**
 * Types mirroring the backend's OpenAPI schemas exactly.
 * Source of truth: `app.openapi()`, documented in `API.md`. Nothing here is
 * invented; a missing field means the backend does not send it.
 */

export type ChatStatus = "completed" | "awaiting_approval";
export type Decision = "approve" | "edit" | "reject";

/* ---------------------------------------------------------------- auth --- */

export interface TokenRequest {
  api_key: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

/* -------------------------------------------------------------- threads --- */

export interface Thread {
  thread_id: string;
  title: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface ThreadListResponse {
  threads: Thread[];
}

export interface ThreadUpdateRequest {
  /** 1–100 characters. */
  title: string;
}

export interface ThreadMessage {
  /** "user" | "assistant" | "tool" — the backend sends a plain string. */
  role: string;
  content: string;
}

export interface ThreadHistoryResponse {
  thread_id: string;
  messages: ThreadMessage[];
}

/* ----------------------------------------------------------------- chat --- */

export interface ChatRequest {
  /** 1–32000 characters, not blank. */
  message: string;
  /** Omit (or send "") to start a conversation; otherwise an ID you own. */
  thread_id?: string | null;
}

export interface ChatResponse {
  thread_id: string;
  response: string;
  status: ChatStatus;
  title?: string | null;
  approval_id?: string | null;
}

/* ------------------------------------------------------------ approvals --- */

export interface ApprovalSummary {
  approval_id: string;
  thread_id: string;
  action: string;
  title: string;
  arguments: Record<string, unknown>;
  allowed_decisions: string[];
}

export interface ApprovalDetail extends ApprovalSummary {
  tool_call_id?: string | null;
  editable_fields: string[];
  /** e.g. { "selling_price": "integer" } */
  field_types: Record<string, string>;
  /** Pairs like ["$label", "value"] rendered by the approval panel. */
  details: unknown[];
  warnings: unknown[];
  requested_by?: string | null;
  reason?: string | null;
}

export interface DecisionRequest {
  decision: Decision;
  /** Required for `edit`, forbidden otherwise. */
  edited_arguments?: Record<string, unknown> | null;
  /** ≤2000 characters. */
  comment?: string | null;
}

export interface DecisionResponse {
  approval_id: string;
  status: ChatStatus;
  response: string;
  thread_id: string;
  title?: string | null;
  next_approval_id?: string | null;
}

/* ------------------------------------------------------------ documents --- */

export interface DocumentMeta {
  doc_id: string;
  title: string;
  namespace: string;
  size_bytes: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface DocumentListResponse {
  documents: DocumentMeta[];
  namespaces: string[];
}

export interface IngestResponse {
  document: DocumentMeta;
  chunks_created: number;
  skipped: boolean;
  warning?: string | null;
}

/* ---------------------------------------------------------------- chat --- */

export interface HealthResponse {
  status: string;
  application: string;
}

export interface ReadinessResponse {
  status: "ready" | "not_ready";
  application: string;
  checks: {
    database: boolean;
    graph: boolean;
    storage: boolean;
    configuration: boolean;
  };
}

/* ------------------------------------------------------------------ SSE --- */

/** Event names emitted by `api/sse.py`. */
export type SseEventName =
  | "thread"
  | "status"
  | "tool_start"
  | "tool_end"
  | "token"
  | "approval_required"
  | "final"
  | "error";

export interface SseThreadFrame {
  thread_id: string;
}

export interface SseStatusFrame {
  status: string;
}

export interface SseToolStartFrame {
  tool: string;
  arguments?: unknown;
  /** Correlates this call with its `tool_end`; LangGraph runs tools in parallel. */
  tool_call_id?: string | null;
}

export interface SseToolEndFrame {
  tool: string;
  result?: unknown;
  tool_call_id?: string | null;
}

export interface SseTokenFrame {
  content: string;
}

export interface SseApprovalFrame {
  approval_id: string | null;
  thread_id: string;
  action: string;
  title: string;
  arguments: Record<string, unknown>;
  details: unknown[];
  warnings: unknown[];
  allowed_decisions: string[];
}

export interface SseFinalFrame {
  title?: string | null;
}

export interface SseErrorFrame {
  code: "STREAM_ERROR" | "THREAD_BUSY";
  message: string;
}
