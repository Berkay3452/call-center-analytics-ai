"use client";

import { useState, useRef, useCallback } from "react";
import type { ChatMessage, CitationCard } from "@/lib/types";

let msgCounter = 0;
function makeId() {
  msgCounter += 1;
  return `msg-${msgCounter}`;
}

const PRESET_QUESTIONS = [
  "Son motor bakımım ne zaman yapıldı?",
  "Bu ayki marina masrafım ne kadar?",
  "Sintine alarmı çaldığında ilk ne yapmalıyım?",
  "Akü voltajım normal seviyede mi?",
];

/** Asistan bilgi tabanı: citation → citations dizisine taşındı */
const MOCK_ASSISTANT_KNOWLEDGE: Record<
  string,
  { reply: string; citations: CitationCard[] }
> = {
  "Son motor bakımım ne zaman yapıldı?": {
    reply:
      "Tekneniz Poyraz (Motoryat 42) için son periyodik motor bakımı 15 Ağustos 2024 tarihinde Kalamış Marina'da usta Mehmet Şimşek tarafından yapılmıştır. Motor yağı, yakıt filtreleri ve impeller değişimi tamamlanmıştır.",
    citations: [
      {
        sourceTitle: "15 Ağustos 2024 Tarihli Usta Servis Raporu",
        date: "15.08.2024",
        callId: "call-001",
        excerpt:
          "Ana makine 250 saatlik periyodik bakımı ve filtre değişimleri tamamlandı.",
      },
    ],
  },
  "Bu ayki marina masrafım ne kadar?": {
    reply:
      "Kalamış Marina sözleşmenize göre Ekim 2024 dönemi bağlama ve elektrik/su tüketim toplamınız 14.250 TL olarak muhasebeleştirilmiştir. Son ödeme tarihi 25 Ekim'dir.",
    citations: [
      {
        sourceTitle: "Kalamış Marina İskele C-12 Hizmet Faturası",
        date: "01.10.2024",
        excerpt: "12m motoryat standart bağlama ve sayaç tüketim bedeli.",
      },
    ],
  },
  "Sintine alarmı çaldığında ilk ne yapmalıyım?": {
    reply:
      "Sintine alarmı devreye girdiğinde derhal: 1) Sintine otomatik pompasının (float switch) çalıştığını kontrol edin, 2) Şaft kovanı ve deniz suyu vanalarını (seacock) su sızıntısına karşı gözleyin, 3) Akü ana şalterinin açık olduğundan emin olun. Gerekirse Miço Usta acil destek hattından yerinde usta çağırabilirsiniz.",
    citations: [
      {
        sourceTitle: "Miço Usta Acil Güvenlik Kılavuzu & Çağrı Analiz Kaydı",
        date: "09.10.2024",
        callId: "call-001",
        excerpt: "Sintine su seviyesi alarmı acil müdahale adımları.",
      },
    ],
  },
};

/** "Bulamadım" yanıtı — citations boş dizi olarak gelir */
const NOT_FOUND_REPLY =
  "Bu konuda kayıtlarda bilgi bulamadım. Daha fazla bilgi için Miço Usta servis ekibinizle iletişime geçebilirsiniz.";

const INITIAL_MESSAGES: ChatMessage[] = [
  {
    id: "msg-welcome",
    role: "assistant",
    content:
      "Merhaba! Ben Miço Usta Tekne Asistanı. Teknenizin bakım geçmişi, marina kayıtları ve teknik durumu hakkında size yardımcı olabilirim.",
    timestamp: "2024-10-09T09:00:00Z",
    citations: [],
  },
];

export default function AssistantPage() {
  const [messages, setMessages] = useState<ChatMessage[]>(INITIAL_MESSAGES);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const sendMessage = useCallback(
    async (textToSend?: string) => {
      const text = (textToSend ?? input).trim();
      if (!text || loading) return;

      const userMsg: ChatMessage = {
        id: makeId(),
        role: "user",
        content: text,
        timestamp: new Date().toISOString(),
        citations: [],
      };

      setMessages((prev) => [...prev, userMsg]);
      setInput("");
      setLoading(true);

      // Simüle edilmiş AI gecikmesi
      await new Promise<void>((resolve) => setTimeout(resolve, 800));

      const matched = MOCK_ASSISTANT_KNOWLEDGE[text];
      const assistantMsg: ChatMessage = matched
        ? {
            id: makeId(),
            role: "assistant",
            content: matched.reply,
            timestamp: new Date().toISOString(),
            citations: matched.citations,
          }
        : {
            id: makeId(),
            role: "assistant",
            content: NOT_FOUND_REPLY,
            timestamp: new Date().toISOString(),
            citations: [], // Boş dizi → kaynak kartı gizlenir
          };

      setMessages((prev) => [...prev, assistantMsg]);
      setLoading(false);
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    },
    [input, loading],
  );

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      {/* Üst Başlık */}
      <div className="mb-4 flex items-center justify-between border-b pb-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            🤖 Miço Usta AI Tekne Asistanı
          </h1>
          <p className="text-xs text-gray-500">
            Kayıtlı Tekneniz: <strong className="text-slate-800">Poyraz (Motoryat 42)</strong> • Kalamış Marina
          </p>
        </div>
        <span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700 border border-emerald-200">
          ● Çevrimiçi &amp; Servis Geçmişi Bağlı
        </span>
      </div>

      {/* Hızlı Soru Öneri Butonları */}
      <div className="mb-3 flex flex-wrap gap-2">
        {PRESET_QUESTIONS.map((q) => (
          <button
            key={q}
            type="button"
            onClick={() => void sendMessage(q)}
            disabled={loading}
            className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm hover:border-sky-300 hover:bg-sky-50 transition-all disabled:opacity-50"
          >
            💬 {q}
          </button>
        ))}
      </div>

      {/* Mesaj Listesi */}
      <div className="flex-1 overflow-y-auto rounded-xl border border-gray-200 bg-white p-5 space-y-4 shadow-sm">
        {messages.map((msg) => {
          const isUser = msg.role === "user";
          const hasCitations =
            !isUser && Array.isArray(msg.citations) && msg.citations.length > 0;

          return (
            <div
              key={msg.id}
              className={`flex ${isUser ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[80%] rounded-2xl p-4 text-sm ${
                  isUser
                    ? "bg-sky-600 text-white rounded-br-sm"
                    : "bg-slate-100 text-slate-900 rounded-bl-sm border border-slate-200"
                }`}
              >
                <p className="leading-relaxed whitespace-pre-wrap">{msg.content}</p>

                {/* Kaynak Atıf Kartları (citations dizisi) */}
                {hasCitations && (
                  <div className="mt-3 space-y-2">
                    {msg.citations!.map((c, idx) => (
                      <div
                        key={idx}
                        className="rounded-lg border border-sky-200 bg-sky-50/80 p-2.5 text-xs text-slate-800"
                      >
                        <div className="flex items-center gap-1.5 font-bold text-sky-800">
                          <span>📌</span>
                          <span>{c.sourceTitle}</span>
                          <span className="text-[10px] text-slate-400">({c.date})</span>
                        </div>
                        {c.excerpt && (
                          <p className="mt-1 text-[11px] text-slate-600 italic">
                            &ldquo;{c.excerpt}&rdquo;
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {/* "Bulamadım" bilgi notu — asistan yanıtı ama citations yok */}
                {!isUser && !hasCitations && msg.id !== "msg-welcome" && (
                  <p className="mt-2 text-[11px] text-slate-400 italic">
                    ℹ️ Bu yanıt için kayıt kaynağı bulunamadı.
                  </p>
                )}

                {msg.timestamp && (
                  <p
                    className={`mt-2 text-[10px] ${
                      isUser ? "text-sky-200" : "text-gray-400"
                    }`}
                  >
                    {new Date(msg.timestamp).toLocaleTimeString("tr-TR")}
                  </p>
                )}
              </div>
            </div>
          );
        })}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-slate-100 rounded-2xl rounded-bl-sm p-3 text-xs text-slate-500 border border-slate-200">
              <span className="animate-pulse">Miço Usta veritabanından sorguluyor…</span>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Mesaj Giriş Alanı */}
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
          placeholder="Tekneniz veya bakım kayıtları hakkında soru sorun…"
          className="flex-1 rounded-xl border border-gray-300 px-4 py-2.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
          disabled={loading}
        />
        <button
          onClick={() => void sendMessage()}
          disabled={loading || !input.trim()}
          className="rounded-xl bg-sky-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-sky-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          Gönder
        </button>
      </div>
    </div>
  );
}
