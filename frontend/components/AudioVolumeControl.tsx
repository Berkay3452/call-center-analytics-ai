"use client";

import { useEffect, useId, useRef, useState, useSyncExternalStore, type RefObject } from "react";

const STORAGE_KEY = "mico-audio-volume";
const CHANGE_EVENT = "mico-audio-volume-change";
let memoryValue: string | null = null;

function snapshot(): string | null {
  try { return localStorage.getItem(STORAGE_KEY) ?? memoryValue; }
  catch { return memoryValue; }
}

function subscribe(listener: () => void) {
  window.addEventListener("storage", listener);
  window.addEventListener(CHANGE_EVENT, listener);
  return () => {
    window.removeEventListener("storage", listener);
    window.removeEventListener(CHANGE_EVENT, listener);
  };
}

function readVolume(raw: string | null): { volume: number; previous: number } {
  try {
    const value = JSON.parse(raw ?? "null");
    if (value && Number.isFinite(value.volume) && value.volume >= 0 && value.volume <= 100 &&
      Number.isFinite(value.previous) && value.previous > 0 && value.previous <= 100) {
      return { volume: Math.round(value.volume), previous: Math.round(value.previous) || 100 };
    }
  } catch { /* Bozuk veya engellenmiş depolama oynatıcıyı durdurmaz. */ }
  return { volume: 100, previous: 100 };
}

export function AudioVolumeControl({ audioRef }: { audioRef: RefObject<HTMLAudioElement | null> }) {
  const raw = useSyncExternalStore(subscribe, snapshot, () => null);
  const { volume, previous } = readVolume(raw);
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelId = useId();
  const level = volume === 0 ? "muted" : volume <= 50 ? "low" : "high";

  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.volume = volume / 100;
      audioRef.current.muted = volume === 0;
    }
  }, [audioRef, volume]);

  const changeVolume = (next: number) => {
    const value = Math.min(100, Math.max(0, Math.round(next)));
    memoryValue = JSON.stringify({ volume: value, previous: value > 0 ? value : previous });
    try { localStorage.setItem(STORAGE_KEY, memoryValue); } catch { /* Bellekte devam et. */ }
    window.dispatchEvent(new Event(CHANGE_EVENT));
  };

  return (
    <div className="relative" onMouseEnter={() => setOpen(true)}
      onMouseLeave={(event) => { if (!event.currentTarget.contains(document.activeElement)) setOpen(false); }}
      onFocusCapture={() => setOpen(true)}
      onBlurCapture={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false); }}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          event.stopPropagation();
          buttonRef.current?.focus();
          setOpen(false);
        }
      }}>
      <button ref={buttonRef} type="button"
        onClick={() => { changeVolume(volume === 0 ? previous : 0); setOpen(true); }}
        aria-label={volume === 0 ? "Sesi Aç" : "Sesi Kapat"}
        title={volume === 0 ? "Sesi Aç" : "Sesi Kapat"}
        aria-pressed={volume === 0} aria-expanded={open} aria-controls={panelId}
        className="cursor-pointer rounded-lg p-2 text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2">
        <svg data-volume-level={level} className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" d="M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" />
          {level === "muted" ? <path d="m17 9 5 6m0-6-5 6" /> : (
            <>
              <path strokeLinecap="round" d="M15.536 8.464a5 5 0 010 7.072" />
              {level === "high" && <path strokeLinecap="round" d="M18.364 5.636a9 9 0 010 12.728" />}
            </>
          )}
        </svg>
      </button>
      {open && (
        <div id={panelId} className="absolute bottom-full right-0 z-20 pb-2">
          <div role="group" aria-label="Ses seviyesi ayarı" className="flex flex-col items-center gap-2 rounded-xl border border-slate-200 bg-white p-3 shadow-lg">
            <span aria-hidden="true" className="text-xs font-semibold text-brand-800">%{volume}</span>
            <input type="range" min={0} max={100} step={1} value={volume}
              aria-label="Ses seviyesi" aria-orientation="vertical"
              aria-valuemin={0} aria-valuemax={100} aria-valuenow={volume} aria-valuetext={`Yüzde ${volume}`}
              onChange={(event) => changeVolume(Number(event.target.value))}
              onKeyDown={(event) => {
                const next = { ArrowUp: volume + 5, ArrowRight: volume + 5, ArrowDown: volume - 5,
                  ArrowLeft: volume - 5, Home: 0, End: 100 }[event.key];
                if (next !== undefined) { event.preventDefault(); changeVolume(next); }
              }}
              style={{ writingMode: "vertical-lr", direction: "rtl" }}
              className="h-28 w-6 cursor-pointer accent-brand-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2" />
          </div>
        </div>
      )}
    </div>
  );
}
