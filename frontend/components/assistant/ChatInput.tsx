import React, { useState, useRef, useEffect, useCallback } from "react";
import { Button } from "@/components/ui";

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
  placeholder = "Tekneniz veya bakım kayıtları hakkında soru sorun…",
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
  }, [text, disabled, isStreaming, onSendMessage]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="flex items-end gap-2 rounded-xl border border-slate-300 bg-white p-2 focus-within:border-brand-500">
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
        className="max-h-[140px] min-h-[38px] flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-slate-900 placeholder:text-slate-500 focus:outline-none disabled:opacity-50"
      />
      {isStreaming && onStopStreaming ? (
        <Button variant="secondary" onClick={onStopStreaming} aria-label="Akışı Durdur">
          Durdur
        </Button>
      ) : (
        <Button onClick={handleSubmit} disabled={disabled || !text.trim()} aria-label="Mesajı Gönder">
          Gönder
        </Button>
      )}
    </div>
  );
}
