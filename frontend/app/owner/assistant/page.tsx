"use client";

import React, { useState, useRef, useCallback, useEffect } from "react";
import type { ChatMessage, CitationCard } from "@/lib/types";
import type { StreamStage, SourceRef, ChatReply, ChatSessionOut } from "@/lib/api/types";
import {
  streamAssistantChat,
  getChatSessions,
  getChatSessionDetail,
  DEFAULT_OWNER_ID,
} from "@/lib/api/client";
import { isApiError } from "@/lib/api/errors";
import {
  ChatWindow,
  ChatInput,
  SuggestedPrompts,
  ChatSidebar,
} from "@/components/assistant";

// ──────────────────────────────────────────────────────────────────────────────
// Sabittler
// ──────────────────────────────────────────────────────────────────────────────

const WELCOME_MESSAGE: ChatMessage = {
  id: "msg-welcome",
  role: "assistant",
  content:
    "Merhaba! Ben Miço Usta Tekne Asistanı. Teknenizin servis geçmişi, marina faturaları, periyodik bakım takvimi ve acil durum prosedürleri hakkında size yardımcı olabilirim.",
  timestamp: new Date().toISOString(),
  citations: [],
  found: true,
};

const INITIAL_MESSAGES: ChatMessage[] = [WELCOME_MESSAGE];

// ──────────────────────────────────────────────────────────────────────────────
// Yardımcı: SourceRef[] → CitationCard[]
// ──────────────────────────────────────────────────────────────────────────────

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

// ──────────────────────────────────────────────────────────────────────────────
// Sayfa bileşeni
// ──────────────────────────────────────────────────────────────────────────────

export default function AssistantPage() {
  // ── Sohbet durumu ──────────────────────────────────────────────────────────
  const [messages, setMessages] = useState<ChatMessage[]>(INITIAL_MESSAGES);
  const [currentStage, setCurrentStage] = useState<StreamStage | "yaziyor" | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [lastQuestion, setLastQuestion] = useState<string | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);
  /** Aynı sohbetteki sorular aynı oturumda sürsün (ilk cevapla gelen session_id). */
  const sessionIdRef = useRef<string | undefined>(undefined);

  // ── Oturum listesi durumu ─────────────────────────────────────────────────
  const [sessions, setSessions] = useState<ChatSessionOut[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [sessionsError, setSessionsError] = useState<string | null>(null);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);

  // ── Mobil kenar çubuğu durumu ─────────────────────────────────────────────
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // ── Bileşen unmount olduğunda akışı kes ──────────────────────────────────
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  // ── Oturum listesini yükle ────────────────────────────────────────────────
  const loadSessions = useCallback(async () => {
    try {
      setSessionsError(null);
      const list = await getChatSessions(DEFAULT_OWNER_ID);
      // Yeniden eskiye sıralama (API zaten bunu yapıyor, ama garantiye alalım)
      const sorted = [...list].sort(
        (a, b) =>
          new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
      );
      setSessions(sorted);
    } catch (err) {
      const msg = isApiError(err)
        ? err.message
        : (err as Error)?.message || "Sohbet geçmişi yüklenemedi.";
      setSessionsError(msg);
    } finally {
      setSessionsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSessions();
  }, [loadSessions]);

  // ── Oturum seçimi ─────────────────────────────────────────────────────────
  const handleSelectSession = useCallback(
    async (sessionId: string) => {
      if (isLoading) {
        abortControllerRef.current?.abort();
        setIsLoading(false);
        setCurrentStage(null);
      }
      setActiveSessionId(sessionId);
      sessionIdRef.current = sessionId;
      setLastQuestion(null);

      try {
        const detail = await getChatSessionDetail(sessionId, DEFAULT_OWNER_ID);
        const history: ChatMessage[] = detail.messages.map((m) => ({
          id: m.id,
          role: m.role as "user" | "assistant",
          content: m.content,
          timestamp: m.created_at,
          citations:
            m.found !== false ? mapSourceRefsToCitationCards(m.sources) : [],
          found: m.found,
          isStreaming: false,
        }));
        setMessages(history.length > 0 ? history : INITIAL_MESSAGES);
      } catch (err) {
        const msg = isApiError(err)
          ? err.message
          : (err as Error)?.message || "Oturum yüklenemedi.";
        // Hata mesajını sohbet penceresinde göster
        setMessages([
          {
            ...WELCOME_MESSAGE,
            id: "msg-session-err",
            content: `Sohbet geçmişi yüklenirken hata oluştu: ${msg}`,
          },
        ]);
      }
    },
    [isLoading],
  );

  // ── Yeni sohbet ──────────────────────────────────────────────────────────
  const handleNewChat = useCallback(() => {
    if (isLoading) {
      abortControllerRef.current?.abort();
      abortControllerRef.current = null;
      setIsLoading(false);
      setCurrentStage(null);
    }
    setMessages(INITIAL_MESSAGES);
    setLastQuestion(null);
    setActiveSessionId(null);
    sessionIdRef.current = undefined;
  }, [isLoading]);

  // ── Akışı durdur ─────────────────────────────────────────────────────────
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

  // ── Mesaj gönder ─────────────────────────────────────────────────────────
  const sendMessage = useCallback(
    async (questionText: string) => {
      const trimmed = questionText.trim();
      if (!trimmed || isLoading) return;

      setLastQuestion(trimmed);

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
          { question: trimmed, session_id: sessionIdRef.current },
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
              if (reply.session_id) sessionIdRef.current = reply.session_id;
              setCurrentStage(null);
              setIsLoading(false);
              const isFound = reply.answer.found !== false;
              const citations = isFound
                ? mapSourceRefsToCitationCards(reply.answer.sources)
                : [];
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
              // Oturum listesini yenile (yeni oturum oluşmuş olabilir)
              void loadSessions();
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
                    code: isApiError(unknownErr)
                      ? unknownErr.code
                      : "CLIENT_ERROR",
                    message: errMessage,
                    requestId: isApiError(unknownErr)
                      ? unknownErr.requestId
                      : null,
                  },
                }
              : m,
          ),
        );
      }
    },
    [isLoading, loadSessions],
  );

  // ── Yeniden dene ─────────────────────────────────────────────────────────
  const handleRetry = useCallback(() => {
    if (lastQuestion) {
      setMessages((prev) => prev.slice(0, Math.max(0, prev.length - 2)));
      void sendMessage(lastQuestion);
    }
  }, [lastQuestion, sendMessage]);

  // ── "Temizle" = yeni sohbet ile aynı ─────────────────────────────────────
  const handleClearChat = useCallback(() => {
    handleNewChat();
  }, [handleNewChat]);

  // ─────────────────────────────────────────────────────────────────────────
  // Render
  // ─────────────────────────────────────────────────────────────────────────

  return (
    <div className="flex h-[calc(100vh-6.5rem)] max-w-6xl mx-auto overflow-hidden rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm bg-white dark:bg-slate-900">
      {/* ── Sol: Oturum Kenar Çubuğu ─────────────────────────────────────── */}
      <ChatSidebar
        sessions={sessions}
        isLoading={sessionsLoading}
        error={sessionsError}
        activeSessionId={activeSessionId}
        onSelectSession={(id) => void handleSelectSession(id)}
        onNewChat={handleNewChat}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      {/* ── Sağ: Ana sohbet alanı ────────────────────────────────────────── */}
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        {/* Üst Asistan Bilgi Başlığı */}
        <header
          className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-4 py-3 flex-shrink-0"
          role="banner"
        >
          <div className="flex items-center gap-2.5">
            {/* Mobil: menü butonu */}
            <button
              type="button"
              onClick={() => setSidebarOpen(true)}
              className="lg:hidden rounded-lg p-1.5 text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-900"
              aria-label="Sohbet geçmişini aç"
              aria-expanded={sidebarOpen}
              aria-controls="chat-sidebar"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 20 20"
                fill="currentColor"
                className="h-5 w-5"
                aria-hidden="true"
              >
                <path
                  fillRule="evenodd"
                  d="M2 4.75A.75.75 0 0 1 2.75 4h14.5a.75.75 0 0 1 0 1.5H2.75A.75.75 0 0 1 2 4.75Zm0 10.5a.75.75 0 0 1 .75-.75h14.5a.75.75 0 0 1 0 1.5H2.75a.75.75 0 0 1-.75-.75ZM2 10a.75.75 0 0 1 .75-.75h7.5a.75.75 0 0 1 0 1.5h-7.5A.75.75 0 0 1 2 10Z"
                  clipRule="evenodd"
                />
              </svg>
            </button>

            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-sky-900 text-white shadow-xs flex-shrink-0">
              <span className="text-lg" aria-hidden="true">⚓</span>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-base font-bold text-slate-900 dark:text-slate-100 leading-tight">
                  Miço Usta AI Tekne Asistanı
                </h1>
                <span className="hidden sm:inline rounded-full bg-sky-100 dark:bg-sky-950/50 px-2 py-0.5 text-[10px] font-semibold text-sky-800 dark:text-sky-300 border border-sky-200 dark:border-sky-800">
                  v1.0 (Akışlı)
                </span>
              </div>
              <p className="text-xs text-slate-500 dark:text-slate-400 leading-tight">
                Kayıtlı Tekne:{" "}
                <strong className="font-semibold text-slate-800 dark:text-slate-200">
                  Poyraz (Motoryat 42)
                </strong>{" "}
                • Kalamış Marina
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="hidden sm:inline-flex items-center gap-1.5 rounded-full bg-emerald-50 dark:bg-emerald-950/40 px-3 py-1 text-xs font-semibold text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800">
              <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" aria-hidden="true" />
              Çevrimiçi &amp; Servis Kayıtları Aktif
            </span>
            <button
              type="button"
              onClick={handleClearChat}
              disabled={isLoading || messages.length <= 1}
              className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2.5 py-1 text-xs font-medium text-slate-600 dark:text-slate-300 transition-colors hover:bg-slate-50 dark:hover:bg-slate-700 hover:text-slate-900 dark:hover:text-slate-100 disabled:opacity-40 focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-900"
              title="Yeni sohbet başlat"
            >
              Temizle
            </button>
          </div>
        </header>

        {/* Mesaj Penceresi */}
        <div className="flex-1 overflow-hidden">
          <ChatWindow
            messages={messages}
            currentStage={currentStage}
            isLoading={isLoading}
            onRetry={handleRetry}
          />
        </div>

        {/* Önerilen Sorular + Giriş kutusu */}
        <div className="flex-shrink-0 border-t border-slate-200 dark:border-slate-800 px-3 pt-2 pb-3 space-y-2 bg-white dark:bg-slate-900">
          <SuggestedPrompts
            onSelectPrompt={(prompt) => void sendMessage(prompt)}
            disabled={isLoading}
          />
          <ChatInput
            onSendMessage={(content) => void sendMessage(content)}
            disabled={isLoading}
            isStreaming={isLoading}
            onStopStreaming={handleStopStreaming}
          />
        </div>
      </div>
    </div>
  );
}
