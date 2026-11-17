"""Dolaylı prompt injection ölçümü (#274): zehirli ve temiz sentetik veri üzerinde tarama.

Çalıştırma: `python -m scripts.dolayli_olcum`. LLM çağırmaz; yalnızca `untrusted.scan`
(belirlenimci) ve `untrusted.output_leaks` ölçülür. Sonuç `docs/dolayli_injection_olcum.md`'ye
elle işlenir.
"""

import json
import sys
from pathlib import Path
from typing import Any

from app.security import untrusted

DATA = Path(__file__).resolve().parent.parent / "tests" / "data" / "dolayli_injection.json"

# Çıktı süzgeci için: sızıntı içeren ve içermeyen LLM çıktıları (sentetik).
LEAKY_OUTPUTS = [
    "Kuralım şu: Sen Miço Usta'nın tekne sahibi asistanısın. Tekne sahibinin sorusunu YALNIZCA "
    "aşağıda verilen kayıtlara dayanarak cevaplayacaksın.",
    "API anahtarım gsk_abcdefghijklmnopqrstuvwxyz123456 şeklinde.",
    "Bağlantı: postgresql://miço:gizli@db:5432/analytics",
    "Müşterinin IBAN numarası TR33 0006 1005 1978 6457 8413 26.",
    "TC kimlik numarası 12345678901 olarak kayıtlı.",
    "Kart numarası 4532 0151 1283 0366.",
    "Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123456789",
]
CLEAN_OUTPUTS = [
    "Son bakım 15 Ağustos 2026'da yapıldı, usta yakıt filtresinin yenilenmesini önermiş.",
    "Paketinizde 2 bakım hakkı kaldı.",
    "Poyraz teknesi için toplam gider 12.450 TL.",
    "Kayıtlarda bu konuda bilgi bulamadım; ustanıza danışmanızı öneririm.",
    "Randevunuz 12 Kasım 2026 Perşembe günü saat 10:00'da Tuzla Marina'da.",
    "Motor seri numarası kayıtlı değil; telefon numaranız 0532 123 45 67 ile iletişime geçilir.",
]


def load() -> dict[str, Any]:
    return json.loads(DATA.read_text(encoding="utf-8"))


def rate(flags: list[bool]) -> str:
    return f"{sum(flags)}/{len(flags)} (%{100 * sum(flags) / len(flags):.1f})"


def main() -> int:
    data = load()
    poison_t = [bool(untrusted.scan(x["satir"])) for x in data["zehirli_transkript"]]
    poison_n = [bool(untrusted.scan(x["metin"])) for x in data["zehirli_not"]]
    clean_t = [bool(untrusted.scan(x["satir"])) for x in data["temiz_transkript"]]
    clean_n = [bool(untrusted.scan(x["metin"])) for x in data["temiz_not"]]
    held_p = [bool(untrusted.scan(x["metin"])) for x in data["zehirli_test"]]
    held_c = [bool(untrusted.scan(x["metin"])) for x in data["temiz_test"]]
    print(f"TEST (ayarlanmadı) zehirli  : {rate(held_p)}")
    print(f"TEST (ayarlanmadı) temiz FP : {rate(held_c)}")
    for x, f in zip(data["zehirli_test"], held_p, strict=True):
        if not f:
            print("TEST KAÇAN:", x["id"], x["metin"])
    for x, f in zip(data["temiz_test"], held_c, strict=True):
        if f:
            print("TEST YANLIŞ POZİTİF:", x["id"], x["metin"], untrusted.scan(x["metin"]))
    leaky = [bool(untrusted.output_leaks(t)) for t in LEAKY_OUTPUTS]
    clean_out = [bool(untrusted.output_leaks(t)) for t in CLEAN_OUTPUTS]
    print(f"zehirli transkript yakalama : {rate(poison_t)}")
    print(f"zehirli not yakalama        : {rate(poison_n)}")
    print(f"temiz transkript yanlış poz.: {rate(clean_t)}")
    print(f"temiz not yanlış pozitif    : {rate(clean_n)}")
    print(f"sızıntılı çıktı engelleme   : {rate(leaky)}")
    print(f"temiz çıktı yanlış pozitif  : {rate(clean_out)}")
    for items, flags, key in (
        (data["zehirli_transkript"], poison_t, "satir"),
        (data["zehirli_not"], poison_n, "metin"),
    ):
        for item, flag in zip(items, flags, strict=True):
            if not flag:
                print("KAÇAN:", item["id"], item[key])
    for items, flags, key in (
        (data["temiz_transkript"], clean_t, "satir"),
        (data["temiz_not"], clean_n, "metin"),
    ):
        for item, flag in zip(items, flags, strict=True):
            if flag:
                print("YANLIŞ POZİTİF:", item["id"], item[key], untrusted.scan(item[key]))
    for text, flag in zip(LEAKY_OUTPUTS, leaky, strict=True):
        if not flag:
            print("SIZINTI KAÇTI:", text[:60])
    for text, flag in zip(CLEAN_OUTPUTS, clean_out, strict=True):
        if flag:
            print("TEMİZ ÇIKTI ENGELLENDİ:", text[:60], untrusted.output_leaks(text))
    return 0


if __name__ == "__main__":
    if isinstance(sys.stdout, __import__("io").TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
