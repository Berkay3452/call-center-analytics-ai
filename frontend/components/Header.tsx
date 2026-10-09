"use client";

import { useRole } from "@/lib/role-context";
import type { Role } from "@/lib/types";

const ROLE_LABELS: Record<Role, string> = {
  admin: "🛡️ Admin",
  owner: "⚓ Tekne Sahibi",
};

// ---------------------------------------------------------------------------
// Bileşen
// ---------------------------------------------------------------------------
export function Header() {
  const { role, setRole } = useRole();

  return (
    <header className="flex h-16 items-center justify-between border-b border-gray-200 bg-white px-6">
      {/* Sayfa başlığı yerini Next.js layout'u ile dolduracak bileşenler alır */}
      <div className="flex items-center gap-2">
        <span className="text-sm text-gray-500">Çağrı Analitiği Sistemi</span>
      </div>

      {/* Rol seçici */}
      <div className="flex items-center gap-3">
        <span className="text-xs text-gray-400">Rol:</span>
        <select
          value={role}
          onChange={(e) => setRole(e.target.value as Role)}
          className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          aria-label="Rol seç"
        >
          <option value="admin">{ROLE_LABELS.admin}</option>
          <option value="owner">{ROLE_LABELS.owner}</option>
        </select>
      </div>
    </header>
  );
}
