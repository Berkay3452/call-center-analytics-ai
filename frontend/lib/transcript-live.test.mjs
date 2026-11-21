// Çalıştırma: `npm run test:unit` (Node >= 22.18, yerleşik test koşucusu).
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  MAX_SEGMENTS,
  formatMs,
  groupTurns,
  initialLiveState,
  parseSegment,
  reduceLive,
} from "./transcript-live.ts";

const seg = (seq, speaker, text, start = seq * 1000) => ({
  seq,
  speaker,
  start_ms: start,
  end_ms: start + 900,
  text,
});
const feed = (events) => events.reduce(reduceLive, initialLiveState);

test("segmentler gelir ve durum canli olur", () => {
  const s = feed([{ type: "open" }, { type: "segment", data: seg(1, "rep", "Merhaba") }]);
  assert.equal(s.status, "canli");
  assert.deepEqual(s.segments.map((x) => x.text), ["Merhaba"]);
});

test("aynı seq iki kez gelirse tekilleştirilir (yeniden bağlanma)", () => {
  const s = feed([
    { type: "segment", data: seg(1, "rep", "bir") },
    { type: "segment", data: seg(1, "rep", "bir") },
    { type: "segment", data: seg(2, "customer", "iki") },
  ]);
  assert.equal(s.segments.length, 2);
});

test("sıra dışı gelen parça zamana göre yerine konur", () => {
  const s = feed([
    { type: "segment", data: seg(2, "customer", "ikinci", 5000) },
    { type: "segment", data: seg(1, "rep", "birinci", 1000) },
  ]);
  assert.deepEqual(s.segments.map((x) => x.text), ["birinci", "ikinci"]);
});

test("geçersiz veri yok sayılır, bilinmeyen konuşmacı unknown olur", () => {
  assert.equal(parseSegment(null), null);
  assert.equal(parseSegment({ seq: "1", start_ms: 0, end_ms: 1, text: "x" }), null);
  assert.equal(parseSegment({ seq: 1, start_ms: 0, end_ms: 1, text: "   " }), null);
  assert.equal(
    parseSegment({ seq: 1, start_ms: 0, end_ms: 1, text: "x", speaker: "<script>" }).speaker,
    "unknown",
  );
  assert.equal(feed([{ type: "segment", data: { bozuk: true } }]).segments.length, 0);
});

test("metin uzunluğu ve liste boyutu sınırlıdır", () => {
  assert.equal(parseSegment(seg(1, "rep", "a".repeat(5000))).text.length, 2000);
  let s = initialLiveState;
  for (let i = 1; i <= MAX_SEGMENTS + 5; i++) {
    s = reduceLive(s, { type: "segment", data: seg(i, "rep", "x") });
  }
  assert.equal(s.segments.length, MAX_SEGMENTS);
});

test("bitiş olayları durumu kalıcı yapar; kopma bitmiş durumu bozmaz", () => {
  assert.equal(feed([{ type: "done" }, { type: "disconnect" }]).status, "bitti");
  assert.equal(feed([{ type: "error" }, { type: "open" }]).status, "hata");
  assert.equal(feed([{ type: "timeout" }, { type: "disconnect" }]).status, "zaman_asimi");
  assert.equal(feed([{ type: "open" }, { type: "disconnect" }]).status, "kopuk");
  assert.equal(feed([{ type: "open" }, { type: "disconnect" }, { type: "open" }]).status, "canli");
});

test("bitmiş akışta geç gelen parça durumu canliya çevirmez", () => {
  const s = feed([{ type: "done" }, { type: "segment", data: seg(1, "rep", "geç") }]);
  assert.equal(s.status, "bitti");
});

test("ardışık aynı konuşmacı parçaları birleşir", () => {
  const turns = groupTurns(
    feed([
      { type: "segment", data: seg(1, "rep", "Merhaba") },
      { type: "segment", data: seg(2, "rep", "buyurun") },
      { type: "segment", data: seg(3, "customer", "Motor tekliyor") },
    ]).segments,
  );
  assert.deepEqual(
    turns.map((t) => [t.speaker, t.text]),
    [
      ["rep", "Merhaba buyurun"],
      ["customer", "Motor tekliyor"],
    ],
  );
});

test("süre biçimi", () => {
  assert.equal(formatMs(0), "0:00");
  assert.equal(formatMs(65_000), "1:05");
});

test("turn olayları nihai cümleleri ayrı listeye koyar ve tekilleştirir", () => {
  const turn = (seq, speaker) => ({ type: "turn", data: { seq, speaker, start_ms: seq * 1000, end_ms: seq * 1000 + 500, text: `c${seq}` } });
  const s = feed([
    { type: "segment", data: { seq: 1, speaker: "unknown", start_ms: 0, end_ms: 900, text: "hepsi" } },
    turn(2, "rep"),
    turn(3, "customer"),
    turn(3, "customer"),
  ]);
  assert.equal(s.segments.length, 1);
  assert.deepEqual(s.finalSegments.map((x) => x.speaker), ["rep", "customer"]);
});
