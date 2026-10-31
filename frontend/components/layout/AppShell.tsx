"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useRole } from "@/lib/role-context";
import type { Role } from "@/lib/types";

interface TabItem {
  href: string;
  label: string;
}

const ADMIN_TABS: TabItem[] = [
  { href: "/admin/analytics", label: "Gösterge Paneli" },
  { href: "/admin/calls", label: "Çağrılar" },
  { href: "/admin/crm", label: "CRM Önerileri" },
  { href: "/admin/service-orders", label: "Servis Emirleri" },
];

const OWNER_TABS: TabItem[] = [{ href: "/owner/assistant", label: "Miço AI" }];

const TABS: Record<Role, TabItem[]> = {
  admin: ADMIN_TABS,
  owner: OWNER_TABS,
};

const ROLE_LABELS: Record<Role, string> = {
  admin: "Admin",
  owner: "Tekne Sahibi",
};

const ROLE_HOME: Record<Role, string> = {
  admin: "/admin/analytics",
  owner: "/owner/assistant",
};

const WORKSPACE_TITLES: Record<Role, { eyebrow: string; title: string }> = {
  admin: { eyebrow: "Admin çalışma alanı", title: "Operasyon ve Çağrı Analitiği" },
  owner: { eyebrow: "Tekne sahibi portalı", title: "Miço AI Asistanı" },
};

/** Çağrı detayı (/admin/calls/[id]) ve yükleme sayfası "Çağrılar" sekmesinin altında kalır. */
function isTabActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

/**
 * Uygulama kabuğu: lacivert üst bar (logo, rol rozeti, rol seçici) ve altında sekmeli gezinme.
 * Yan menü yoktur; sayfa içeriği tek sütunda, tam genişlikte akar.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { role, setRole } = useRole();

  const effectiveRole: Role = pathname.startsWith("/owner")
    ? "owner"
    : pathname.startsWith("/admin")
      ? "admin"
      : role;
  const tabs = TABS[effectiveRole];
  const workspace = WORKSPACE_TITLES[effectiveRole];

  const handleRoleChange = (next: Role) => {
    setRole(next);
    router.push(ROLE_HOME[next]);
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="bg-[#0a2540] text-white">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between gap-3 px-4 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <Link
              href={ROLE_HOME[effectiveRole]}
              className="text-lg font-bold tracking-tight"
              aria-label="Miço Usta ana sayfa"
            >
              Miço<span className="text-orange-400">Usta</span>
            </Link>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-2.5 py-1 text-xs font-medium">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" aria-hidden="true" />
              {ROLE_LABELS[effectiveRole]}
            </span>
          </div>

          <div className="flex items-center gap-2">
            <label htmlFor="header-role-select" className="hidden text-xs text-white/70 sm:inline">
              Rol (simülasyon)
            </label>
            <select
              id="header-role-select"
              value={effectiveRole}
              onChange={(e) => handleRoleChange(e.target.value as Role)}
              className="rounded-lg border border-white/20 bg-white/10 px-2.5 py-1.5 text-xs font-medium text-white"
              aria-label="Rol seç"
            >
              <option value="admin" className="text-slate-900">
                {ROLE_LABELS.admin}
              </option>
              <option value="owner" className="text-slate-900">
                {ROLE_LABELS.owner}
              </option>
            </select>
          </div>
        </div>
      </header>

      <div className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-7xl px-4 sm:px-6">
          <div className="py-4">
            <p className="text-xs font-semibold uppercase tracking-widest text-teal-700">
              {workspace.eyebrow}
            </p>
            <p className="text-lg font-semibold text-[#0a2540]">{workspace.title}</p>
          </div>
          <nav aria-label="Ana gezinme" className="-mb-px flex gap-1 overflow-x-auto pb-3">
            {tabs.map((tab) => {
              const active = isTabActive(pathname, tab.href);
              return (
                <Link
                  key={tab.href}
                  href={tab.href}
                  aria-current={active ? "page" : undefined}
                  className={`whitespace-nowrap rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
                    active
                      ? "bg-[#0a3356] text-white"
                      : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                  }`}
                >
                  {tab.label}
                </Link>
              );
            })}
          </nav>
        </div>
      </div>

      <main className="mx-auto w-full max-w-7xl min-w-0 px-4 py-6 sm:px-6">{children}</main>
    </div>
  );
}
