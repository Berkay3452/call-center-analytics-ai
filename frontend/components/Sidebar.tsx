/**
 * Sidebar — rol'e göre navigasyon.
 *
 * Next.js 16: usePathname() prerender sırasında client hook olduğu için
 * bu bileşenin kendisi Suspense içinde render edilmeli.
 * Bkz. app/layout.tsx → <Suspense> sarmalayıcısı.
 */
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRole } from "@/lib/role-context";
import type { Role } from "@/lib/types";

// ---------------------------------------------------------------------------
// Navigasyon öğeleri
// ---------------------------------------------------------------------------
interface NavItem {
  href: string;
  label: string;
  icon: string;
}

const ADMIN_NAV: NavItem[] = [
  { href: "/admin/analytics", label: "Çağrı Analitiği", icon: "📊" },
  { href: "/admin/calls", label: "Çağrılar", icon: "📞" },
  { href: "/admin/crm", label: "CRM Önerisi", icon: "💡" },
];

const OWNER_NAV: NavItem[] = [
  { href: "/owner/assistant", label: "Asistan", icon: "🤖" },
];

const NAV_MAP: Record<Role, NavItem[]> = {
  admin: ADMIN_NAV,
  owner: OWNER_NAV,
};

// ---------------------------------------------------------------------------
// Bileşen
// ---------------------------------------------------------------------------
export function Sidebar() {
  const pathname = usePathname();
  const { role } = useRole();
  const navItems = NAV_MAP[role];

  return (
    <aside className="flex h-full w-56 flex-col border-r border-gray-200 bg-white">
      {/* Logo */}
      <div className="flex h-16 items-center px-4 border-b border-gray-200">
        <span className="text-lg font-bold text-blue-600">⚓ Miço Usta</span>
      </div>

      {/* Navigasyon */}
      <nav className="flex-1 overflow-y-auto p-3 space-y-1">
        {navItems.map((item) => {
          const isActive = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? "bg-blue-50 text-blue-700"
                  : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
              }`}
            >
              <span>{item.icon}</span>
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      {/* Sürüm */}
      <div className="p-4 text-xs text-gray-400 border-t border-gray-100">
        v0.1.0 — iskelet
      </div>
    </aside>
  );
}

/**
 * Sidebar için statik fallback — Suspense sınırı içinde sunucu tarafında render edilir.
 */
export function SidebarFallback() {
  return (
    <aside className="flex h-full w-56 flex-col border-r border-gray-200 bg-white">
      <div className="flex h-16 items-center px-4 border-b border-gray-200">
        <span className="text-lg font-bold text-blue-600">⚓ Miço Usta</span>
      </div>
      <nav className="flex-1 p-3 space-y-1">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="h-9 rounded-lg bg-gray-100 animate-pulse"
          />
        ))}
      </nav>
    </aside>
  );
}
