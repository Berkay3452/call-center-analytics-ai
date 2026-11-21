"use client";

import { useEffect, useReducer } from "react";
import {
  initialLiveState,
  reduceLive,
  type LiveEvent,
  type LiveSegment,
  type LiveState,
} from "@/lib/transcript-live";

const USE_MOCKS = process.env.NEXT_PUBLIC_USE_MOCKS === "true";

/** Sahte mod: gerçek STT yokken pop-up'ı göstermek için senaryolu konuşma (yalnız demo/test). */
const MOCK_DIALOGUE: Array<Pick<LiveSegment, "speaker" | "text">> = [
  { speaker: "rep", text: "Miço Usta, buyurun." },
  { speaker: "customer", text: "Merhaba, Tuzla Marina'da teknem var. Motor çalışıyor ama gaz verdiğimde devir yükselmiyor." },
  { speaker: "rep", text: "Geçmiş olsun. Teknenin adını alabilir miyim?" },
  { speaker: "customer", text: "Rüzgar. Yarın bir usta gelebilir mi?" },
  { speaker: "rep", text: "Usta uygunluğuna bakıp sizi bilgilendireceğiz." },
];
const MOCK_STEP_MS = 600;

export function transcriptStreamUrl(callId: string): string {
  return `/api/backend/calls/${encodeURIComponent(callId)}/transcript/stream`;
}

/**
 * Canlı transkript akışı (#325). `enabled` iken `callId` için SSE'ye bağlanır; bitiş olayında
 * (`done`/`error`/`timeout`) bağlantıyı kendisi kapatır. Tarayıcının `EventSource`u kopmada
 * `Last-Event-ID` ile kaldığı yerden yeniden bağlanır; tekrarlar `seq` ile ayıklanır.
 *
 * Akış kullanılamıyorsa (yetki, ağ, eski sunucu) durum `kopuk` olur; çağıran kayıtlı
 * transkripte düşmelidir, akış çağrı analizini etkilemez.
 */
export function useTranscriptStream(callId: string | null, enabled: boolean): LiveState {
  const [state, dispatch] = useReducer(reduceLive, initialLiveState);

  useEffect(() => {
    if (!callId || !enabled) return;
    const send = (event: LiveEvent) => dispatch(event);

    if (USE_MOCKS) {
      const timers: ReturnType<typeof setTimeout>[] = [];
      timers.push(setTimeout(() => send({ type: "open" }), 100));
      MOCK_DIALOGUE.forEach((line, index) => {
        timers.push(
          setTimeout(
            () =>
              send({
                type: "segment",
                data: {
                  seq: index + 1,
                  speaker: line.speaker,
                  start_ms: index * 2500,
                  end_ms: index * 2500 + 2200,
                  text: line.text,
                },
              }),
            300 + index * MOCK_STEP_MS,
          ),
        );
      });
      timers.push(setTimeout(() => send({ type: "done" }), 300 + MOCK_DIALOGUE.length * MOCK_STEP_MS + 200));
      return () => timers.forEach(clearTimeout);
    }

    const source = new EventSource(transcriptStreamUrl(callId));
    const parse = (raw: MessageEvent): unknown => {
      try {
        return JSON.parse(String(raw.data));
      } catch {
        return null;
      }
    };
    source.onopen = () => send({ type: "open" });
    source.addEventListener("segment", (e) => send({ type: "segment", data: parse(e as MessageEvent) }));
    source.addEventListener("turn", (e) => send({ type: "turn", data: parse(e as MessageEvent) }));
    for (const type of ["done", "timeout"] as const) {
      source.addEventListener(type, () => {
        send({ type });
        source.close();
      });
    }
    // Dikkat: "error" hem sunucunun STT hatası olayının hem de tarayıcının bağlantı hatası
    // olayının adıdır. Sunucu olayı `MessageEvent` (data ile) gelir, bağlantı hatası düz `Event`.
    source.addEventListener("error", (e) => {
      if (e instanceof MessageEvent) {
        send({ type: "error" });
        source.close();
        return;
      }
      // Ağ hatası: tarayıcı yeniden dener (CONNECTING); sunucu reddettiyse (4xx/5xx) CLOSED olur.
      send({ type: "disconnect" });
      if (source.readyState === EventSource.CLOSED) source.close();
    });
    return () => source.close();
  }, [callId, enabled]);

  return state;
}
