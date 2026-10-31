"use client";

import React, { useState, useRef, useCallback } from "react";

interface AudioPlayerProps {
  callId: string;
  hasAudio?: boolean;
  durationSec?: number;
  className?: string;
}

function formatTime(seconds: number): string {
  if (isNaN(seconds) || seconds < 0) return "00:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export function AudioPlayer({
  callId,
  hasAudio = true,
  durationSec = 0,
  className = "",
}: AudioPlayerProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(durationSec);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [isMuted, setIsMuted] = useState(false);
  const [audioError, setAudioError] = useState<string | null>(null);

  // Ses kaynağı
  const audioSrc = `/api/backend/calls/${encodeURIComponent(callId)}/audio`;

  const togglePlayPause = useCallback(async () => {
    if (!audioRef.current) return;
    try {
      if (isPlaying) {
        audioRef.current.pause();
      } else {
        setAudioError(null);
        await audioRef.current.play();
      }
    } catch (err) {
      // AbortError veya kullanıcı etkileşimi kısıtlamaları
      if ((err as Error)?.name !== "AbortError") {
        setAudioError("Ses oynatılamadı. Dosya mevcut olmayabilir.");
        setIsPlaying(false);
      }
    }
  }, [isPlaying]);

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newTime = parseFloat(e.target.value);
    setCurrentTime(newTime);
    if (audioRef.current) {
      audioRef.current.currentTime = newTime;
    }
  };

  const handleSkip = (seconds: number) => {
    if (!audioRef.current) return;
    const target = Math.min(Math.max(0, audioRef.current.currentTime + seconds), duration);
    audioRef.current.currentTime = target;
    setCurrentTime(target);
  };

  const cyclePlaybackRate = () => {
    const rates = [1, 1.25, 1.5, 2];
    const nextIndex = (rates.indexOf(playbackRate) + 1) % rates.length;
    const nextRate = rates[nextIndex];
    setPlaybackRate(nextRate);
    if (audioRef.current) {
      audioRef.current.playbackRate = nextRate;
    }
  };

  const toggleMute = () => {
    if (!audioRef.current) return;
    const nextMuted = !isMuted;
    audioRef.current.muted = nextMuted;
    setIsMuted(nextMuted);
  };

  // 1. Durum: Ses Yok (has_audio === false)
  if (!hasAudio) {
    return (
      <div
        className={`rounded-xl border border-dashed border-gray-200 bg-gray-50/80 p-6 text-center shadow-xs transition-colors ${className}`}
        role="region"
        aria-label="Ses Kaydı Durumu"
      >
        <div className="flex flex-col items-center justify-center gap-2 text-slate-500">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-200/80 text-lg" aria-hidden="true">
            
          </div>
          <div>
            <p className="text-sm font-semibold text-slate-700">
              Bu çağrı için ses kaydı yok
            </p>
            <p className="text-xs text-slate-500 mt-0.5">
              Cevapsız çağrı, harici aktarım veya ses dosyası yüklenmemiş görüşme
            </p>
          </div>
        </div>
      </div>
    );
  }

  // 2. Durum: Gerçek Ses Oynatıcı
  const progressPercent = duration > 0 ? Math.min(100, (currentTime / duration) * 100) : 0;

  return (
    <div
      className={`rounded-xl border border-gray-200 bg-white p-5 shadow-sm transition-colors ${className}`}
      role="region"
      aria-label="Ses Kaydı Oynatıcı"
    >
      {/* Gizli HTML5 Audio Etiketi */}
      <audio
        ref={audioRef}
        src={audioSrc}
        preload="metadata"
        onTimeUpdate={() => {
          if (audioRef.current) {
            setCurrentTime(audioRef.current.currentTime);
          }
        }}
        onLoadedMetadata={() => {
          if (audioRef.current && !isNaN(audioRef.current.duration)) {
            setDuration(audioRef.current.duration);
          }
        }}
        onDurationChange={() => {
          if (audioRef.current && !isNaN(audioRef.current.duration)) {
            setDuration(audioRef.current.duration);
          }
        }}
        onPlay={() => setIsPlaying(true)}
        onPause={() => setIsPlaying(false)}
        onEnded={() => {
          setIsPlaying(false);
          setCurrentTime(0);
        }}
        onError={() => {
          setAudioError("Ses dosyası yüklenemedi veya akış başarısız oldu.");
          setIsPlaying(false);
        }}
      />

      {/* Başlık ve Zaman Bilgisi */}
      <div className="flex items-center justify-between mb-3.5">
        <div className="flex items-center gap-2">
          <span className="flex h-2 w-2 relative" aria-hidden="true">
            {isPlaying && (
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand-400 opacity-75"></span>
            )}
            <span
              className={`relative inline-flex rounded-full h-2 w-2 ${
                isPlaying ? "bg-brand-500" : "bg-slate-400"
              }`}
            ></span>
          </span>
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-600">
            Görüşme Ses Kaydı
          </h2>
        </div>

        <div className="flex items-center gap-2">
          <span className="font-mono text-xs font-semibold text-slate-700">
            {formatTime(currentTime)} <span className="text-slate-400">/</span> {formatTime(duration)}
          </span>
        </div>
      </div>

      {/* İlerleme Çubuğu (Seek Bar) */}
      <div className="relative mb-3 flex items-center">
        <div className="relative w-full h-2 rounded-full bg-slate-100 overflow-hidden">
          <div
            className="h-full bg-brand-600 transition-all duration-75"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
        <input
          type="range"
          min={0}
          max={duration || 100}
          step={0.1}
          value={currentTime}
          onChange={handleSeek}
          aria-label="Ses ilerleme çubuğu"
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 rounded-full"
        />
      </div>

      {/* Kontrol Butonları */}
      <div className="flex items-center justify-between gap-3 pt-1">
        <div className="flex items-center gap-1.5 sm:gap-2">
          {/* -5sn Geri Sar */}
          <button
            type="button"
            onClick={() => handleSkip(-5)}
            title="5 saniye geri"
            aria-label="5 saniye geri"
            className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2"
          >
            <span className="text-xs font-bold font-mono">-5s</span>
          </button>

          {/* Oynat / Duraklat Butonu */}
          <button
            type="button"
            onClick={togglePlayPause}
            aria-label={isPlaying ? "Duraklat" : "Oynat"}
            title={isPlaying ? "Duraklat" : "Oynat"}
            className="flex h-10 w-10 items-center justify-center rounded-full bg-brand-600 text-white shadow-sm hover:bg-brand-700 active:scale-95 transition-all focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2"
          >
            {isPlaying ? (
              <svg className="w-4 h-4 fill-current" viewBox="0 0 24 24" aria-hidden="true">
                <rect x="6" y="4" width="4" height="16" rx="1" />
                <rect x="14" y="4" width="4" height="16" rx="1" />
              </svg>
            ) : (
              <svg className="w-4 h-4 fill-current ml-0.5" viewBox="0 0 24 24" aria-hidden="true">
                <path d="M8 5v14l11-7z" />
              </svg>
            )}
          </button>

          {/* +5sn İleri Sar */}
          <button
            type="button"
            onClick={() => handleSkip(5)}
            title="5 saniye ileri"
            aria-label="5 saniye ileri"
            className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2"
          >
            <span className="text-xs font-bold font-mono">+5s</span>
          </button>
        </div>

        <div className="flex items-center gap-1.5 sm:gap-2">
          {/* Oynatma Hızı */}
          <button
            type="button"
            onClick={cyclePlaybackRate}
            title="Oynatma Hızı"
            aria-label={`Oynatma hızı ${playbackRate}x`}
            className="rounded-lg px-2.5 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-100 transition-colors border border-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2"
          >
            {playbackRate}x
          </button>

          {/* Ses Aç / Kapa (Mute) */}
          <button
            type="button"
            onClick={toggleMute}
            title={isMuted ? "Sesi Aç" : "Sesi Kapat"}
            aria-label={isMuted ? "Sesi Aç" : "Sesi Kapat"}
            className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2"
          >
            {isMuted ? (
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M17 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2" />
              </svg>
            ) : (
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" />
              </svg>
            )}
          </button>
        </div>
      </div>

      {/* Hata Uyarısı (Dosya bulunamazsa vs.) */}
      {audioError && (
        <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-2.5 text-xs text-amber-800">
          {audioError}
        </div>
      )}
    </div>
  );
}
