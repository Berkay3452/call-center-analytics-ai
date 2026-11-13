"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { getCallById, getCallStatus } from "@/lib/api/client";
import type { CallState, CallStatus } from "@/lib/api/types";
import { Badge } from "@/components/ui";
import { ANALYSIS_STATUS_LABELS, ANALYSIS_STATUS_TONE } from "@/lib/types";

export function analysisIsRunning(state?: CallState) {
  return state === "beklemede" || state === "yaziya_cevriliyor" || state === "isleniyor";
}

type Snapshot = Pick<CallStatus, "call_id" | "state"> & Omit<Partial<CallStatus>, "updated_at"> & { updated_at?: string | null };
type Entry = { status: Snapshot; connectionError?: string };
type Notice = { id: string; message: string };
const NOTICE_TIMEOUT_MS = 5000;
const STORAGE_KEY = "active-call-analyses";
const Context = createContext<{
  entries: Record<string, Entry>;
  observe: (snapshot: Snapshot) => void;
  track: (snapshot: Snapshot) => void;
  announce: (snapshot: Snapshot) => void;
} | null>(null);
/** Yükleme sayfası ilerlemeyi kendi gösterir; bildirimi sayfa bitişi gösterdikten sonra bu sayfa tetikler. */
const UPLOAD_PATH = "/admin/calls/upload";

/** The layout owns polling; closing a dialog or navigating cannot cancel it. */
export function AnalysisTracker({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [entries, setEntries] = useState<Record<string, Entry>>({});
  const [notices, setNotices] = useState<Notice[]>([]);
  const active = useRef(new Set<string>());
  const observed = useRef(new Set<string>());
  const requests = useRef(new Set<string>());
  const generations = useRef(new Map<string, number>());
  const mounted = useRef(false);
  const pathnameRef = useRef(pathname);
  const pending = useRef(new Map<string, Snapshot>());
  const announcedEarly = useRef(new Set<string>());

  const persist = useCallback(() => {
    if (!mounted.current) return;
    try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify([...active.current])); } catch { /* Storage may be unavailable. */ }
  }, []);

  const notifyDone = useCallback(async (id: string, status: Snapshot) => {
    pending.current.delete(id);
    let reason = status.error;
    if (status.state === "kismi" && !reason) {
      try {
        const detail = await getCallById(id);
        reason = Object.values(detail.analysis?.errors ?? {}).join("; ");
      } catch { /* The status response is still authoritative. */ }
    }
    if (!mounted.current) return;
    const message = status.state === "tamam"
      ? "Analiz tamamlandı, sonucu gör"
      : status.state === "kismi"
        ? `Analiz kısmen tamamlandı: ${reason || "Bazı analiz bölümleri üretilemedi."}`
        : `Analiz tamamlanamadı: ${reason || "Sunucu hata nedeni bildirmedi."}`;
    setNotices((previous) => [...previous.filter((notice) => notice.id !== id), { id, message }]);
    router.refresh();
  }, [router]);

  const poll = useCallback(async (id: string) => {
    if (requests.current.has(id)) return;
    requests.current.add(id);
    const generation = generations.current.get(id);
    try {
      const status = await getCallStatus(id);
      if (!mounted.current || generation !== generations.current.get(id)) return;
      setEntries((previous) => ({ ...previous, [id]: { status } }));
      if (analysisIsRunning(status.state)) {
        active.current.add(id);
      } else if (active.current.delete(id)) {
        if (pathnameRef.current === UPLOAD_PATH && !announcedEarly.current.delete(id)) {
          pending.current.set(id, status); // sayfa adımları işaretleyince `announce` gösterir
        } else {
          await notifyDone(id, status);
        }
      }
      persist();
    } catch (error) {
      if (!mounted.current) return;
      // A network failure must never be interpreted as a completed/failed analysis.
      setEntries((previous) => previous[id] ? ({
        ...previous,
        [id]: { ...previous[id], connectionError: error instanceof Error ? error.message : "Durum alınamadı; yeniden deneniyor." },
      }) : previous);
      persist();
    } finally {
      requests.current.delete(id);
    }
  }, [persist, notifyDone]);

  useEffect(() => {
    pathnameRef.current = pathname;
    if (pathname === UPLOAD_PATH) return;
    for (const [id, status] of pending.current) void notifyDone(id, status);
  }, [pathname, notifyDone]);

  const announce = useCallback((snapshot: Snapshot) => {
    const status = pending.current.get(snapshot.call_id);
    if (status) void notifyDone(snapshot.call_id, status);
    else announcedEarly.current.add(snapshot.call_id); // arka plan takibi henüz bitişi görmedi
  }, [notifyDone]);

  // Bildirim 5 sn sonra kendiliğinden kapanır (kullanıcı ✕ ile de kapatabilir).
  useEffect(() => {
    if (notices.length === 0) return;
    const timers = notices.map((notice) =>
      setTimeout(() => setNotices((previous) => previous.filter((item) => item.id !== notice.id)), NOTICE_TIMEOUT_MS),
    );
    return () => timers.forEach(clearTimeout);
  }, [notices]);

  const track = useCallback((snapshot: Snapshot) => {
    generations.current.set(snapshot.call_id, (generations.current.get(snapshot.call_id) ?? 0) + 1);
    setEntries((previous) => ({ ...previous, [snapshot.call_id]: { status: snapshot } }));
    if (analysisIsRunning(snapshot.state)) active.current.add(snapshot.call_id);
    persist();
    void poll(snapshot.call_id);
  }, [persist, poll]);

  const observe = useCallback((snapshot: Snapshot) => {
    if (observed.current.has(snapshot.call_id)) { void poll(snapshot.call_id); return; }
    observed.current.add(snapshot.call_id);
    track(snapshot);
  }, [track, poll]);

  useEffect(() => {
    mounted.current = true;
    try {
      const ids: unknown = JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? "[]");
      if (Array.isArray(ids)) {
        for (const id of ids) {
          if (typeof id === "string" && id.length < 100) {
            active.current.add(id);
            void poll(id);
          }
        }
      }
    } catch { /* Start with an empty watch list if storage is invalid. */ }
    const timer = setInterval(() => {
      for (const id of active.current) void poll(id);
    }, 4000);
    return () => { mounted.current = false; clearInterval(timer); };
  }, [poll]);

  // Track at the persistent layout too: navigation can happen before a streamed
  // detail component hydrates, but its live request must continue in the background.
  useEffect(() => {
    const id = /^\/admin\/calls\/([^/]+)$/.exec(pathname)?.[1];
    if (id && id !== "upload") void poll(id);
  }, [pathname, poll]);

  return (
    <Context.Provider value={{ entries, observe, track, announce }}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 max-w-sm space-y-2" role="region" aria-label="Analiz bildirimleri">
        {notices.map((notice) => (
          <div key={notice.id} role="status" className="flex items-start gap-3 rounded-xl border border-brand-200 bg-white p-4 text-sm text-brand-900 shadow-lg">
            <Link href={`/admin/calls/${notice.id}`} className="underline">{notice.message}</Link>
            <button type="button" aria-label="Bildirimi kapat" onClick={() => setNotices((previous) => previous.filter((item) => item.id !== notice.id))}>✕</button>
          </div>
        ))}
      </div>
    </Context.Provider>
  );
}

export function useTrackAnalysis() {
  const context = useContext(Context);
  if (!context) throw new Error("AnalysisTracker bulunamadı.");
  return context.track;
}

export function useAnnounceAnalysis() {
  const context = useContext(Context);
  if (!context) throw new Error("AnalysisTracker bulunamadı.");
  return context.announce;
}

export function useAnalysis(snapshot: Snapshot) {
  const context = useContext(Context);
  if (!context) throw new Error("AnalysisTracker bulunamadı.");
  const { observe } = context;
  const { call_id, state, stage, updated_at, analysis_version } = snapshot;
  useEffect(() => {
    observe({ call_id, state, stage, updated_at, analysis_version });
  }, [observe, call_id, state, stage, updated_at, analysis_version]);
  return { status: context.entries[call_id]?.status ?? snapshot, connectionError: context.entries[call_id]?.connectionError, track: context.track };
}

export function AnalysisSpinner() {
  return <span aria-hidden="true" className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />;
}

export function analysisStage(status: Snapshot) {
  if (status.stage === "stt" || status.state === "yaziya_cevriliyor") return "Yazıya çevriliyor";
  if (status.stage === "analiz" || status.state === "isleniyor") return "Analiz ediliyor";
  return "Kuyrukta bekliyor";
}

export function AnalysisBanner({ initial }: { initial: Snapshot }) {
  const { status, connectionError } = useAnalysis(initial);
  const [now, setNow] = useState<number | null>(null);
  const running = analysisIsRunning(status.state);
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [running]);
  if (!running) return null;
  const since = status.updated_at ? Date.parse(status.updated_at) : NaN;
  const seconds = now !== null && Number.isFinite(since) ? Math.max(0, Math.floor((now - since) / 1000)) : null;
  return (
    <div role="status" aria-label="Analiz durumu" className="sticky top-0 z-20 flex flex-wrap items-center gap-3 rounded-xl border border-brand-200 bg-brand-50 p-4 text-sm text-brand-900">
      <AnalysisSpinner /> <strong>Analiz sürüyor</strong>
      <span>{analysisStage(status)}</span>
      <span>Bu aşamada geçen süre: {seconds === null ? "Süre bilgisi bekleniyor" : `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`}</span>
      {connectionError && <span role="alert">{connectionError} Durum yeniden sorgulanacak.</span>}
    </div>
  );
}

export function CallAnalysisBadge({ initial }: { initial: Snapshot }) {
  const { status } = useAnalysis(initial);
  return analysisIsRunning(status.state)
    ? <Badge tone="brand"><AnalysisSpinner /> Analiz sürüyor</Badge>
    : <Badge tone={ANALYSIS_STATUS_TONE[status.state as "tamam" | "kismi" | "basarisiz"]}>{ANALYSIS_STATUS_LABELS[status.state as "tamam" | "kismi" | "basarisiz"]}</Badge>;
}
