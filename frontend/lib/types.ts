/**
 * Uygulama genelinde kullanılan tip tanımları.
 * Backend hazır olduğunda bu tipler API şeması ile eşleştirilecektir.
 */

// ---------------------------------------------------------------------------
// Rol sistemi
// ---------------------------------------------------------------------------
export type Role = "admin" | "owner";

// ---------------------------------------------------------------------------
// Çağrı verileri
// ---------------------------------------------------------------------------
export type CallStatus = "completed" | "missed" | "ongoing";
export type Sentiment = "positive" | "neutral" | "negative";

export interface Call {
  id: string;
  caller: string;
  /** ISO 8601 tarih-saat */
  startedAt: string;
  /** Saniye cinsinden süre */
  durationSec: number;
  status: CallStatus;
  sentiment: Sentiment;
  transcript: string;
  summary: string;
  /** CRM etiketleri */
  tags: string[];
}

// ---------------------------------------------------------------------------
// KPI kartları
// ---------------------------------------------------------------------------
export interface KpiCard {
  label: string;
  value: number | string;
  unit?: string;
  /** Pozitif sayı artış, negatif sayı düşüş anlamına gelir (%) */
  changePercent?: number;
}

// ---------------------------------------------------------------------------
// CRM önerisi
// ---------------------------------------------------------------------------
export interface CrmSuggestion {
  callId: string;
  caller: string;
  suggestion: string;
  priority: "high" | "medium" | "low";
}

// ---------------------------------------------------------------------------
// Asistan mesajı
// ---------------------------------------------------------------------------
export type MessageRole = "user" | "assistant";

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  /** ISO 8601 */
  timestamp: string;
}
