"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRole } from "@/lib/role-context";
import type { Role } from "@/lib/types";

interface NavItem {
  href: string;
  label: string;
  icon: string;
}

const ADMIN_NAV: NavItem[] = [
  { href: "/admin/analytics", label: "Çağrı Analitiği", icon: "📊" },
  { href: "/admin/calls", label: "Çağrılar", icon: "📞" },
  { href: "/admin/calls/upload", label: "Çağrı Yükle", icon: "🎙️" },
  { href: "/admin/crm", label: "CRM Önerisi", icon: "💡" },
];

const OWNER_NAV: NavItem[] = [
  { href: "/owner/assistant", label: "Asistan", icon: "🤖" },
];

const NAV_MAP: Record<Role, NavItem[]> = {
  admin: ADMIN_NAV,
  owner: OWNER_NAV,
};

export function Sidebar() {
  const pathname = usePathname();
  const { role } = useRole();
  const navItems = NAV_MAP[role];

  return (
    <aside className="flex h-full w-56 flex-col border-r border-gray-200 dark:border-slate-800 bg-white dark:bg-slate-900 transition-colors">
      {/* Logo */}
      <div className="flex h-16 items-center px-4 border-b border-gray-200 dark:border-slate-800">
        <span className="text-lg font-bold text-sky-600 dark:text-sky-400">⚓ Miço Usta</span>
      </div>

      {/* Navigasyon */}
      <nav className="flex-1 overflow-y-auto p-3 space-y-1">
        {navItems.map((item) => {
          const isActive =
            item.href === "/admin/calls"
              ? pathname === "/admin/calls" || /^\/admin\/calls\/[0-9a-fA-F-]+$/.test(pathname)
              : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? "bg-sky-50 dark:bg-sky-950/70 text-sky-700 dark:text-sky-300 font-semibold border border-sky-100 dark:border-sky-800/50 shadow-sm"
                  : "text-gray-600 dark:text-slate-300 hover:bg-gray-100 dark:hover:bg-slate-800 hover:text-gray-900 dark:hover:text-white"
              }`}
            >
              <span>{item.icon}</span>
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      {/* Sürüm */}
      <div className="p-4 text-xs text-gray-400 dark:text-slate-500 border-t border-gray-100 dark:border-slate-800">
        v0.1.0 — Miço Usta
      </div>
    </aside>
  );
}

export function SidebarFallback() {
  return (
    <aside className="flex h-full w-56 flex-col border-r border-gray-200 dark:border-slate-800 bg-white dark:bg-slate-900">
      <div className="flex h-16 items-center px-4 border-b border-gray-200 dark:border-slate-800">
        <span className="text-lg font-bold text-sky-600 dark:text-sky-400">⚓ Miço Usta</span>
      </div>
      <nav className="flex-1 p-3 space-y-1">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="h-9 rounded-lg bg-gray-100 dark:bg-slate-800 animate-pulse"
          />
        ))}
      </nav>
    </aside>
  );
}
