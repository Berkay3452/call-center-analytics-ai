/**
 * Backend API sözleşmesi (#46): uçların döndürdüğü JSON'un birebir tipleri.
 *
 * Kaynak: backend/app/schemas/api.py (+ analysis.py, assistant.py). Alan adları backend ile
 * aynıdır (snake_case); arayüzün kendi tiplerine (lib/types.ts) çevrimi lib/api.ts'te yapılır.
 * Alanlar backend ile uyuşmazsa backend/tests/test_api_contract.py kırılır.
 * Uç listesi ve örnek JSON'lar: docs/api.md, docs/ornekler/api/.
 */

import type {
  AnalysisStatus,
  CallType,
  LossReason,
  NextAction,
  RequestCategory,
  SalesOutcomeType,
  ServiceMode,
  Urgency,
} from "@/lib/types";

/** ISO 8601 tarih-saat (UTC), ör. "2026-10-12T09:05:00Z". */
export type IsoDateTime = string;
/** ISO 8601 gün, ör. "2026-10-12". */
export type IsoDate = string;

export type CallState =
  | "beklemede"
  | "yaziya_cevriliyor"
  | "isleniyor"
  | "tamam"
  | "kismi"
  | "basarisiz";

export type Speaker = "customer" | "rep";

export type SwitchboardOutcome =
  | "randevu_olusturuldu"
  | "usta_yonlendirildi"
  | "kayit_olusturuldu"
  | "bilgi_verildi"
  | "geri_aranacak"
  | "iptal";

export type QuestionType = "gecmis_oneri" | "sayisal" | "kapsam_disi";

export type SourceKind = "service_record" | "boat_note" | "expense" | "subscription";

// ---------------------------------------------------------------------------
// Ortak
// ---------------------------------------------------------------------------
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface ErrorBody {
  code: string;
  message: string;
  details: Record<string, unknown>;
  request_id: string | null;
}

export interface ErrorResponse {
  error: ErrorBody;
}

// ---------------------------------------------------------------------------
// Analiz (agent çıktıları)
// ---------------------------------------------------------------------------
export interface CallClassification {
  call_type: CallType;
  confidence: number;
  reason: string;
}

export interface CrmExtraction {
  request_category: RequestCategory | null;
  location: string | null;
  problem: string | null;
  service_mode: ServiceMode | null;
  urgency: Urgency | null;
  potential_job: string | null;
  next_action: NextAction | null;
  evidence: Record<string, string>;
}

export interface SalesAnalysis {
  outcome: SalesOutcomeType;
  loss_reason: LossReason | null;
  evidence: string | null;
  confidence: number;
}

export interface CallSummary {
  summary: string;
  key_points: string[];
}

export interface AgentRun {
  agent: string;
  status: string;
  attempts: number;
  latency_ms: number;
  error: string | null;
  error_kind: string | null;
  model: string | null;
  prompt_version: string | null;
  tokens_in: number;
  tokens_out: number;
}

export interface AnalysisOut {
  version: number;
  status: AnalysisStatus;
  created_at: IsoDateTime;
  classification: CallClassification | null;
  crm: CrmExtraction | null;
  sales: SalesAnalysis | null;
  summary: CallSummary | null;
  errors: Record<string, string>;
  runs: AgentRun[];
}

// ---------------------------------------------------------------------------
// Çağrılar — GET /calls, GET /calls/{id}
// ---------------------------------------------------------------------------
export interface CallListItem {
  id: string;
  started_at: IsoDateTime;
  duration_s: number | null;
  answer_delay_s: number | null;
  switchboard_outcome: SwitchboardOutcome | null;
  customer_name: string | null;
  boat_name: string | null;
  marina: string | null;
  state: CallState;
  call_type: CallType | null;
  request_category: RequestCategory | null;
  urgency: Urgency | null;
  sales_outcome: SalesOutcomeType | null;
  summary: string | null;
}

export interface TranscriptSegmentOut {
  index: number;
  speaker: Speaker;
  start_ms: number | null;
  end_ms: number | null;
  text: string;
}

export interface TranscriptOut {
  text: string;
  segments: TranscriptSegmentOut[];
}

export interface CallDetail {
  id: string;
  started_at: IsoDateTime;
  duration_s: number | null;
  answer_delay_s: number | null;
  switchboard_outcome: SwitchboardOutcome | null;
  customer_id: string | null;
  boat_id: string | null;
  customer_name: string | null;
  customer_phone: string | null;
  boat_name: string | null;
  boat_model: string | null;
  marina: string | null;
  has_audio: boolean;
  state: CallState;
  error: string | null;
  transcript: TranscriptOut | null;
  analysis: AnalysisOut | null;
}

// ---------------------------------------------------------------------------
// CRM önerileri — GET /crm
// ---------------------------------------------------------------------------
export interface CrmRecordItem {
  call_id: string;
  started_at: IsoDateTime;
  customer_name: string | null;
  boat_name: string | null;
  analysis_version: number;
  request_category: RequestCategory | null;
  location: string | null;
  problem: string | null;
  service_mode: ServiceMode | null;
  urgency: Urgency | null;
  potential_job: string | null;
  next_action: NextAction | null;
  evidence: Record<string, string>;
}

// ---------------------------------------------------------------------------
// Çağrı alma ve analiz — POST /calls, POST /calls/audio, GET /calls/{id}/status
// ---------------------------------------------------------------------------
export interface SegmentIn {
  speaker: Speaker;
  text: string;
  start_ms?: number | null;
  end_ms?: number | null;
}

export interface CallCreate {
  started_at: IsoDateTime;
  duration_s?: number | null;
  answer_delay_s?: number | null;
  switchboard_outcome?: SwitchboardOutcome | null;
  customer_name?: string | null;
  customer_phone?: string | null;
  boat_name?: string | null;
  boat_model?: string | null;
  marina?: string | null;
  transcript?: string | null;
  segments?: SegmentIn[];
}

export interface CallAccepted {
  call_id: string;
  state: CallState;
  task_id: string | null;
}

export interface CallStatus {
  call_id: string;
  state: CallState;
  analysis_version: number | null;
  error: string | null;
  updated_at: IsoDateTime;
}

// ---------------------------------------------------------------------------
// KPI — GET /analytics/summary
// ---------------------------------------------------------------------------
export interface CountItem {
  name: string;
  count: number;
}

export interface DailyCount {
  day: IsoDate;
  count: number;
}

export interface KpiSummary {
  period_start: IsoDate;
  period_end: IsoDate;
  total_calls: number;
  analyzed_calls: number;
  new_customers: number;
  service_requests: number;
  quote_requests: number;
  urgent_requests: number;
  converted_sales: number;
  conversion_rate: number | null;
  lost_by_reason: Partial<Record<LossReason, number>>;
  top_problems: CountItem[];
  busiest_marinas: CountItem[];
  by_category: Partial<Record<RequestCategory, number>>;
  by_urgency: Partial<Record<Urgency, number>>;
  daily_calls: DailyCount[];
  avg_answer_delay_s: number | null;
}

// ---------------------------------------------------------------------------
// Miço AI sohbeti — POST /chat/messages, GET /chat/sessions[/{id}]
// ---------------------------------------------------------------------------
export interface SourceRef {
  kind: SourceKind;
  record_id: string;
  title: string;
  date: IsoDate | null;
  excerpt: string | null;
}

export interface ChatQuestion {
  question: string;
  session_id?: string | null;
}

export interface ChatMessageOut {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: IsoDateTime;
  question_type: QuestionType | null;
  sources: SourceRef[];
  found: boolean;
}

export interface ChatReply {
  session_id: string;
  question: ChatMessageOut;
  answer: ChatMessageOut;
}

export interface ChatSessionOut {
  id: string;
  title: string | null;
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
}

export interface ChatSessionDetail {
  session: ChatSessionOut;
  messages: ChatMessageOut[];
}

// ---------------------------------------------------------------------------
// Akışlı cevap (SSE) — POST /chat/messages/stream
// Her olay: `event: <type>` + `data: <JSON>`. Metin kaynak kontrolünden sonra akar.
// ---------------------------------------------------------------------------
export type StreamStage = "araniyor" | "hazirlaniyor" | "dogrulaniyor";

export interface StatusEvent {
  type: "status";
  stage: StreamStage;
}

export interface DeltaEvent {
  type: "delta";
  text: string;
}

export interface DoneEvent {
  type: "done";
  reply: ChatReply;
}

export interface ErrorEvent {
  type: "error";
  code: string;
  message: string;
}

export type ChatStreamEvent = StatusEvent | DeltaEvent | DoneEvent | ErrorEvent;
