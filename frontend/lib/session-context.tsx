/**
 * Oturum bilgisi için React context (#372): sunucuda doğrulanmış oturum (rol, ad, müşteri kimliği)
 * kök yerleşimden verilir. Tarayıcı rolü kendisi seçemez; bu değerler yalnızca gösterim ve
 * yönlendirme içindir, yetkiyi sunucu (proxy + backend) verir.
 */
"use client";

import { createContext, useContext, type ReactNode } from "react";
import type { Role } from "@/lib/types";

export interface ClientSession {
  role: Role;
  name: string;
  /** Tekne sahibi için müşteri kimliği; yönetici için null. */
  customerId: string | null;
}

const SessionContext = createContext<ClientSession | null>(null);

export function SessionProvider({
  session,
  children,
}: {
  session: ClientSession | null;
  children: ReactNode;
}) {
  return <SessionContext.Provider value={session}>{children}</SessionContext.Provider>;
}

/** Oturum yoksa (giriş sayfası) null döner. */
export function useSession(): ClientSession | null {
  return useContext(SessionContext);
}
