/**
 * Tarayıcının gönderdiği `x-user-id`'nin vekil rotada imzalanıp iletilip iletilmeyeceği (#266).
 *
 * Oturum/giriş (#265) yokken tarayıcı kimliğini imzalamak, istemcinin herhangi bir sahibi
 * taklit etmesine izin verir; bu yüzden YALNIZCA yerel geliştirmede açılabilir. Canlıda
 * (`NODE_ENV=production`) bayrak true olsa bile, ortam açıkça `APP_ENV=local|test` demedikçe
 * kimlik imzalanmaz ve düşürülür (APP_ENV eksikse de reddedilir).
 */

export type Env = Record<string, string | undefined>;

export interface BrowserUserIdDecision {
  allow: boolean;
  /** Bayrak istendi ama canlı kapısı reddetti: hata günlüğüne yazılmalı. */
  refusedInProduction: boolean;
}

export function decideBrowserUserId(env: Env): BrowserUserIdDecision {
  if (env.ALLOW_BROWSER_USER_ID !== "true") {
    return { allow: false, refusedInProduction: false };
  }
  const isProd = env.NODE_ENV === "production";
  const localEnv = env.APP_ENV === "local" || env.APP_ENV === "test";
  if (isProd && !localEnv) {
    return { allow: false, refusedInProduction: true };
  }
  return { allow: true, refusedInProduction: false };
}
