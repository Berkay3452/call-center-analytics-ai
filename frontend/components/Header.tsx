"use client";

import { usePathname, useRouter } from "next/navigation";
import { useRole } from "@/lib/role-context";
import type { Role } from "@/lib/types";
import { ThemeToggle } from "@/components/ThemeToggle";

const ROLE_LABELS: Record<Role, string> = {
  admin: "🛡️ Admin",
  owner: "⚓ Tekne Sahibi",
};

export function Header() {
  const router = useRouter();
  const pathname = usePathname();
  const { role, setRole } = useRole();

  const effectiveRole: Role = pathname.startsWith("/owner")
    ? "owner"
    : pathname.startsWith("/admin")
      ? "admin"
      : role;

  const handleRoleChange = (newRole: Role) => {
    setRole(newRole);
    if (newRole === "owner") {
      router.push("/owner/assistant");
    } else if (newRole === "admin") {
      router.push("/admin/analytics");
    }
  };

  return (
    <header className="flex min-h-16 h-auto flex-wrap items-center justify-between gap-3 border-b border-gray-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-4 sm:px-6 py-2 sm:py-0 transition-colors">
      <div className="flex items-center gap-2 min-w-0">
        <span className="text-sm font-medium text-gray-600 dark:text-slate-300 truncate">
          Çağrı Analitiği Sistemi
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-3 sm:gap-4">
        {/* Tema Seçici */}
        <ThemeToggle />

        {/* Rol seçici */}
        <div className="flex items-center gap-2 border-l border-gray-200 dark:border-slate-700 pl-3 sm:pl-4">
          <label htmlFor="header-role-select" className="text-xs text-gray-500 dark:text-slate-400 shrink-0">
            Rol:
          </label>
          <span className="rounded-full bg-amber-50 dark:bg-amber-950/60 px-2 py-0.5 text-[10px] font-semibold text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800 shrink-0">
            Simülasyon
          </span>
          <select
            id="header-role-select"
            value={effectiveRole}
            onChange={(e) => handleRoleChange(e.target.value as Role)}
            className="rounded-lg border border-gray-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-2.5 py-1.5 text-xs font-semibold text-gray-700 dark:text-slate-200 shadow-sm focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-900"
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
