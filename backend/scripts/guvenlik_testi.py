"""Güvenlik paketini (`tests/security/`) tek komutla çalıştırır, geçti/kaldı tablosu basar (#276).

Kullanım (backend/ klasöründe):

    python -m scripts.guvenlik_testi             # veritabanı gerektirmeyenler (CI ile aynı)
    python -m scripts.guvenlik_testi --db        # RUN_DB_TESTS=1: sahip izolasyonu da gerçek DB ile
    python -m scripts.guvenlik_testi --markdown  # tabloyu docs/guvenlik_testi.md biçiminde yazar

Çıkış kodu: kalan test yoksa 0. "Bilinen sınırlama" (xfail) kalan sayılmaz, ayrı sütunda görünür.
"""

import argparse
import io
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).parents[1]

# Test modülü -> (saldırı sınıfı, OWASP LLM Top 10 (2025), OWASP API Security Top 10 (2023))
SINIFLAR: dict[str, tuple[str, str, str]] = {
    "test_kimlik_saldirilari": ("Kimlik doğrulama ve yetki yükseltme", "LLM06", "API2, API5, API8"),
    "test_imzali_kimlik_saldirilari": (
        "İmzalı kullanıcı kimliği (sahte/yeniden oynatılan imza, rol yükseltme)",
        "LLM06",
        "API1, API2",
    ),
    "test_sahip_izolasyonu_integration": ("Sahip izolasyonu (IDOR/BOLA)", "LLM06, LLM02", "API1"),
    "test_prompt_injection_saldirilari": (
        "Prompt injection (doğrudan, gizlenmiş, dolaylı) ve çıktı sızıntısı",
        "LLM01, LLM02, LLM07",
        "-",
    ),
    "test_maskeleme_sizinti": ("Kişisel veri (maskeleme) sızıntısı", "LLM02", "API3"),
    "test_hiz_siniri_ve_kaynak_tuketimi": ("Hız sınırı ve kaynak tüketimi", "LLM10", "API4"),
    "test_yetkisiz_arac_kullanimi": ("Yetkisiz araç / aşırı yetki", "LLM06", "API5"),
    "test_yetki_haritasi": ("Yazma uçlarında işlev düzeyi yetki", "LLM06", "API5"),
    "test_owasp_eslesmesi": ("Eşleme tablosunun doğruluğu", "-", "-"),
}


@dataclass
class Sonuc:
    gecti: int = 0
    kaldi: int = 0
    atlandi: int = 0
    bilinen_sinir: int = 0

    @property
    def toplam(self) -> int:
        return self.gecti + self.kaldi + self.atlandi + self.bilinen_sinir


def calistir(db: bool) -> tuple[dict[str, Sonuc], int]:
    env = {**os.environ, "APP_ENV": "test"}
    if db:
        env["RUN_DB_TESTS"] = "1"
    with tempfile.TemporaryDirectory() as tmp:
        xml_yolu = Path(tmp) / "guvenlik.xml"
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/security",
                "-q",
                "-p",
                "no:cacheprovider",
                f"--junitxml={xml_yolu}",
            ],
            cwd=BACKEND,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        if not xml_yolu.exists():
            sys.stderr.write(proc.stdout + proc.stderr)
            raise SystemExit("pytest sonuç dosyası üretmedi")
        sonuclar = ayristir(xml_yolu)
    if proc.returncode not in (0, 1):
        sys.stderr.write(proc.stdout + proc.stderr)
    return sonuclar, proc.returncode


def ayristir(xml_yolu: Path) -> dict[str, Sonuc]:
    sonuclar: dict[str, Sonuc] = {}
    for case in ET.parse(xml_yolu).getroot().iter("testcase"):
        modul = (case.get("classname") or "").rsplit(".", 1)[-1]
        s = sonuclar.setdefault(modul, Sonuc())
        skipped = case.find("skipped")
        if case.find("failure") is not None or case.find("error") is not None:
            s.kaldi += 1
        elif skipped is not None:
            # xfail: JUnit'te `skipped type="pytest.xfail"`; gerçek atlama: pytest.skip.
            if skipped.get("type") == "pytest.xfail":
                s.bilinen_sinir += 1
            else:
                s.atlandi += 1
        else:
            s.gecti += 1
    return sonuclar


def tablo(sonuclar: dict[str, Sonuc], markdown: bool) -> str:
    basliklar = [
        "Saldırı sınıfı",
        "OWASP LLM",
        "OWASP API",
        "Geçti",
        "Kaldı",
        "Atlandı",
        "Sınırlama",
    ]
    satirlar: list[list[str]] = []
    toplam = Sonuc()
    for modul, (ad, llm, api) in SINIFLAR.items():
        s = sonuclar.get(modul)
        if s is None:
            continue
        satirlar.append(
            [ad, llm, api, str(s.gecti), str(s.kaldi), str(s.atlandi), str(s.bilinen_sinir)]
        )
        toplam.gecti += s.gecti
        toplam.kaldi += s.kaldi
        toplam.atlandi += s.atlandi
        toplam.bilinen_sinir += s.bilinen_sinir
    satirlar.append(
        [
            "**Toplam**" if markdown else "Toplam",
            "",
            "",
            str(toplam.gecti),
            str(toplam.kaldi),
            str(toplam.atlandi),
            str(toplam.bilinen_sinir),
        ]
    )
    if markdown:
        cikti = ["| " + " | ".join(basliklar) + " |", "|" + "---|" * len(basliklar)]
        cikti += ["| " + " | ".join(r) + " |" for r in satirlar]
        return "\n".join(cikti)
    genislik = [max(len(r[i]) for r in [basliklar, *satirlar]) for i in range(len(basliklar))]
    cikti = ["  ".join(c.ljust(w) for c, w in zip(basliklar, genislik, strict=True))]
    cikti.append("  ".join("-" * w for w in genislik))
    cikti += ["  ".join(c.ljust(w) for c, w in zip(r, genislik, strict=True)) for r in satirlar]
    return "\n".join(cikti)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--db", action="store_true", help="veritabanı testlerini de çalıştır")
    ap.add_argument("--markdown", action="store_true", help="tabloyu Markdown olarak yaz")
    args = ap.parse_args()

    sonuclar, kod = calistir(args.db)
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    print(tablo(sonuclar, args.markdown))
    kalan = sum(s.kaldi for s in sonuclar.values())
    durum = "BAŞARILI" if kalan == 0 else "BAŞARISIZ"
    print(f"\n{durum}: {kalan} kalan test (pytest çıkış kodu {kod})")
    return 0 if kalan == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
