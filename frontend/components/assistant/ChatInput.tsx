import React, { useState, useRef, useEffect, useCallback } from "react";

interface ChatInputProps {
  onSendMessage: (content: string) => void;
  disabled?: boolean;
  placeholder?: string;
  onStopStreaming?: () => void;
  isStreaming?: boolean;
}

export function ChatInput({
  onSendMessage,
  disabled = false,
  placeholder = "Tekneniz veya bakım kayıtları hakkında soru sorun… (Örn: Son motor bakımı ne zamandı?)",
  onStopStreaming,
  isStreaming = false,
}: ChatInputProps) {
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Otomatik yükseklik ayarlama
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 140)}px`;
    }
  }, [text]);

  const handleSubmit = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed || disabled || isStreaming) return;
    onSendMessage(trimmed);
    setText("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [text, disabled, isStreaming, onSendMessage]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="relative flex items-end gap-2 rounded-2xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 p-2 shadow-sm transition-all focus-within:border-sky-500 focus-within:ring-2 focus-within:ring-sky-500/20">
      <label htmlFor="assistant-chat-input" className="sr-only">
        Soru giriş kutusu
      </label>
      <textarea
        id="assistant-chat-input"
        ref={textareaRef}
        rows={1}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={disabled || isStreaming}
        aria-label="Tekneniz hakkında soru sorun"
        className="max-h-[140px] min-h-[38px] flex-1 resize-none bg-transparent px-2.5 py-1.5 text-sm text-slate-900 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:outline-none disabled:opacity-50"
      />

      <div className="flex items-center gap-1.5 shrink-0 self-end">
        {isStreaming && onStopStreaming ? (
          <button
            type="button"
            onClick={onStopStreaming}
            className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-500 text-white transition-colors hover:bg-amber-600 focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-900"
            title="Akışı Durdur"
            aria-label="Akışı Durdur"
          >
            <svg
              className="w-4 h-4"
              fill="currentColor"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <rect x="6" y="6" width="12" height="12" rx="2" />
            </svg>
          </button>
        ) : (
          <button
            type="button"
            onClick={handleSubmit}
            disabled={disabled || !text.trim()}
            className="flex h-9 items-center gap-1.5 rounded-xl bg-sky-700 px-4 text-xs font-semibold text-white shadow-xs transition-all hover:bg-sky-800 focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-900 disabled:opacity-40 disabled:cursor-not-allowed"
            aria-label="Mesajı Gönder"
          >
            <span>Gönder</span>
            <svg
              className="w-3.5 h-3.5"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5"
              />
            </svg>
          </button>
        )}
      </div>
    </div>
  );
}
