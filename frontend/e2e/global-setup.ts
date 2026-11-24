import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import type { FullConfig } from "@playwright/test";
import { storageStateFor } from "./auth";

export const AUTH_DIR = path.join(__dirname, ".auth");

/** Varsayılan oturum yönetici; sahip sayfaları `fixtures.ts` ile sahip çerezini kullanır. */
export default async function globalSetup(config: FullConfig) {
  const baseURL = config.projects[0].use.baseURL ?? "http://localhost:3000";
  await mkdir(AUTH_DIR, { recursive: true });
  await writeFile(path.join(AUTH_DIR, "admin.json"), JSON.stringify(await storageStateFor("admin", baseURL)));
  await writeFile(path.join(AUTH_DIR, "owner.json"), JSON.stringify(await storageStateFor("owner", baseURL)));
}
