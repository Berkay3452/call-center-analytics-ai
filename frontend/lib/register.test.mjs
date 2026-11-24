// Çalıştırma: `npm run test:unit` (Node >= 22.18, yerleşik test koşucusu).
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  isEmail,
  normalizePhone,
  passwordProblems,
  registerErrorMessage,
  validateBoat,
  validateRegister,
} from "./register.ts";

const OK = {
  firstName: "Ayşe",
  lastName: "Demir",
  phone: "0532 123 45 67",
  email: "ayse.demir@example.com",
  password: "Güçlü-Parola_26",
  passwordConfirm: "Güçlü-Parola_26",
};

test("passwordProblems: 12 karakter, büyük harf, küçük harf ve özel sembol zorunlu", () => {
  assert.deepEqual(passwordProblems("Güçlü-Parola_26"), []);
  assert.ok(passwordProblems("Ab!kisa").some((p) => p.includes("12 karakter")));
  assert.ok(passwordProblems("kucukharfsadece!!").some((p) => p.includes("büyük harf")));
  assert.ok(passwordProblems("BUYUKHARFSADECE!!").some((p) => p.includes("küçük harf")));
  assert.ok(passwordProblems("SembolsuzParola123").some((p) => p.includes("özel sembol")));
  assert.ok(passwordProblems("Boşluk Boşluk Boşluk").some((p) => p.includes("özel sembol")));
});

test("normalizePhone: TR cep biçimleri +905xxxxxxxxx olur, diğerleri reddedilir", () => {
  for (const raw of ["+90 532 123 45 67", "05321234567", "5321234567", "(0532) 123-45-67"]) {
    assert.equal(normalizePhone(raw), "+905321234567");
  }
  assert.equal(normalizePhone("0212 123 45 67"), null);
  assert.equal(normalizePhone("12345"), null);
});

test("isEmail", () => {
  assert.ok(isEmail("a@b.co"));
  assert.ok(!isEmail("a@b"));
  assert.ok(!isEmail("ab.com"));
});

test("validateRegister: geçerli form hatasız; eksik/uyuşmayan alanlar işaretlenir", () => {
  assert.deepEqual(validateRegister(OK), {});
  const bad = validateRegister({ ...OK, firstName: " ", email: "x", passwordConfirm: "baska" });
  assert.deepEqual(Object.keys(bad).sort(), ["email", "firstName", "passwordConfirm"]);
});

test("registerErrorMessage: sunucu iletisi 409/422'de korunur", () => {
  assert.equal(registerErrorMessage(409, "Bu bilgilerle kayıt yapılamadı."), "Bu bilgilerle kayıt yapılamadı.");
  assert.match(registerErrorMessage(429), /Çok fazla/);
  assert.match(registerErrorMessage(503), /yapılamıyor/);
});

test("validateBoat: ad zorunlu, yıl 1950 ile gelecek yıl arasında", () => {
  assert.deepEqual(validateBoat({ name: "Rüzgar", model: "", year: "", marina: "" }, 2026), {});
  assert.ok(validateBoat({ name: " ", model: "", year: "", marina: "" }, 2026).name);
  assert.ok(validateBoat({ name: "T", model: "", year: "1900", marina: "" }, 2026).year);
  assert.ok(validateBoat({ name: "T", model: "", year: "2099", marina: "" }, 2026).year);
  assert.ok(validateBoat({ name: "T", model: "", year: "20.5", marina: "" }, 2026).year);
  assert.deepEqual(validateBoat({ name: "T", model: "", year: "2027", marina: "" }, 2026), {});
});
