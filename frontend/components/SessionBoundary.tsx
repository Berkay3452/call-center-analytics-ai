import { cookies } from "next/headers";
import { AnalysisTracker } from "@/components/AnalysisTracker";
import { AppShell } from "@/components/layout/AppShell";
import { SessionProvider, type ClientSession } from "@/lib/session-context";
import { SESSION_COOKIE, getSessionKey, verifySessionToken } from "@/lib/server/session";

/**
 * Oturumu sunucuda okuyup (imza + süre doğrulanır) istemci bileşenlerine verir (#372). Çerez
 * okumak sayfayı istek anında üretir (`cacheComponents` açık); bu yüzden kök yerleşimde bir
 * `Suspense` sınırı içinde kullanılır. Tarayıcı rolü kendisi seçemez.
 */
export async function SessionBoundary({ children }: { children: React.ReactNode }) {
  const key = await getSessionKey(process.env);
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  const verified = key ? await verifySessionToken(token, key) : null;
  const session: ClientSession | null = verified
    ? { role: verified.role, name: verified.name, customerId: verified.cid }
    : null;

  return (
    <SessionProvider session={session}>
      <AnalysisTracker>
        <AppShell>{children}</AppShell>
      </AnalysisTracker>
    </SessionProvider>
  );
}
