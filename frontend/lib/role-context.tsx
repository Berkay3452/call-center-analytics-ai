/**
 * Rol yönetimi için React context.
 *
 * Gerçek auth olmadan URL veya state tabanlı rol seçimi sağlar.
 * Miço Usta entegrasyonunda bu context JWT claim'leri ile beslenecektir.
 */
"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { Role } from "@/lib/types";

// ---------------------------------------------------------------------------
// Context tipi
// ---------------------------------------------------------------------------
interface RoleContextValue {
  role: Role;
  setRole: (role: Role) => void;
}

const RoleContext = createContext<RoleContextValue | null>(null);

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------
interface RoleProviderProps {
  children: ReactNode;
  defaultRole?: Role;
}

export function RoleProvider({
  children,
  defaultRole = "admin",
}: RoleProviderProps) {
  const [role, setRoleState] = useState<Role>(defaultRole);

  const setRole = useCallback((next: Role) => {
    setRoleState(next);
  }, []);

  const value = useMemo<RoleContextValue>(
    () => ({ role, setRole }),
    [role, setRole],
  );

  return <RoleContext.Provider value={value}>{children}</RoleContext.Provider>;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------
export function useRole(): RoleContextValue {
  const ctx = useContext(RoleContext);
  if (!ctx) {
    throw new Error("useRole must be used within a <RoleProvider>");
  }
  return ctx;
}
