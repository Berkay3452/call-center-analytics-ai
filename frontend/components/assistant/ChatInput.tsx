import React, {
  useState,
  useRef,
  useEffect,
  useCallback,
  useSyncExternalStore,
} from "react";
import { Button } from "@/components/ui";

export const MAX_QUESTION_LENGTH = 5000;

const subscribeToHydration = () => () => {};

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
  const hydrated = useSyncExternalStore(
    subscribeToHydration,
    () => true,
    () => false,
  );
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
        disabled={!hydrated || disabled}
        maxLength={MAX_QUESTION_LENGTH}
        className="max-h-[140px] min-h-[38px] min-w-0 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-slate-900 placeholder:text-slate-500 focus:outline-none disabled:opacity-50"
      />
      {text.length > MAX_QUESTION_LENGTH * 0.8 && (
        <span className="self-center text-xs text-slate-500" aria-live="polite">
          {text.length}/{MAX_QUESTION_LENGTH}
        </span>
      )}
      {isStreaming && onStopStreaming ? (
        <Button
          variant="secondary"
          onClick={onStopStreaming}
          aria-label="Akışı Durdur"
        >
          Durdur
        </Button>
      ) : (
        <Button
          onClick={handleSubmit}
          disabled={disabled || !text.trim()}
          aria-label="Mesajı Gönder"
        >
          Gönder
        </Button>
      )}
    </div>
  );
}
