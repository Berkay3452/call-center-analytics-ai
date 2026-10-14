/**
 * OpenAPI'den türetilen TypeScript tipleri.
 * Kaynak: lib/api/schema.ts
 */

import type { components, paths } from "./schema";

export type { components, paths };

export type Schema = components["schemas"];

// Ortak Tipler
export type CallType = Schema["CallType"];
export type RequestCategory = Schema["RequestCategory"];
export type ServiceMode = Schema["ServiceMode"];
export type Urgency = Schema["Urgency"];
export type NextAction = Schema["NextAction"];
export type SalesOutcomeType = Schema["SalesOutcomeType"];
export type SwitchboardOutcome = Schema["SwitchboardOutcome"];
export type LossReason = Schema["LossReason"];
export type CallState = Schema["CallState"];
export type AnalysisStatus = Schema["AnalysisStatus"];
export type Speaker = Schema["Speaker"];
export type QuestionType = Schema["QuestionType"];
export type SourceKind = Schema["SourceKind"];

// Hata Şemaları
export type ErrorBody = Schema["ErrorBody"];
export type ErrorResponse = Schema["ErrorResponse"];

// Sayfalı Yanıtlar
export type Page<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};
export type PageCallListItem = Schema["PageCallListItem"];
export type PageCrmRecordItem = Schema["PageCrmRecordItem"];

// Analiz Çıktıları
export type CallClassification = Schema["CallClassification"];
export type CrmExtraction = Schema["CrmExtraction"];
export type SalesAnalysis = Schema["SalesAnalysis"];
export type CallSummary = Schema["CallSummary"];
export type AgentRun = Schema["AgentRun"];
export type AnalysisOut = Schema["AnalysisOut"];

// Çağrı Modelleri
export type CallListItem = Schema["CallListItem"];
export type TranscriptSegmentOut = Schema["TranscriptSegmentOut"];
export type TranscriptOut = Schema["TranscriptOut"];
export type CallDetail = Schema["CallDetail"];
export type SegmentIn = Schema["SegmentIn"];
export type CallCreate = Schema["CallCreate"];
export type CallAccepted = Schema["CallAccepted"];
export type CallStatus = Schema["CallStatus"];

// CRM ve KPI Modelleri
export type CrmRecordItem = Schema["CrmRecordItem"];
export type CountItem = Schema["CountItem"];
export type DailyCount = Schema["DailyCount"];
export type KpiSummary = Schema["KpiSummary"];

// Asistan & Chat Modelleri
export type SourceRef = Schema["SourceRef"];
export type ChatQuestion = Schema["ChatQuestion"];
export type ChatMessageOut = Schema["ChatMessageOut"];
export type ChatReply = Schema["ChatReply"];
export type ChatSessionOut = Schema["ChatSessionOut"];
export type ChatSessionDetail = Schema["ChatSessionDetail"];

// SSE Olayları
export type StatusEvent = Schema["StatusEvent"];
export type StreamStage = StatusEvent["stage"];
export type DeltaEvent = Schema["DeltaEvent"];
export type DoneEvent = Schema["DoneEvent"];
export type ErrorEvent = Schema["ErrorEvent"];
export type ChatStreamEvent = StatusEvent | DeltaEvent | DoneEvent | ErrorEvent;

