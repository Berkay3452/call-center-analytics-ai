"use client";

import { useRole } from "@/lib/role-context";
import type { Role } from "@/lib/types";
import { ThemeToggle } from "@/components/ThemeToggle";

const ROLE_LABELS: Record<Role, string> = {
  admin: "🛡️ Admin",
  owner: "⚓ Tekne Sahibi",
};

export function Header() {
  const { role, setRole } = useRole();

  return (
    <header className="flex h-16 items-center justify-between border-b border-gray-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-6 transition-colors">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-gray-500 dark:text-slate-400">
          Çağrı Analitiği Sistemi
        </span>
      </div>

      <div className="flex items-center gap-4">
        {/* Tema Seçici */}
        <ThemeToggle />

        {/* Rol seçici */}
        <div className="flex items-center gap-2 border-l border-gray-200 dark:border-slate-700 pl-4">
          <span className="text-xs text-gray-500 dark:text-slate-400">Rol:</span>
          <select
            value={role}
            onChange={(e) => setRole(e.target.value as Role)}
            className="rounded-lg border border-gray-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-1.5 text-xs font-semibold text-gray-700 dark:text-slate-200 shadow-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
            aria-label="Rol seç"
          >
            <option value="admin">{ROLE_LABELS.admin}</option>
            <option value="owner">{ROLE_LABELS.owner}</option>
          </select>
        </div>
      </div>
    </header>
  );
}
