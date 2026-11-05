import type { CallState, CallStatus } from "./types";
import { mockSeedCalls } from "./mock-seed";

type Run = { step?: number; startedAt: number; analysisVersion: number };
const shared = globalThis as typeof globalThis & { __mockAnalysisRuns?: Map<string, Run> };
export const mockAnalysisRuns = shared.__mockAnalysisRuns ??= new Map<string, Run>();
const running = (state?: string) => state === "beklemede" || state === "yaziya_cevriliyor" || state === "isleniyor";

/** Time-based server fixture: extra observers never speed up the analysis. */
export function readMockAnalysis(id: string): CallStatus {
  const seed = mockSeedCalls.find((call) => call.id === id);
  if (!mockAnalysisRuns.has(id) && running(seed?.state)) {
    mockAnalysisRuns.set(id, { startedAt: Date.now() - (seed?.state === "isleniyor" ? 8000 : 0), analysisVersion: 1 });
  }
  const run = mockAnalysisRuns.get(id);
  let state: CallState = seed?.state ?? "tamam";
  let updatedAt = seed?.updated_at ?? seed?.started_at ?? new Date().toISOString();
  if (run) {
    const elapsed = Date.now() - run.startedAt;
    const offset = elapsed < 4000 ? 0 : elapsed < 8000 ? 4000 : elapsed < 20000 ? 8000 : 20000;
    state = elapsed < 4000 ? "beklemede" : elapsed < 8000 ? "yaziya_cevriliyor" : elapsed < 20000 ? "isleniyor" : id === "mock-slow-failed" ? "basarisiz" : id === "mock-slow-partial" ? "kismi" : "tamam";
    updatedAt = new Date(run.startedAt + offset).toISOString();
  }
  return {
    call_id: id,
    state,
    stage: state === "beklemede" ? "kuyruk" : state === "yaziya_cevriliyor" ? "stt" : state === "isleniyor" ? "analiz" : null,
    analysis_version: run?.analysisVersion ?? 1,
    error: state === "basarisiz" ? "Ses kaydı okunamadı." : state === "kismi" ? "Çağrı sınıflandırma bölümü üretilemedi." : null,
    updated_at: updatedAt,
  };
}

export function startMockAnalysis(id: string) {
  const current = readMockAnalysis(id);
  if (running(current.state)) return { ...current, already_running: true, task_id: null };
  mockAnalysisRuns.set(id, { startedAt: Date.now(), analysisVersion: (current.analysis_version ?? 1) + 1 });
  return { ...readMockAnalysis(id), already_running: false, task_id: null };
}
