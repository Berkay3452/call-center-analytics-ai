"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import type { ChatMessage } from "@/lib/types";

let msgCounter = 0;
function makeId() {
  msgCounter += 1;
  return `msg-${msgCounter}`;
}

// Statik örnek yanıtlar — backend AI entegrasyonu gelene kadar
const MOCK_REPLIES = [
  "Merhaba! Size nasıl yardımcı olabilirim?",
  "Teknenizle ilgili detaylı bilgi verebilir misiniz?",
  "Randevunuzu en kısa sürede oluşturuyorum.",
  "Başka bir sorunuz var mı?",
];

// Karşılama mesajı ID'si — useEffect ile timestamp doldurulur (prerender uyumlu).
const WELCOME_ID = makeId();

export default function AssistantPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: WELCOME_ID,
      role: "assistant",
      content:
        "Merhaba! Ben Miço Usta AI asistanı. Size nasıl yardımcı olabilirim?",
      // Prerender sırasında new Date() çağrısını önlemek için boş bırakılır;
      // useEffect istemci tarafında doldurur.
      timestamp: "",
    },
  ]);

  // İstemci mount olduktan sonra ilk mesajın timestamp'ini doldur.
  useEffect(() => {
    setMessages((prev) =>
      prev.map((m) =>
        m.id === WELCOME_ID ? { ...m, timestamp: new Date().toISOString() } : m,
      ),
    );
  }, []);

  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg: ChatMessage = {
      id: makeId(),
      role: "user",
      content: text,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    // Simüle edilmiş gecikme ve yanıt
    await new Promise<void>((resolve) => setTimeout(resolve, 800));

    const reply = MOCK_REPLIES[Math.floor(Math.random() * MOCK_REPLIES.length)];
    const assistantMsg: ChatMessage = {
      id: makeId(),
      role: "assistant",
      content: reply ?? "Anlıyorum.",
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, assistantMsg]);
    setLoading(false);
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [input, loading]);

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      <h1 className="text-2xl font-bold text-gray-900 mb-4">
        🤖 Asistan Sohbet
      </h1>

      {/* Mesaj alanı */}
      <div className="flex-1 overflow-y-auto rounded-xl border border-gray-200 bg-white p-4 space-y-4 shadow-sm">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[75%] rounded-2xl px-4 py-2.5 text-sm ${
                msg.role === "user"
                  ? "bg-blue-600 text-white rounded-br-sm"
                  : "bg-gray-100 text-gray-800 rounded-bl-sm"
              }`}
            >
              <p>{msg.content}</p>
              {msg.timestamp && (
                <p
                  className={`mt-1 text-[10px] ${
                    msg.role === "user" ? "text-blue-200" : "text-gray-400"
                  }`}
                >
                  {new Date(msg.timestamp).toLocaleTimeString("tr-TR")}
                </p>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 rounded-2xl rounded-bl-sm px-4 py-2.5 text-sm text-gray-500">
              <span className="animate-pulse">Yazıyor…</span>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Giriş alanı */}
      <div className="mt-3 flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void sendMessage();
            }
          }}
          placeholder="Mesajınızı yazın…"
          className="flex-1 rounded-xl border border-gray-300 px-4 py-2.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          disabled={loading}
        />
        <button
          onClick={() => void sendMessage()}
          disabled={loading || !input.trim()}
          className="rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          Gönder
        </button>
      </div>
    </div>
  );
}
