"""ER diyagramını (docs/diagrams/er_diagram.png) SQLAlchemy modellerinden üretir.

İki adım (modeller Python 3.12 + bağımlılık ister, çizim yalnızca matplotlib):
  1. Tablo bilgisini modellerden çıkar (backend/ klasöründen):
         PYTHONPATH=. uv run --no-sync python ../docs/diagrams/kaynak/er_semasi.py --dump
     -> docs/diagrams/kaynak/er_tablolar.json  (backend/tests/test_docs_consistency.py modellerle
        farkı yakalar; model değişince bu adım unutulursa test kırılır)
  2. Çiz (matplotlib olan herhangi bir Python ile, depo kökünden):
         python docs/diagrams/kaynak/er_semasi.py

Yalnızca tabloların yerleşimi elle verilir. Kesikli çerçeve = dış kaynak (Miço Usta) tabloları.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "er_diagram.png"
JSON_PATH = HERE / "er_tablolar.json"

W, HEAD, ROW = 30.0, 3.2, 2.0
COLS = [0, 38, 76, 114, 152]

# (sütun, y) — y aşağı doğru artar
LAYOUT: dict[str, tuple[int, float]] = {
    "customers": (0, 0),
    "user_accounts": (0, 21),
    "chat_sessions": (0, 48),
    "chat_messages": (0, 66),
    "boats": (1, 0),
    "subscriptions": (1, 22),
    "boat_notes": (1, 48),
    "craftsmen": (1, 68),
    "rag_chunks": (1, 86),
    "service_orders": (2, 0),
    "expenses": (2, 30),
    "audit_log": (2, 54),
    "calls": (3, 0),
    "transcripts": (3, 46),
    "transcript_segments": (3, 64),
    "crm_reviews": (3, 86),
    "analysis_results": (4, 0),
    "agent_runs": (4, 64),
}
EXTERNAL = {"customers", "boats", "craftsmen", "service_orders", "boat_notes", "expenses", "subscriptions"}
NEW = {"sentiment", "sentiment_complaint", "sentiment_reason", "sentiment_evidence", "sentiment_confidence"}
PALETTE = ["#e8574f", "#8b6be0", "#e8944f", "#c04fe0", "#4fb27a", "#3aa7d6", "#d6b43a", "#4f6fe0", "#7fc24a"]


def dump() -> None:
    """Modellerden tablo, sütun ve yabancı anahtar bilgisini JSON'a yazar (adım 1)."""
    import app.db.models  # noqa: F401  (modelleri metadata'ya kaydeder)
    from app.db.base import Base

    doc = {}
    for t in sorted(Base.metadata.tables.values(), key=lambda t: t.name):
        cols = []
        for c in t.columns:
            fk = next(iter(c.foreign_keys), None)
            cols.append({
                "name": c.name,
                "type": str(c.type).lower().split("(")[0],
                "pk": bool(c.primary_key),
                "fk": f"{fk.column.table.name}.{fk.column.name}" if fk else None,
            })
        doc[t.name] = cols
    JSON_PATH.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("yazıldı:", JSON_PATH, len(doc), "tablo")


def type_name(raw: str) -> str:
    return {"timestamp": "timestamptz", "double precision": "float"}.get(raw, raw)


def draw() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    tables: dict[str, list[dict]] = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    missing = set(tables) - set(LAYOUT)
    assert not missing, f"Yerleşimde olmayan tablo: {missing}"
    pos = {n: (COLS[c], y, HEAD + ROW * len(tables[n])) for n, (c, y) in LAYOUT.items()}

    ymax = max(y + h for _, y, h in pos.values()) + 4
    n_far = sum(1 for n, cols in tables.items() for c in cols if c["fk"]
                and abs(LAYOUT[n][0] - LAYOUT[c["fk"].split(".")[0]][0]) >= 2)
    top = -3 - 1.6 * (n_far + 1)
    fig, ax = plt.subplots(figsize=(17, 17 * (ymax - top) / (COLS[-1] + W + 4)), dpi=110)
    ax.set_xlim(-2, COLS[-1] + W + 2)
    ax.set_ylim(ymax, top)
    ax.axis("off")
    color = {n: PALETTE[i % len(PALETTE)] for i, n in enumerate(sorted(LAYOUT))}

    def row_y(name: str, colname: str) -> float:
        _, y, _ = pos[name]
        names = [c["name"] for c in tables[name]]
        return y + HEAD + ROW * (names.index(colname) + 0.5)

    used: dict[int, int] = {}  # boşluk (gutter) -> kullanılan kanal sayısı

    def gutter(gap: int) -> float:
        n = used.get(gap, 0)
        used[gap] = n + 1
        return COLS[gap] + W + 4 + (-3.0 + 0.9 * n)  # gap i: sütun i ile i+1 arası

    far_lane = 0
    # ilişkiler: boşluklardan ve üst şeritlerden dik açılı yönlendirilir (tabloların üstünden geçmez)
    for name, cols in tables.items():
        for c in cols:
            if not c["fk"]:
                continue
            target, tcol = c["fk"].split(".")
            s, t = LAYOUT[name][0], LAYOUT[target][0]
            y1, y2 = row_y(name, c["name"]), row_y(target, tcol)
            if s == t:
                gx = gutter(s)
                pts = [(COLS[s] + W, y1), (gx, y1), (gx, y2), (COLS[t] + W, y2)]
            elif s < t:
                p1, p2 = (COLS[s] + W, y1), (COLS[t], y2)
                if t - s == 1:
                    gx = gutter(s)
                    pts = [p1, (gx, y1), (gx, y2), p2]
                else:
                    lane = -3 - 1.6 * far_lane
                    far_lane += 1
                    g1, g2 = gutter(s), gutter(t - 1)
                    pts = [p1, (g1, y1), (g1, lane), (g2, lane), (g2, y2), p2]
            else:
                p1, p2 = (COLS[s], y1), (COLS[t] + W, y2)
                if s - t == 1:
                    gx = gutter(t)
                    pts = [p1, (gx, y1), (gx, y2), p2]
                else:
                    lane = -3 - 1.6 * far_lane
                    far_lane += 1
                    g1, g2 = gutter(s - 1), gutter(t)
                    pts = [p1, (g1, y1), (g1, lane), (g2, lane), (g2, y2), p2]
            xs, ys = zip(*pts)
            ax.plot(xs, ys, color=color[target], lw=1.3, alpha=0.85, zorder=1, solid_joinstyle="round")
            ax.plot(*pts[0], "o", ms=3.5, color=color[target], zorder=1)  # çok (N) tarafı
            ax.plot(*pts[-1], "|", ms=7, color=color[target], zorder=1)  # bir (1) tarafı

    for name, (x, y, h) in pos.items():
        col = color[name]
        ax.add_patch(Rectangle((x, y), W, h, fc="white", ec=col, lw=2.0,
                               ls="--" if name in EXTERNAL else "-", zorder=2))
        ax.add_patch(Rectangle((x, y), W, HEAD, fc=col, ec=col, alpha=0.9, zorder=3))
        ax.text(x + W / 2, y + HEAD / 2, name + ("  (dış)" if name in EXTERNAL else ""), ha="center",
                va="center", fontsize=8.5, fontweight="bold", color="white", zorder=4)
        for i, c in enumerate(tables[name]):
            ry = y + HEAD + ROW * i
            if name == "analysis_results" and c["name"] in NEW:
                ax.add_patch(Rectangle((x, ry), W, ROW, fc="#ede7ff", ec="none", zorder=2.5))
            tag = "PK" if c["pk"] else ("FK" if c["fk"] else "")
            ax.text(x + 0.8, ry + ROW / 2, type_name(c["type"]), fontsize=6.3, va="center",
                    color="#666", zorder=4)
            ax.text(x + 8.5, ry + ROW / 2, c["name"], fontsize=6.8, va="center", color="#111", zorder=4)
            ax.text(x + W - 0.8, ry + ROW / 2, tag, fontsize=6.3, va="center", ha="right",
                    color=col, fontweight="bold", zorder=4)
    ax.text(0, ymax - 1.5,
            f"{len(tables)} tablo · kaynak: SQLAlchemy modelleri (docs/diagrams/kaynak/er_semasi.py) · "
            "mor zemin: duygu analizi sütunları (#333) · kesikli çerçeve: dış kaynak (Miço Usta) tabloları",
            fontsize=7.5, color="#555")
    fig.savefig(OUT, bbox_inches="tight", pad_inches=0.2, facecolor="white")
    print("yazıldı:", OUT, len(tables), "tablo")


if __name__ == "__main__":
    dump() if "--dump" in sys.argv else draw()
