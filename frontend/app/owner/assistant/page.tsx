"use client";

import React, { useState, useRef, useCallback, useEffect } from "react";
import type { ChatMessage, CitationCard } from "@/lib/types";
import type { StreamStage, SourceRef, ChatReply } from "@/lib/api/types";
import { streamAssistantChat, DEFAULT_OWNER_ID } from "@/lib/api/client";
import { isApiError } from "@/lib/api/errors";
import {
  ChatWindow,
  ChatInput,
  SuggestedPrompts,
} from "@/components/assistant";

const INITIAL_MESSAGES: ChatMessage[] = [
  {
    id: "msg-welcome",
    role: "assistant",
    content:
      "Merhaba! Ben Miço Usta Tekne Asistanı. Teknenizin servis geçmişi, marina faturaları, periyodik bakım takvimi ve acil durum prosedürleri hakkında size yardımcı olabilirim.",
    timestamp: new Date().toISOString(),
    citations: [],
    found: true,
  },
];

function mapSourceRefsToCitationCards(sources?: SourceRef[]): CitationCard[] {
  if (!sources || !Array.isArray(sources)) return [];
  return sources.map((s) => ({
    sourceTitle: s.title,
    date: s.date || "",
    excerpt: s.excerpt || undefined,
    kind: s.kind,
    recordId: s.record_id,
  }));
}

export default function AssistantPage() {
  const [messages, setMessages] = useState<ChatMessage[]>(INITIAL_MESSAGES);
  const [currentStage, setCurrentStage] = useState<StreamStage | "yaziyor" | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [lastQuestion, setLastQuestion] = useState<string | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);

  // Bileşen unmount olduğunda akışı kes
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  const handleStopStreaming = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setCurrentStage(null);
    setIsLoading(false);
    setMessages((prev) => {
      const copy = [...prev];
      const lastIndex = copy.length - 1;
      if (lastIndex >= 0 && copy[lastIndex].isStreaming) {
        copy[lastIndex] = {
          ...copy[lastIndex],
          isStreaming: false,
          content: copy[lastIndex].content + "\n\n*(Akış kullanıcı tarafından durduruldu)*",
        };
      }
      return copy;
    });
  }, []);

  const sendMessage = useCallback(
    async (questionText: string) => {
      const trimmed = questionText.trim();
      if (!trimmed || isLoading) return;

      setLastQuestion(trimmed);

      // Yeni bir AbortController oluştur
      abortControllerRef.current?.abort();
      const controller = new AbortController();
      abortControllerRef.current = controller;

      const userMsgId = `user-${Date.now()}`;
      const assistantMsgId = `asst-${Date.now()}`;

      const userMsg: ChatMessage = {
        id: userMsgId,
        role: "user",
        content: trimmed,
        timestamp: new Date().toISOString(),
        citations: [],
      };

      // Geçici asistan mesajı (yazılıyor efekti ile)
      const pendingAssistantMsg: ChatMessage = {
        id: assistantMsgId,
        role: "assistant",
        content: "",
        timestamp: new Date().toISOString(),
        citations: [],
        isStreaming: true,
      };

      setMessages((prev) => [...prev, userMsg, pendingAssistantMsg]);
      setIsLoading(true);
      setCurrentStage("araniyor");

      try {
        await streamAssistantChat(
          { question: trimmed },
          DEFAULT_OWNER_ID,
          {
            onStatus: (stage) => {
              setCurrentStage(stage);
            },
            onDelta: (chunk) => {
              setCurrentStage("yaziyor");
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId
                    ? { ...m, content: m.content + chunk }
                    : m,
                ),
              );
            },
            onDone: (reply: ChatReply) => {
              setCurrentStage(null);
              setIsLoading(false);
              const isFound = reply.answer.found !== false;
              // found=false durumunda veya kaynak yoksa kartlar gösterilmez
              const citations = isFound ? mapSourceRefsToCitationCards(reply.answer.sources) : [];
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId
                    ? {
                        ...m,
                        content: reply.answer.content || m.content,
                        citations,
                        found: isFound,
                        isStreaming: false,
                      }
                    : m,
                ),
              );
            },
            onError: (err) => {
              setCurrentStage(null);
              setIsLoading(false);
              const isApiKey =
                err.code === "LLM_NOT_CONFIGURED" ||
                err.message.includes("LLM_API_KEY");

              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId
                    ? {
                        ...m,
                        isStreaming: false,
                        error: {
                          code: err.code,
                          message: err.message,
                          requestId: err.requestId,
                          isApiKeyError: isApiKey,
                        },
                      }
                    : m,
                ),
              );
            },
          },
          controller.signal,
        );
      } catch (unknownErr) {
        if ((unknownErr as Error)?.name === "AbortError") {
          return;
        }
        setCurrentStage(null);
        setIsLoading(false);
        const errMessage = isApiError(unknownErr)
          ? unknownErr.message
          : (unknownErr as Error)?.message || "Beklenmeyen bir hata oluştu.";

        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId
              ? {
                  ...m,
                  isStreaming: false,
                  error: {
                    code: isApiError(unknownErr) ? unknownErr.code : "CLIENT_ERROR",
                    message: errMessage,
                    requestId: isApiError(unknownErr) ? unknownErr.requestId : null,
                  },
                }
              : m,
          ),
        );
      }
    },
    [isLoading],
  );

  const handleRetry = useCallback(() => {
    if (lastQuestion) {
      // Hatalı son asistan mesajını ve soruyu temizleyip tekrar gönder
      setMessages((prev) => {
        const withoutLastPair = prev.slice(0, Math.max(0, prev.length - 2));
        return withoutLastPair;
      });
      void sendMessage(lastQuestion);
    }
  }, [lastQuestion, sendMessage]);

  const handleClearChat = useCallback(() => {
    if (isLoading) handleStopStreaming();
    setMessages(INITIAL_MESSAGES);
    setLastQuestion(null);
  }, [isLoading, handleStopStreaming]);

  return (
    <div className="flex flex-col h-[calc(100vh-6.5rem)] max-w-5xl mx-auto space-y-3">
      {/* Üst Asistan Bilgi Başlığı */}
      <header
        className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white px-5 py-3.5 shadow-xs"
        role="banner"
      >
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-sky-900 text-white shadow-xs">
            <span className="text-xl">⚓</span>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-bold text-slate-900">
                Miço Usta AI Tekne Asistanı
              </h1>
              <span className="rounded-full bg-sky-100 px-2 py-0.5 text-[10px] font-semibold text-sky-800 border border-sky-200">
                v1.0 (Akışlı)
              </span>
            </div>
            <p className="text-xs text-slate-500">
              Kayıtlı Tekne: <strong className="font-semibold text-slate-800">Poyraz (Motoryat 42)</strong> • Kalamış Marina
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700 border border-emerald-200">
            <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse"></span>
            Çevrimiçi &amp; Servis Kayıtları Aktif
          </span>
          <button
            type="button"
            onClick={handleClearChat}
            disabled={isLoading || messages.length <= 1}
            className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-50 hover:text-slate-900 disabled:opacity-40"
            title="Sohbeti Temizle"
          >
            Temizle
          </button>
        </div>
      </header>

      {/* Mesaj Penceresi */}
      <ChatWindow
        messages={messages}
        currentStage={currentStage}
        isLoading={isLoading}
        onRetry={handleRetry}
      />

      {/* Önerilen Sorular */}
      <div className="px-1">
        <SuggestedPrompts
          onSelectPrompt={(prompt) => void sendMessage(prompt)}
          disabled={isLoading}
        />
      </div>

      {/* Mesaj Giriş Kutusu */}
      <div className="px-1">
        <ChatInput
          onSendMessage={(content) => void sendMessage(content)}
          disabled={isLoading}
          isStreaming={isLoading}
          onStopStreaming={handleStopStreaming}
        />
      </div>
    </div>
  );
}
