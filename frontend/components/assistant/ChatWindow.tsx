import React, { useEffect, useRef, type ReactNode } from "react";
import type { ChatMessage } from "@/lib/types";
import type { StreamStage } from "@/lib/api/types";
import { Button } from "@/components/ui";
import { CitationList } from "./CitationList";
import { StatusIndicator } from "./StatusIndicator";

interface ChatWindowProps {
  messages: ChatMessage[];
  currentStage?: StreamStage | "yaziyor" | null;
  isLoading?: boolean;
  onRetry?: () => void;
  /** Mesaj listesinin altında gösterilir (ör. ilk ekrandaki hazır sorular). */
  footer?: ReactNode;
  className?: string;
}

function formatTime(iso?: string): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
}

export function ChatWindow({
  messages,
  currentStage,
  isLoading = false,
  onRetry,
  footer,
  className = "",
}: ChatWindowProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Otomatik aşağı kaydırma
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, currentStage, isLoading]);

  return (
    <div
      role="log"
      aria-live="polite"
      aria-label="Asistan Sohbet Geçmişi"
      className={`h-full space-y-4 overflow-y-auto p-4 sm:p-6 ${className}`}
    >
      {messages.map((msg) => {
        const isUser = msg.role === "user";
        const isNotFound =
          msg.found === false || msg.content.includes("Bu konuda kayıtlarda bilgi bulamadım");
        const hasCitations =
          !isUser &&
          !isNotFound &&
          !msg.isStreaming &&
          Array.isArray(msg.citations) &&
          msg.citations.length > 0;
        const error = msg.error;
        const isConfigError =
          !!error &&
          (error.isApiKeyError ||
            error.code === "LLM_NOT_CONFIGURED" ||
            error.message.includes("LLM_API_KEY"));

        return (
          <div key={msg.id} className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm sm:max-w-[75%] ${
                isUser
                  ? "rounded-br-sm bg-brand-700 text-white"
                  : "rounded-bl-sm border border-slate-200 bg-white text-slate-900"
              }`}
            >
              <p className="whitespace-pre-wrap break-words leading-relaxed">
                {msg.content}
                {msg.isStreaming && (
                  <span
                    className="ml-1 inline-block h-4 w-1.5 animate-pulse bg-brand-600 align-middle"
                    aria-hidden="true"
                  />
                )}
              </p>

              {isNotFound && !msg.isStreaming && (
                <p className="mt-2 text-xs text-slate-500">
                  Servis kayıtlarında eşleşen belge bulunamadı.
                </p>
              )}

              {hasCitations && <CitationList citations={msg.citations} />}

              {error && (
                <div role="alert" className="mt-2 space-y-2 text-xs text-red-700">
                  <p>
                    {isConfigError
                      ? "Yapay zekâ servisi yapılandırılmamış. Sistem yöneticinize başvurun."
                      : error.message}
                  </p>
                  {error.requestId && (
                    <p className="font-mono text-[10px] text-slate-500">İstek no: {error.requestId}</p>
                  )}
                  {onRetry && (
                    <Button variant="secondary" size="sm" onClick={onRetry}>
                      Yeniden dene
                    </Button>
                  )}
                </div>
              )}

              {msg.timestamp && (
                <p className={`mt-1 text-[10px] ${isUser ? "text-right text-white/70" : "text-slate-400"}`}>
                  {formatTime(msg.timestamp)}
                </p>
              )}
            </div>
          </div>
        );
      })}

      {isLoading && currentStage && <StatusIndicator stage={currentStage} />}

      {footer}

      <div ref={bottomRef} className="h-1" />
    </div>
  );
}
