import React, { useEffect, useRef } from "react";
import type { ChatMessage } from "@/lib/types";
import type { StreamStage } from "@/lib/api/types";
import { CitationList } from "./CitationList";
import { StatusIndicator } from "./StatusIndicator";

interface ChatWindowProps {
  messages: ChatMessage[];
  currentStage?: StreamStage | "yaziyor" | null;
  isLoading?: boolean;
  onRetry?: () => void;
  className?: string;
}

export function ChatWindow({
  messages,
  currentStage,
  isLoading = false,
  onRetry,
  className = "",
}: ChatWindowProps) {
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Otomatik aşağı kaydırma
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, currentStage, isLoading]);

  return (
    <div
      ref={scrollContainerRef}
      role="log"
      aria-live="polite"
      aria-label="Asistan Sohbet Geçmişi"
      className={`flex-1 overflow-y-auto rounded-2xl border border-slate-200 dark:border-slate-800 bg-linear-to-b from-slate-50/50 to-white dark:from-slate-900/60 dark:to-slate-950 p-4 sm:p-6 space-y-5 shadow-inner ${className}`}
    >
      {messages.map((msg) => {
        const isUser = msg.role === "user";
        const isNotFound = msg.found === false || msg.content.includes("Bu konuda kayıtlarda bilgi bulamadım");
        const hasCitations =
          !isUser &&
          !isNotFound &&
          !msg.isStreaming &&
          Array.isArray(msg.citations) &&
          msg.citations.length > 0;
        const hasError = !!msg.error;

        return (
          <div
            key={msg.id}
            className={`flex items-start gap-3 ${isUser ? "justify-end" : "justify-start"}`}
          >
            {/* Asistan Avatarı */}
            {!isUser && (
              <div
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-sky-900 text-white shadow-xs"
                aria-hidden="true"
              >
                <span className="text-sm">⚓</span>
              </div>
            )}

            {/* Mesaj Balonu */}
            <div
              className={`relative max-w-[85%] sm:max-w-[75%] rounded-2xl px-4 py-3 text-sm shadow-2xs transition-all ${
                isUser
                  ? "bg-sky-700 text-white rounded-tr-xs"
                  : hasError
                  ? "bg-rose-50/90 dark:bg-rose-950/40 text-rose-950 dark:text-rose-200 border border-rose-200 dark:border-rose-900 rounded-tl-xs"
                  : isNotFound
                  ? "bg-amber-50/80 dark:bg-amber-950/40 text-slate-800 dark:text-slate-200 border border-amber-200/80 dark:border-amber-900 rounded-tl-xs"
                  : "bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 border border-slate-200/90 dark:border-slate-800 rounded-tl-xs"
              }`}
            >
              {/* Asistan Başlığı */}
              {!isUser && (
                <div className="mb-1 flex items-center justify-between gap-2 border-b border-slate-100 dark:border-slate-800 pb-1">
                  <span className="text-xs font-bold text-sky-950 dark:text-sky-300 flex items-center gap-1.5">
                    Miço Usta AI
                    {msg.isStreaming && (
                      <span className="inline-block h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                    )}
                  </span>
                  {msg.timestamp && (
                    <span className="text-[10px] text-slate-500 dark:text-slate-400">
                      {new Date(msg.timestamp).toLocaleTimeString("tr-TR", {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </span>
                  )}
                </div>
              )}

              {/* Mesaj İçeriği */}
              <div className="leading-relaxed whitespace-pre-wrap break-words">
                {msg.content}
                {msg.isStreaming && (
                  <span
                    className="inline-block w-1.5 h-4 ml-1 bg-sky-700 animate-pulse align-middle"
                    aria-hidden="true"
                  />
                )}
              </div>

              {/* "Bulamadım" Özel Durumu */}
              {isNotFound && !msg.isStreaming && (
                <div className="mt-2.5 flex items-center gap-2 rounded-lg bg-amber-100/70 dark:bg-amber-950/60 p-2 text-xs text-amber-900 dark:text-amber-200">
                  <span className="text-sm">🔍</span>
                  <span className="text-[11px] leading-snug">
                    Veritabanı ve servis kayıtlarında eşleşen belge bulunamadı. Kaynak kartları gizlendi.
                  </span>
                </div>
              )}

              {/* Doğrulanan Kaynaklar (Citations) */}
              {hasCitations && <CitationList citations={msg.citations} />}

              {/* Hata Durumu & API Key Koruması */}
              {hasError && msg.error && (
                <div className="mt-3 rounded-xl border border-rose-300 dark:border-rose-800 bg-rose-100/80 dark:bg-rose-950/50 p-3 text-xs text-rose-950 dark:text-rose-200">
                  <div className="flex items-start gap-2">
                    <span className="text-base text-rose-600 dark:text-rose-400">⚠️</span>
                    <div className="flex-1 space-y-1">
                      <p className="font-semibold text-rose-900 dark:text-rose-200">
                        {msg.error.isApiKeyError ||
                        msg.error.code === "LLM_NOT_CONFIGURED" ||
                        msg.error.message.includes("LLM_API_KEY")
                          ? "AI Servisi Yapılandırma Uyarısı"
                          : "Yanıt Alınırken Hata Oluştu"}
                      </p>
                      <p className="text-[11px] text-rose-800 dark:text-rose-300 leading-snug">
                        {msg.error.isApiKeyError ||
                        msg.error.code === "LLM_NOT_CONFIGURED" ||
                        msg.error.message.includes("LLM_API_KEY")
                          ? "Backend AI modeli için geçerli bir LLM_API_KEY tanımlanmamış. Sistem yöneticinizle görüşün veya backend yapılandırmasını kontrol edin."
                          : msg.error.message}
                      </p>
                      {msg.error.requestId && (
                        <p className="text-[10px] text-rose-600 dark:text-rose-400 font-mono">
                          İstek ID: {msg.error.requestId}
                        </p>
                      )}
                    </div>
                  </div>

                  {onRetry && (
                    <div className="mt-2.5 flex justify-end">
                      <button
                        type="button"
                        onClick={onRetry}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-rose-700 px-3 py-1.5 text-xs font-semibold text-white shadow-xs hover:bg-rose-800 transition-colors focus:outline-none focus:ring-2 focus:ring-rose-500"
                      >
                        <svg
                          className="w-3.5 h-3.5"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                          strokeWidth="2"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                          />
                        </svg>
                        Yeniden Dene
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Kullanıcı Mesajı Zaman Damgası */}
              {isUser && msg.timestamp && (
                <div className="mt-1 text-right text-[10px] text-sky-200">
                  {new Date(msg.timestamp).toLocaleTimeString("tr-TR", {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </div>
              )}
            </div>

            {/* Kullanıcı Avatarı */}
            {isUser && (
              <div
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-slate-700 dark:bg-slate-800 text-white shadow-xs"
                aria-hidden="true"
              >
                <span className="text-xs font-bold">K</span>
              </div>
            )}
          </div>
        );
      })}

      {/* Akış Durumu Bildirimi */}
      {isLoading && currentStage && (
        <div className="flex items-center justify-start gap-3 pl-11">
          <StatusIndicator stage={currentStage} />
        </div>
      )}

      <div ref={bottomRef} className="h-1" />
    </div>
  );
}
