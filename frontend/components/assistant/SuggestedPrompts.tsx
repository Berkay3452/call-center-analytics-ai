import React from "react";

export const DEFAULT_SUGGESTIONS = [
  "Son bakım ne zaman yapıldı?",
  "Bu ay ne kadar harcadım?",
  "Yakında yapılması gereken bir şey var mı?",
  "Sintine alarmı çaldığında ilk ne yapmalıyım?",
];

interface SuggestedPromptsProps {
  prompts?: string[];
  onSelectPrompt: (prompt: string) => void;
  disabled?: boolean;
  className?: string;
}

/** Girdi çubuğunun üstünde yatay kaydırılabilen kısa soru seçenekleri. */
export function SuggestedPrompts({
  prompts = DEFAULT_SUGGESTIONS,
  onSelectPrompt,
  disabled = false,
  className = "",
}: SuggestedPromptsProps) {
  return (
    <div className={className} role="group" aria-label="Hazır soru önerileri">
      <p className="sr-only text-sm font-medium text-slate-600">Şunlardan birini sorabilirsiniz</p>
      <div className="flex min-w-0 gap-2 overflow-x-auto p-1">
        {prompts.map((prompt) => (
          <button
            key={prompt}
            type="button"
            onClick={() => onSelectPrompt(prompt)}
            disabled={disabled}
            className="max-w-[min(80vw,22rem)] shrink-0 rounded-full border border-slate-300 bg-slate-50 px-3 py-2 text-left text-xs text-slate-800 transition-colors hover:border-brand-300 hover:bg-brand-50 focus-visible:ring-2 focus-visible:ring-brand-500 disabled:pointer-events-none disabled:opacity-50"
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
}
