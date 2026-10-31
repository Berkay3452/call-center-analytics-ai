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

/** Hazır soru kartları: sohbetin ilk ekranında görünür. */
export function SuggestedPrompts({
  prompts = DEFAULT_SUGGESTIONS,
  onSelectPrompt,
  disabled = false,
  className = "",
}: SuggestedPromptsProps) {
  return (
    <div className={className} role="group" aria-label="Hazır soru önerileri">
      <p className="mb-2 text-sm font-medium text-slate-600">Şunlardan birini sorabilirsiniz</p>
      <div className="grid gap-2 sm:grid-cols-2">
        {prompts.map((prompt) => (
          <button
            key={prompt}
            type="button"
            onClick={() => onSelectPrompt(prompt)}
            disabled={disabled}
            className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-left text-sm text-slate-800 transition-colors hover:border-brand-300 hover:bg-brand-50 disabled:pointer-events-none disabled:opacity-50"
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
}
