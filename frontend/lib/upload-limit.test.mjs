import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import config from "../next.config.ts";

test("vekil gövde sınırı, arayüzün izin verdiği ses boyutundan büyük (#390)", async () => {
  const page = await readFile(new URL("../app/admin/calls/upload/page.tsx", import.meta.url), "utf8");
  const audioMb = Number(page.match(/MAX_AUDIO_BYTES = (\d+) \* 1024 \* 1024/)?.[1]);
  const proxyMb = Number(String(config.experimental?.proxyClientMaxBodySize).match(/^(\d+)mb$/)?.[1]);
  assert.ok(audioMb > 0, "MAX_AUDIO_BYTES okunamadı");
  assert.ok(proxyMb > audioMb, `vekil sınırı ${proxyMb} MB, ses sınırı ${audioMb} MB`);
});
