"""Genel mimari, çağrı analitiği akışı ve agent orkestratörü şemalarını (01, 02, 04) üretir.

Çalıştırma (depo kökünden):  python docs/diagrams/kaynak/mimari_semalari.py
Çıktı: docs/diagrams/01_genel_mimari.png, 02_cagri_analitigi.png, 04_agent_orkestrator.png

Renk anlamı: mor = yapay zekâ agent'ı / modülü, mavi = servis, turuncu = dış hizmet,
yeşil = veri, kırmızı = hata yolu, kalın mor çerçeve = son sürümde eklenen parça.
Sistem değişince şemalar ve `Sistem_mimarisi_v*.md` aynı işte güncellenir.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon

OUT = Path(__file__).resolve().parent.parent

C = {
    "agent": ("#ede7ff", "#7e57c2"),
    "servis": ("#e1effe", "#4285c4"),
    "dis": ("#fff0d9", "#d19a2a"),
    "veri": ("#e4f4e6", "#3d9a52"),
    "hata": ("#fde4e4", "#c0392b"),
    "alan": ("#fffde0", "#b8b04a"),
    "kisi": ("#ffefd5", "#c4962a"),
}
INK = "#222222"


class Canvas:
    def __init__(self, w: float, h: float, wu: float = 100, hu: float = 100):
        self.fig, self.ax = plt.subplots(figsize=(w, h), dpi=110)
        self.ax.set_xlim(0, wu)
        self.ax.set_ylim(0, hu)
        self.ax.axis("off")

    def box(self, x, y, w, h, text, kind="servis", fs=9.5, shape="round", new=False, dashed=False):
        fc, ec = C[kind]
        style = "round,pad=0,rounding_size=%s" % (min(w, h) / 2 if shape == "pill" else 0.7)
        p = FancyBboxPatch(
            (x, y), w, h, boxstyle=style, fc=fc, ec="#7e57c2" if new else ec,
            lw=2.8 if new else 1.5, ls="--" if dashed else "-", zorder=2,
        )
        self.ax.add_patch(p)
        self.ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs,
                     color=INK, linespacing=1.4, zorder=3)

    def zone(self, x, y, w, h, label, fs=10.5):
        fc, ec = C["alan"]
        p = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.8",
                           fc=fc, ec=ec, lw=1.2, zorder=0)
        self.ax.add_patch(p)
        self.ax.text(x + w / 2, y + h - 1.2, label, ha="center", va="top", fontsize=fs, color="#444")

    def diamond(self, cx, cy, hw, hh, text, fs=9.5):
        fc, ec = C["agent"]
        self.ax.add_patch(Polygon([(cx - hw, cy), (cx, cy + hh), (cx + hw, cy), (cx, cy - hh)],
                                  closed=True, fc=fc, ec=ec, lw=1.5, zorder=2))
        self.ax.text(cx, cy, text, ha="center", va="center", fontsize=fs, color=INK, zorder=3)

    def line(self, pts, arrow=True, dotted=False, label=None, lpos=None, lw=1.4):
        xs, ys = zip(*pts)
        ls = (0, (2, 2)) if dotted else "-"
        if arrow:
            self.ax.plot(xs[:-1], ys[:-1], color="#333", lw=lw, ls=ls, zorder=1,
                         solid_capstyle="butt")
            self.ax.add_patch(FancyArrowPatch(pts[-2], pts[-1], arrowstyle="-|>", mutation_scale=11,
                                              color="#333", lw=lw, ls=ls, zorder=1,
                                              shrinkA=0, shrinkB=0))
        else:
            self.ax.plot(xs, ys, color="#333", lw=lw, ls=ls, zorder=1)
        if label:
            lx, ly = lpos or ((xs[0] + xs[-1]) / 2, (ys[0] + ys[-1]) / 2)
            self.ax.text(lx, ly, label, fontsize=8.5, ha="center", va="center", color="#333",
                         bbox={"fc": "white", "ec": "none", "pad": 1.5}, zorder=4)

    def note(self, x, y, text, fs=9, color="#555"):
        self.ax.text(x, y, text, ha="center", va="center", fontsize=fs, color=color, linespacing=1.5)

    def save(self, name: str):
        self.fig.savefig(OUT / name, bbox_inches="tight", pad_inches=0.25, facecolor="white")
        plt.close(self.fig)
        print("yazıldı:", OUT / name)


def genel_mimari() -> None:
    c = Canvas(13, 11.5, 100, 100)
    c.box(14, 92, 20, 5, "Admin / İşletme", "kisi", shape="pill")
    c.box(44, 92, 20, 5, "Tekne Sahibi", "kisi", shape="pill")

    c.zone(3, 66, 94, 23, "Miço Usta (hazır uygulama)")
    c.box(7, 69, 46, 12.5,
          "Next.js arayüz\nAdmin · Tekne Sahibi · Usta panelleri\nsunucu tarafı vekil rota, servis anahtarları\n"
          "canlı transkript pop-up · duygu rozeti", "servis", fs=9)
    c.box(62, 74.5, 30, 8, ".NET 10 API\nentegrasyon yöntemi\nhocadan bekleniyor", "servis", fs=9)
    c.box(68, 68.5, 18, 4, "PostgreSQL · Redis", "veri", fs=9)
    c.line([(24, 92), (24, 90.5), (24, 81.5)], arrow=True)
    c.line([(54, 92), (54, 91), (40, 91), (40, 81.5)], arrow=True)
    c.line([(53, 77), (62, 77)], dotted=True, label="olası yol", lpos=(57.5, 79))
    c.line([(77, 74.5), (77, 72.5)], arrow=True)

    c.line([(20, 69), (20, 59)], arrow=True, label="REST · JSON · SSE", lpos=(20, 64))

    c.zone(1.5, 1, 97, 57, "Bizim AI servisimiz (Python 3.12 · FastAPI)")
    c.box(5, 44, 38, 10,
          "REST API\nservis anahtarı · imzalı kimlik ve rol\nhız sınırı · denetim günlüğü · SSE akışı", "servis", fs=9)
    c.box(50, 44, 45, 10,
          "Celery işçisi + Beat\nkuyruk: Redis · canlı transkript: Redis Stream\ntakılı çağrı kurtarma, KVKK temizliği",
          "servis", fs=9)
    c.line([(43, 49), (50, 49)], arrow=True)

    # veri yolu
    c.line([(24, 44), (24, 40), (88, 40)], arrow=False)
    c.line([(72.5, 44), (72.5, 40)], arrow=False)
    for x in (17, 46.5, 70.5, 88.5):
        c.line([(x, 40), (x, 37)], arrow=True)

    c.box(5, 26, 25, 11, "Çağrı Analizi\nSTT → 5 agent + orkestratör\n(LangGraph)", "agent", fs=9)
    c.box(33, 26, 27, 11, "Miço AI\nplanlayıcı · hibrit arama\naraçlar · takip sorusu", "agent", fs=9)
    c.box(63, 26, 16, 11, "CRM inceleme\nonayla · reddet\n→ servis emri", "servis", fs=9)
    c.box(81, 26, 16, 11, "KPI ve analitik\nözet uçları\nduygu dağılımı", "servis", fs=9)

    c.box(5, 9, 19, 12, "Konuşma tanıma\n(STT)\nfaster-whisper (yerel)\nWhisper API · stub", "dis", fs=8.5, shape="pill")
    c.box(27, 9, 23, 12, "LLM (ayardan seçilir)\nNVIDIA ücretsiz: hızlı +\ngüçlü katman, yedek model\nGemini/Vertex uyumu", "dis", fs=8.5, shape="pill")
    c.box(53, 9, 15, 12, "Embedding\nbge-m3\n(TEI konteyneri)", "dis", fs=8.5, shape="pill")
    c.box(5, 3, 19, 4, "Ses depolama (yerel/GCS)", "veri", fs=8)
    c.box(75, 3, 22, 20, "AI veritabanı\nPostgreSQL 17 + pgvector\n\nçağrılar, analiz (duygu\ndahil), CRM incelemesi,\nsohbet, RAG parçaları,\nkullanıcı hesapları,\ndenetim günlüğü", "veri", fs=8.5)

    c.line([(14, 26), (14, 21)], arrow=True)
    c.line([(29, 26), (29, 21)], arrow=True)
    c.line([(42, 26), (42, 21)], arrow=True)
    c.line([(57, 26), (57, 21)], arrow=True)
    c.line([(71.5, 26), (71.5, 15), (75, 15)], arrow=True)
    c.line([(89, 26), (89, 23)], arrow=True)
    c.note(50, -3, "Güvenlik katmanı beş güven sınırında uygulanır: S0 şeması ve docs/guvenlik_mimarisi.md", fs=8.5)
    c.ax.set_ylim(-6, 100)
    c.save("01_genel_mimari.png")


def cagri_analitigi() -> None:
    c = Canvas(11.5, 13, 100, 100)
    c.box(2, 90, 18, 8, "Çağrı\nses kaydı + bilgisi\n(zaman, süre, sonuç)", "agent", fs=8.5, shape="pill")
    c.box(23, 90, 17, 8, "Celery kuyruğu\n(Redis) · 202", "servis", fs=8.5)
    c.box(43, 90, 27, 8, "Konuşma tanıma (STT)\nstereo: temsilci sol, müşteri sağ\nsegmentler, konuşmacı ayrımı", "dis", fs=8.5)
    c.box(74, 90, 24, 8, "Kişisel veri maskeleme\n(LLM'e maskeli metin gider)", "servis", fs=8.5)
    c.line([(20, 94), (23, 94)])
    c.line([(40, 94), (43, 94)])
    c.line([(70, 94), (74, 94)])

    c.box(43, 76, 27, 9,
          "Canlı transkript (yalnız yönetici)\nRedis Stream → SSE → pop-up\nparçalar zamana göre sıralı", "servis", fs=8.5, dashed=True, new=True)
    c.line([(56.5, 90), (56.5, 85)], dotted=True)

    c.box(26, 66, 46, 7,
          "Beş agent tek aşamada paralel çalışır\n(ANALYSIS_CLASSIFIER_FIRST=false)", "servis", fs=9, shape="pill")
    c.line([(86, 90), (86, 69.5), (72, 69.5)])

    names = [
        "Çağrı Sınıflandırma\nAgent'ı\nçağrı tipi",
        "CRM Bilgi Çıkarım\nAgent'ı\n7 alan",
        "Satış Analiz\nAgent'ı\nsonuç, kayıp nedeni",
        "Özetleme\nAgent'ı\nkısa özet",
        "Duygu Analiz\nAgent'ı (yeni)\nduygu + şikâyet",
    ]
    xs = [1.5, 21, 40.5, 60, 79.5]
    for i, (x, t) in enumerate(zip(xs, names)):
        c.box(x, 50, 19, 11, t, "agent", fs=8.5, new=(i == 4))
        c.line([(49, 66), (x + 9.5, 61)])
    for x in xs:
        c.line([(x + 9.5, 50), (49, 44)], arrow=False)
    c.line([(49, 44), (49, 41)])

    c.box(22, 31, 54, 10,
          "Orkestratör: şema doğrulama · hata varsa agent'a 1 düzeltme şansı\nLLM zaman aşımı → yedek model · agent çalışması kaydı (agent_runs)",
          "servis", fs=8.8)
    c.box(80, 31, 19, 10, "Yeniden analiz\n(arayüzden): yeni sürüm,\neski sürüm saklanır", "servis", fs=8.2)
    c.line([(80, 36), (76, 36)], dotted=True)

    c.line([(49, 31), (49, 27)])
    c.diamond(49, 22, 20, 5, "Tüm agent'lar başarılı mı?")
    c.box(76, 16, 23, 12, "Durum: kısmi / başarısız\nbaşarılı agent sonuçları\nkorunur (ör. duygu boş\nkalırsa diğerleri geçerli)", "hata", fs=8.2)
    c.line([(69, 22), (76, 22)], label="hayır", lpos=(72.5, 24))
    c.line([(49, 17), (49, 12.5)], label="evet · tamam", lpos=(56, 14.8))

    c.box(14, 5, 70, 7.5,
          "Müşteri-tekne eşleştirme (telefon, ad + tekne) → AI veritabanı: analiz sürümü + agent kayıtları",
          "veri", fs=8.8)
    c.line([(87.5, 16), (87.5, 8.7), (84, 8.7)])
    c.box(1, -4, 30, 6, "Çağrı Analitiği (KPI)\n+ duygu dağılımı, şikâyet sayısı", "veri", fs=8.2)
    c.box(35, -4, 33, 6, "CRM önerisi → admin onayı\n→ servis emri", "veri", fs=8.2)
    c.box(72, -4, 27, 6, "Takılı çağrı kurtarma (Beat)", "hata", fs=8.2)
    c.line([(30, 5), (16, 2)])
    c.line([(52, 5), (52, 2)])
    c.ax.set_ylim(-8, 100)
    c.save("02_cagri_analitigi.png")


def agent_orkestrator() -> None:
    c = Canvas(11, 13.2, 100, 130)
    c.box(30, 120, 40, 8, "Analiz başlat\nçağrı kimliği", "agent", fs=10, shape="pill")
    c.box(24, 104, 52, 8, "Transkripti yükle\n(maskeli metin, konuşmacı etiketli)", "servis", fs=10)
    c.line([(50, 120), (50, 112)])
    c.box(35, 90, 30, 7, "paralel", "agent", fs=10.5, shape="pill")
    c.line([(50, 104), (50, 97)])
    names = [
        "Çağrı\nSınıflandırma\nAgent'ı\nçağrı tipi:\nyeni müşteri,\nservis, teklif,\nacil, bilgi",
        "CRM Bilgi\nÇıkarım Agent'ı\ntalep, lokasyon,\nproblem, aciliyet,\nsonraki aksiyon",
        "Satış Analiz\nAgent'ı\nsonuç ve kayıp\nnedeni (fiyat,\ngeç dönüş...)",
        "Özetleme\nAgent'ı\nkısa görüşme\nözeti",
        "Duygu Analiz\nAgent'ı (yeni)\nolumlu / nötr /\nolumsuz + şikâyet\nbayrağı, gerekçe",
    ]
    xs = [0.5, 20.5, 40.5, 60.5, 80.5]
    for i, (x, t) in enumerate(zip(xs, names)):
        c.box(x, 56, 19, 22, t, "agent", fs=9, new=(i == 4))
        c.line([(50, 90), (x + 9.5, 78)])
        c.line([(x + 9.5, 56), (50, 49)], arrow=False)
    c.box(38, 43, 24, 6, "birleş", "agent", fs=10.5, shape="pill")
    c.box(18, 27, 64, 10,
          "Orkestratör: her çıktıyı şemasıyla doğrular,\nhatada agent'a tek düzeltme turu, agent başına süre bütçesi",
          "servis", fs=10)
    c.line([(50, 43), (50, 37)])
    c.box(22, 11, 56, 10, "Analiz sonucu + CRM önerisi\n+ eşleştirme (veritabanı)", "veri", fs=10, shape="pill")
    c.line([(50, 27), (50, 21)])
    c.box(25, -4, 50, 8, "Durum: tamam · kısmi · başarısız", "agent", fs=10, shape="pill")
    c.line([(50, 11), (50, 4)])
    c.note(50, -11,
           "Beş agent tek aşamada paralel çalışır (ANALYSIS_CLASSIFIER_FIRST=false).\n"
           "Bir agent çökerse diğerlerinin sonucu korunur, analiz \"kısmi\" olur.\n"
           "LLM kota/zaman aşımında yedek modele geçilir.", fs=9)
    c.ax.set_ylim(-16, 130)
    c.save("04_agent_orkestrator.png")


if __name__ == "__main__":
    genel_mimari()
    cagri_analitigi()
    agent_orkestrator()
