import React, { useEffect, useRef } from "react";
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
      className={`h-full min-w-0 space-y-4 overflow-y-auto p-4 sm:p-6 ${className}`}
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
        // İlk içerik gelene kadar balon yok; bekleme yalnızca durum göstergesiyle anlatılır (#212).
        if (!isUser && !msg.content.trim() && !error) return null;
        const isConfigError =
          !!error &&
          (error.isApiKeyError ||
            error.code === "LLM_NOT_CONFIGURED" ||
            error.message.includes("LLM_API_KEY"));

        return (
          <div
            key={msg.id}
            data-testid="chat-message"
            data-role={msg.role}
            className={`flex ${isUser ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`min-w-0 max-w-[85%] rounded-2xl px-4 py-2.5 text-sm sm:max-w-[75%] ${
                isUser
                  ? "rounded-br-sm bg-brand-700 text-white"
                  : "rounded-bl-sm border border-slate-200 bg-white text-slate-900"
              }`}
            >
              {msg.content.trim() && (
                <p className="whitespace-pre-wrap break-words [overflow-wrap:anywhere] leading-relaxed">
                  {msg.content}
                  {msg.isStreaming && (
                    <span
                      className="ml-1 inline-block h-4 w-1.5 animate-pulse bg-brand-600 align-middle"
                      aria-hidden="true"
                    />
                  )}
                </p>
              )}

              {isNotFound && !msg.isStreaming && (
                <p className="mt-2 text-xs text-slate-500">
                  Servis kayıtlarında eşleşen belge bulunamadı.
                </p>
              )}

              {hasCitations && <CitationList citations={msg.citations} />}

              {error && (
                <div role="alert" className={`${msg.content.trim() ? "mt-2 " : ""}space-y-2 text-xs text-red-700`}>
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
                <p className={`mt-1 text-[10px] ${isUser ? "text-right text-white/70" : "text-slate-500"}`}>
                  {formatTime(msg.timestamp)}
                </p>
              )}
            </div>
          </div>
        );
      })}

      {isLoading && currentStage && <StatusIndicator stage={currentStage} />}

      <div ref={bottomRef} className="h-1" />
    </div>
  );
}
