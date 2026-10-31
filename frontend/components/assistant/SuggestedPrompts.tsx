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

export function SuggestedPrompts({
  prompts = DEFAULT_SUGGESTIONS,
  onSelectPrompt,
  disabled = false,
  className = "",
}: SuggestedPromptsProps) {
  return (
    <div
      className={`flex flex-wrap items-center gap-2 ${className}`}
      role="group"
      aria-label="Hazır Soru Önerileri"
    >
      <span className="text-xs font-semibold text-slate-500 flex items-center gap-1 mr-1">
        <svg
          className="w-3.5 h-3.5 text-sky-700"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth="2"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M13 10V3L4 14h7v7l9-11h-7z"
          />
        </svg>
        Önerilen:
      </span>
      {prompts.map((prompt) => (
        <button
          key={prompt}
          type="button"
          onClick={() => onSelectPrompt(prompt)}
          disabled={disabled}
          className="group inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-2xs transition-all hover:border-sky-400 hover:bg-sky-50/70 hover:text-sky-900 focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 disabled:opacity-50 disabled:pointer-events-none"
        >
          <span className="text-sky-700 group-hover:scale-110 transition-transform">💬</span>
          <span>{prompt}</span>
        </button>
      ))}
    </div>
  );
}
