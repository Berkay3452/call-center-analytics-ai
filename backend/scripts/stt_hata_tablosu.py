"""STT hata tablosu (#328): `stt_benchmark --out` çıktısından sınıflandırılmış hata özeti.

Kullanım (backend/ klasöründe):

    python -m scripts.stt_benchmark --audio <klasör> --out sonuc.json
    python -m scripts.stt_hata_tablosu sonuc.json            # Markdown tablo yazdırır
    python -m scripts.stt_hata_tablosu sonuc.json --top 30

Hata sınıfları: `marka`, `parca`, `yer`, `tekne_adi`, `gun_ay`, `sayi` (alan terimleri, kaynak
`tests/data/stt_referans/terimler.json`), `biçim` (rakam/sözcük ya da ek ayrımı farkı: tanıma
hatası değil), `genel` (diğer sözcükler).
"""

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

CLASS_NOTE = {
    "marka": "Yabancı marka/model: ses benzerliği yüksek, Türkçe okunuşla yazılıyor. "
    "initial_prompt/hotwords ve düzeltme sözlüğü.",
    "parca": "Teknik parça adı: benzer sesli Türkçe sözcüğe kayıyor. Büyük model, initial_prompt, "
    "hotwords.",
    "yer": "İl/ilçe/marina adı: özel ad; ek ve ayırma hatası. Alan sözlüğü ve hotwords.",
    "tekne_adi": "Tekne adı (sıradan Türkçe sözcük): bağlama dayalı; sözlük sınırlı yardım eder.",
    "gun_ay": "Gün/ay adı: ek ayrımı ve nadir ses hatası. Düşük öncelik.",
    "sayi": "Sayı: yanlış duyulan sayı (rakam/sözcük farkı `biçim` sınıfında). Büyük model.",
    "biçim": "Rakam/sözcük ve ek ayrımı: tanıma doğru, yazım tercihi farklı. Düzeltme gerekmez; "
    "ölçümde ayrı tutulur.",
    "genel": "Terim olmayan sözcükler: ses kalitesi ve model kapasitesi. Büyük model.",
}


def summarize(rows: list[dict[str, Any]], top: int) -> str:
    ok = [r for r in rows if "errors" in r]
    if not ok:
        return "Hata verisi yok (benchmark `--out` ile, referans metinli ses üzerinde çalışmalı)."
    errors = [e for r in ok for e in r["errors"]]
    by_class = Counter(e["sinif"] for e in errors)
    lines = [f"Dosya: {len(ok)}, hata öbeği: {len(errors)}", ""]
    lines += ["| Sınıf | Hata öbeği | Not |", "|---|---|---|"]
    for cls, count in by_class.most_common():
        lines.append(f"| {cls} | {count} | {CLASS_NOTE.get(cls, '')} |")

    hit: Counter[str] = Counter()
    total: Counter[str] = Counter()
    for r in ok:
        for cat, (h, t) in (r.get("terms") or {}).items():
            hit[cat] += h
            total[cat] += t
    if total:
        lines += ["", "| Terim sınıfı | Doğru / toplam | Doğruluk |", "|---|---|---|"]
        for cat in total:
            lines.append(
                f"| {cat} | {hit[cat]} / {total[cat]} | %{100 * hit[cat] / total[cat]:.0f} |"
            )
        lines.append(
            f"| **tümü** | {sum(hit.values())} / {sum(total.values())} | "
            f"**%{100 * sum(hit.values()) / sum(total.values()):.0f}** |"
        )

    term_errors = [e for e in errors if e["sinif"] not in ("genel", "biçim")]
    lines += [
        "",
        f"Terim hataları (ilk {top}):",
        "",
        "| Sınıf | Beklenen | Yazılan | Tür |",
        "|---|---|---|---|",
    ]
    for e in term_errors[:top]:
        lines.append(f"| {e['sinif']} | {e['ref'] or '—'} | {e['cikti'] or '—'} | {e['tur']} |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path, help="stt_benchmark --out JSON dosyası")
    parser.add_argument("--top", type=int, default=25, help="Listelenecek terim hatası sayısı")
    args = parser.parse_args()
    rows = json.loads(args.results.read_text(encoding="utf-8"))
    print(summarize(rows, args.top))


if __name__ == "__main__":
    main()
