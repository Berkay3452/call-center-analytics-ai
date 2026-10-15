"use client";

import { useSyncExternalStore } from "react";
import { useTheme, type Theme } from "@/lib/theme-context";

const THEME_OPTIONS: Array<{ value: Theme; label: string; icon: string }> = [
  { value: "light", label: "Açık", icon: "☀️" },
  { value: "dark", label: "Koyu", icon: "🌙" },
  { value: "system", label: "Sistem", icon: "💻" },
];

const emptySubscribe = () => () => {};

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const mounted = useSyncExternalStore(
    emptySubscribe,
    () => true,
    () => false,
  );

  if (!mounted) {
    return (
      <div className="flex h-8 w-24 items-center justify-center rounded-lg bg-gray-100 dark:bg-slate-800" />
    );
  }

  return (
    <div
      className="flex items-center rounded-lg border border-gray-200 dark:border-slate-700 bg-gray-50 dark:bg-slate-800/80 p-0.5 shadow-sm"
      role="group"
      aria-label="Tema seçimi"
    >
      {THEME_OPTIONS.map((opt) => {
        const isActive = theme === opt.value;
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => setTheme(opt.value)}
            title={`${opt.label} Tema`}
            aria-pressed={isActive}
            className={`flex items-center gap-1 rounded-md px-2 py-1 text-xs font-semibold transition-all ${
              isActive
                ? "bg-white dark:bg-slate-900 text-sky-700 dark:text-sky-400 shadow-sm"
                : "text-gray-500 dark:text-slate-400 hover:text-gray-800 dark:hover:text-slate-200"
            }`}
          >
            <span className="text-xs">{opt.icon}</span>
            <span className="hidden sm:inline">{opt.label}</span>
          </button>
        );
      })}
    </div>
  );
}
