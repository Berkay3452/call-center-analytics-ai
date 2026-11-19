/**
 * Canlı transkript durumu (#325): SSE olaylarından konuşma parçaları listesi üretir.
 *
 * Saf mantık (React yok): `lib/use-transcript-stream.ts` olayları buraya besler, birim testi
 * `lib/transcript-live.test.mjs` içindedir. Sunucudan gelen veri güvenilmez sayılır: alanlar
 * doğrulanır, metin kırpılır, liste boyutu sınırlıdır.
 */

export type LiveSpeaker = "rep" | "customer" | "unknown";

export interface LiveSegment {
  seq: number;
  speaker: LiveSpeaker;
  start_ms: number;
  end_ms: number;
  text: string;
}

/** baglaniyor: ilk bağlantı · canli: yayın sürüyor · bitti: yazıya çevirme bitti · hata: STT
 * başarısız · kopuk: bağlantı koptu/yok (kayıtlı metne dönülür) · zaman_asimi: sunucu süresi doldu */
export type LiveStatus = "baglaniyor" | "canli" | "bitti" | "hata" | "kopuk" | "zaman_asimi";

export interface LiveState {
  segments: LiveSegment[];
  status: LiveStatus;
}

export type LiveEvent =
  | { type: "open" }
  | { type: "segment"; data: unknown }
  | { type: "done" }
  | { type: "error" }
  | { type: "timeout" }
  | { type: "disconnect" };

export const MAX_SEGMENTS = 2000;
export const MAX_TEXT_LENGTH = 2000;
export const initialLiveState: LiveState = { segments: [], status: "baglaniyor" };

const SPEAKERS = new Set<LiveSpeaker>(["rep", "customer", "unknown"]);

export function parseSegment(data: unknown): LiveSegment | null {
  if (typeof data !== "object" || data === null) return null;
  const d = data as Record<string, unknown>;
  const { seq, start_ms: start, end_ms: end, text, speaker } = d;
  if (!Number.isInteger(seq) || !Number.isInteger(start) || !Number.isInteger(end)) return null;
  if (typeof text !== "string" || !text.trim()) return null;
  const who =
    typeof speaker === "string" && SPEAKERS.has(speaker as LiveSpeaker)
      ? (speaker as LiveSpeaker)
      : "unknown";
  return {
    seq: seq as number,
    speaker: who,
    start_ms: Math.max(0, start as number),
    end_ms: Math.max(0, end as number),
    text: text.trim().slice(0, MAX_TEXT_LENGTH),
  };
}

export function reduceLive(state: LiveState, event: LiveEvent): LiveState {
  switch (event.type) {
    case "open":
      return state.status === "baglaniyor" || state.status === "kopuk"
        ? { ...state, status: "canli" }
        : state;
    case "segment": {
      const segment = parseSegment(event.data);
      if (!segment) return state;
      // Yeniden bağlanmada aynı olay iki kez gelebilir (seq ile tekilleştirilir).
      if (state.segments.some((s) => s.seq === segment.seq)) return state;
      const segments = [...state.segments, segment]
        .sort((a, b) => a.start_ms - b.start_ms || a.seq - b.seq)
        .slice(-MAX_SEGMENTS);
      const finished =
        state.status === "bitti" || state.status === "hata" || state.status === "zaman_asimi";
      return { segments, status: finished ? state.status : "canli" };
    }
    case "done":
      return { ...state, status: "bitti" };
    case "error":
      return { ...state, status: "hata" };
    case "timeout":
      return { ...state, status: "zaman_asimi" };
    case "disconnect":
      return state.status === "bitti" || state.status === "hata" || state.status === "zaman_asimi"
        ? state
        : { ...state, status: "kopuk" };
  }
}

export interface LiveTurn {
  speaker: LiveSpeaker;
  start_ms: number;
  text: string;
  lastSeq: number;
}

/** Ardışık aynı konuşmacı parçalarını tek baloncukta birleştirir (okunabilirlik). */
export function groupTurns(segments: LiveSegment[]): LiveTurn[] {
  const turns: LiveTurn[] = [];
  for (const s of segments) {
    const last = turns[turns.length - 1];
    if (last && last.speaker === s.speaker) {
      last.text = `${last.text} ${s.text}`;
      last.lastSeq = s.seq;
    } else {
      turns.push({ speaker: s.speaker, start_ms: s.start_ms, text: s.text, lastSeq: s.seq });
    }
  }
  return turns;
}

export const SPEAKER_LABEL: Record<LiveSpeaker, string> = {
  rep: "Temsilci",
  customer: "Müşteri",
  unknown: "Konuşmacı",
};

export function formatMs(ms: number): string {
  const total = Math.floor(ms / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}
