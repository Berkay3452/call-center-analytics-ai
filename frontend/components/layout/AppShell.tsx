"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { useSession } from "@/lib/session-context";
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
  const session = useSession();
  const [signingOut, setSigningOut] = useState(false);

  // Giriş sayfasında kabuk (üst bar, sekmeler) gösterilmez (#371).
  if (pathname.startsWith("/login")) return <>{children}</>;

  const effectiveRole: Role = pathname.startsWith("/owner")
    ? "owner"
    : pathname.startsWith("/admin")
      ? "admin"
      : (session?.role ?? "admin");
  const tabs = TABS[effectiveRole];
  const workspace = WORKSPACE_TITLES[effectiveRole];

  const handleSignOut = async () => {
    setSigningOut(true);
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } finally {
      router.replace("/login");
      router.refresh();
    }
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
              Miço{" "}<span className="text-orange-400">Usta</span>
            </Link>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-2.5 py-1 text-xs font-medium">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" aria-hidden="true" />
              {ROLE_LABELS[effectiveRole]}
            </span>
          </div>

          <div className="flex items-center gap-3">
            {session && (
              <span className="hidden max-w-[16rem] truncate text-xs text-white/80 sm:inline" data-testid="session-name">
                {session.name}
              </span>
            )}
            <button
              type="button"
              onClick={handleSignOut}
              disabled={signingOut}
              className="rounded-lg border border-white/20 bg-white/10 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-white/20 disabled:opacity-60"
            >
              {signingOut ? "Çıkılıyor…" : "Çıkış"}
            </button>
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
