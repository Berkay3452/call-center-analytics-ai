"use client";

import React, { useState, useRef, useCallback, useEffect } from "react";
import type { ChatMessage, CitationCard } from "@/lib/types";
import type { StreamStage, SourceRef, ChatReply, ChatSessionOut } from "@/lib/api/types";
import {
  streamAssistantChat,
  getChatSessions,
  getChatSessionDetail,
  deleteChatSession,
  deleteAllChatSessions,
  DEFAULT_OWNER_ID,
} from "@/lib/api/client";
import { isApiError } from "@/lib/api/errors";
import { Button } from "@/components/ui";
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

  // ── Sohbet silme (#176) ──────────────────────────────────────────────────
  const handleDeleteSession = useCallback(
    async (sessionId: string) => {
      await deleteChatSession(sessionId, DEFAULT_OWNER_ID);
      setSessions((prev) => prev.filter((x) => x.id !== sessionId));
      // Açık sohbet silindiyse boş sohbete dön
      if (sessionIdRef.current === sessionId) handleNewChat();
    },
    [handleNewChat],
  );

  const handleDeleteAll = useCallback(async () => {
    await deleteAllChatSessions(DEFAULT_OWNER_ID);
    setSessions([]);
    handleNewChat();
  }, [handleNewChat]);

  // ─────────────────────────────────────────────────────────────────────────
  // Render
  // ─────────────────────────────────────────────────────────────────────────

  const isFreshChat = messages.length <= 1;

  return (
    <div className="mx-auto flex h-[calc(100vh-13rem)] min-h-[32rem] max-w-6xl overflow-hidden rounded-xl border border-slate-200 bg-white">
      <ChatSidebar
        sessions={sessions}
        isLoading={sessionsLoading}
        error={sessionsError}
        activeSessionId={activeSessionId}
        onSelectSession={(id) => void handleSelectSession(id)}
        onNewChat={handleNewChat}
        newChatDisabled={isFreshChat && !activeSessionId}
        onDeleteSession={handleDeleteSession}
        onDeleteAll={handleDeleteAll}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex flex-shrink-0 items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
          <div className="flex min-w-0 items-center gap-2.5">
            <Button
              variant="ghost"
              size="sm"
              className="lg:hidden"
              onClick={() => setSidebarOpen(true)}
              aria-label="Sohbet geçmişini aç"
              aria-expanded={sidebarOpen}
              aria-controls="chat-sidebar"
            >
              Geçmiş
            </Button>
            <div className="min-w-0">
              <h1 className="truncate text-base font-semibold text-brand-800">Miço AI</h1>
              <p className="truncate text-xs text-slate-500">Poyraz (Motoryat 42) · Kalamış Marina</p>
            </div>
          </div>
          <Button
            variant="secondary"
            size="sm"
            className="lg:hidden"
            onClick={handleNewChat}
            disabled={isLoading || isFreshChat}
            title="Mevcut sohbet geçmişte kalır, boş bir sohbet açılır"
          >
            Yeni sohbet
          </Button>
        </header>

        <div className="min-h-0 flex-1 bg-slate-50">
          <ChatWindow
            messages={messages}
            currentStage={currentStage}
            isLoading={isLoading}
            onRetry={handleRetry}
            footer={
              isFreshChat && !isLoading ? (
                <SuggestedPrompts onSelectPrompt={(prompt) => void sendMessage(prompt)} />
              ) : null
            }
          />
        </div>

        <div className="flex-shrink-0 border-t border-slate-200 bg-white p-3">
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
