"""Miço Usta sentetik veri üreticisi (#23).

LLM/agent içermez; sabit tohumlu (`SEED = 42`) `Faker('tr_TR')`, `random.Random` ve
elle hazırlanmış tekne bakım kataloglarıyla deterministik veri üretir. Her çalıştırmada
birebir aynı JSON dosyalarını `data/synthetic/` altına yazar.
"""

from __future__ import annotations

import json
import random
import unicodedata
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from faker import Faker

from app.domain.enums import RequestCategory, ServiceOrderStatus

SEED = 42
DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "synthetic"

SERVICE_STATUSES: tuple[str, ...] = tuple(s.value for s in ServiceOrderStatus)

# En az 8 gerçekçi İstanbul / Marmara / Ege marinası (burada 10 adet).
MARINAS: list[dict[str, str]] = [
    {"id": "marina_001", "name": "Tuzla Marina", "region": "İstanbul / Marmara"},
    {"id": "marina_002", "name": "Kalamış Marina", "region": "İstanbul / Marmara"},
    {"id": "marina_003", "name": "Ataköy Marina", "region": "İstanbul / Marmara"},
    {"id": "marina_004", "name": "Pendik Marinturk Marina", "region": "İstanbul / Marmara"},
    {"id": "marina_005", "name": "İstinye Tekne Park", "region": "İstanbul / Boğaz"},
    {"id": "marina_006", "name": "Göcek D-Marin", "region": "Muğla / Ege"},
    {"id": "marina_007", "name": "Bodrum Milta Marina", "region": "Muğla / Ege"},
    {"id": "marina_008", "name": "Yalıkavak Marina", "region": "Muğla / Ege"},
    {"id": "marina_009", "name": "Marmaris Netsel Marina", "region": "Muğla / Ege"},
    {"id": "marina_010", "name": "Çeşme Marina", "region": "İzmir / Ege"},
]

# İlk 10 müşteri ve tekne, Berkay'ın `data/synthetic/calls_meta.json` dosyasıyla birebir eşleşir.
# `call_001` hocanın örnek senaryosudur (Tuzla Marina, Rüzgar, motor devir sorunu).
ANCHOR_CUSTOMERS_AND_BOATS: list[dict[str, Any]] = [
    {
        "customer_code": "cust_001",
        "full_name": "Burak Çelik",
        "phone": "+90 533 889 12 67",
        "marina": "Tuzla Marina",
        "boat_code": "boat_001",
        "boat_name": "Rüzgar",
        "boat_type": "yelkenli",
        "boat_model": "Jeanneau Sun Odyssey 440",
        "length_m": 13.39,
        "engine": "Yanmar 4JH45 (45 HP)",
        "year": 2021,
    },
    {
        "customer_code": "cust_002",
        "full_name": "Fatma Kaya",
        "phone": "+90 543 219 44 33",
        "marina": "Göcek D-Marin",
        "boat_code": "boat_002",
        "boat_name": "Albatros",
        "boat_type": "yelkenli",
        "boat_model": "Beneteau Oceanis 45",
        "length_m": 13.85,
        "engine": "Yanmar 4JH57 (57 HP)",
        "year": 2019,
    },
    {
        "customer_code": "cust_003",
        "full_name": "Mehmet Deniz",
        "phone": "+90 555 771 00 12",
        "marina": "Bodrum Milta Marina",
        "boat_code": "boat_003",
        "boat_name": "Poseidon",
        "boat_type": "yelkenli",
        "boat_model": "Bavaria Cruiser 46",
        "length_m": 14.27,
        "engine": "Volvo Penta D2-75 (75 HP)",
        "year": 2018,
    },
    {
        "customer_code": "cust_004",
        "full_name": "Kemal Aydoğan",
        "phone": "+90 532 614 90 11",
        "marina": "Kalamış Marina",
        "boat_code": "boat_004",
        "boat_name": "Lodos",
        "boat_type": "motoryat",
        "boat_model": "Sealine F42",
        "length_m": 12.90,
        "engine": "2x Volvo Penta D6-370 (740 HP)",
        "year": 2017,
    },
    {
        "customer_code": "cust_005",
        "full_name": "Deniz Saygın",
        "phone": "+90 542 660 33 21",
        "marina": "Yalıkavak Marina",
        "boat_code": "boat_005",
        "boat_name": "Martı",
        "boat_type": "katamaran",
        "boat_model": "Lagoon 42 Katamaran",
        "length_m": 12.80,
        "engine": "2x Yanmar 4JH57 (114 HP)",
        "year": 2022,
    },
    {
        "customer_code": "cust_006",
        "full_name": "Selin Arslan",
        "phone": "+90 530 447 22 88",
        "marina": "Göcek D-Marin",
        "boat_code": "boat_006",
        "boat_name": "Ufuk",
        "boat_type": "motoryat",
        "boat_model": "Azimut 55",
        "length_m": 16.90,
        "engine": "2x MAN i6-800 (1600 HP)",
        "year": 2021,
    },
    {
        "customer_code": "cust_007",
        "full_name": "Okan Yurdakul",
        "phone": "+90 535 908 41 72",
        "marina": "Tuzla Marina",
        "boat_code": "boat_007",
        "boat_name": "Karayel",
        "boat_type": "motoryat",
        "boat_model": "Fairline Targa 40",
        "length_m": 12.30,
        "engine": "2x Volvo Penta D6-340 (680 HP)",
        "year": 2020,
    },
    {
        "customer_code": "cust_008",
        "full_name": "Ahmet Yılmaz",
        "phone": "+90 532 412 88 90",
        "marina": "Kalamış Marina",
        "boat_code": "boat_008",
        "boat_name": "Poyraz",
        "boat_type": "motoryat",
        "boat_model": "Motoryat 42",
        "length_m": 12.80,
        "engine": "2x Cummins QSB 6.7 (960 HP)",
        "year": 2019,
    },
    {
        "customer_code": "cust_009",
        "full_name": "Zeynep Karaca",
        "phone": "+90 544 318 65 09",
        "marina": "Göcek D-Marin",
        "boat_code": "boat_009",
        "boat_name": "Yıldız",
        "boat_type": "motoryat",
        "boat_model": "Princess V48",
        "length_m": 15.49,
        "engine": "2x Volvo Penta IPS600 (870 HP)",
        "year": 2020,
    },
    {
        "customer_code": "cust_010",
        "full_name": "Cem Baykal",
        "phone": "+90 536 702 19 84",
        "marina": "Bodrum Milta Marina",
        "boat_code": "boat_010",
        "boat_name": "Akdeniz",
        "boat_type": "motoryat",
        "boat_model": "Ferretti 500",
        "length_m": 15.33,
        "engine": "2x Cummins QSC 8.3 (1100 HP)",
        "year": 2023,
    },
]

# Ek tekneler (toplam 23 tekne: motoryat, yelkenli, gulet, katamaran, trawler).
EXTRA_BOATS_CATALOG: list[dict[str, Any]] = [
    {
        "name": "Meltem",
        "boat_type": "yelkenli",
        "model": "Dufour 430 Grand Large",
        "length_m": 13.24,
        "engine": "Volvo Penta D2-60 (60 HP)",
        "year": 2020,
        "marina": "Ataköy Marina",
    },
    {
        "name": "Bora",
        "boat_type": "motoryat",
        "model": "Absolute 47 Fly",
        "length_m": 14.65,
        "engine": "2x Volvo Penta IPS650 (960 HP)",
        "year": 2022,
        "marina": "Pendik Marinturk Marina",
    },
    {
        "name": "Çapariz",
        "boat_type": "gulet",
        "model": "Bodrum Geleneksel Gulet 22m",
        "length_m": 22.00,
        "engine": "Iveco Cursor 300 HP",
        "year": 2016,
        "marina": "Bodrum Milta Marina",
    },
    {
        "name": "Pruva",
        "boat_type": "yelkenli",
        "model": "Hanse 458",
        "length_m": 14.04,
        "engine": "Yanmar 4JH57 (57 HP)",
        "year": 2021,
        "marina": "Marmaris Netsel Marina",
    },
    {
        "name": "Kalyon",
        "boat_type": "gulet",
        "model": "Ketch Gulet 24m",
        "length_m": 24.00,
        "engine": "2x Perkins Sabre M225Ti (450 HP)",
        "year": 2015,
        "marina": "Marmaris Netsel Marina",
    },
    {
        "name": "İmbat",
        "boat_type": "yelkenli",
        "model": "Beneteau First 36",
        "length_m": 11.00,
        "engine": "Yanmar 3YM30AE (29 HP)",
        "year": 2023,
        "marina": "Çeşme Marina",
    },
    {
        "name": "Yıldırım",
        "boat_type": "motoryat",
        "model": "Sunseeker Predator 50",
        "length_m": 15.46,
        "engine": "2x Volvo Penta D8-IPS800 (1200 HP)",
        "year": 2021,
        "marina": "İstinye Tekne Park",
    },
    {
        "name": "Fora",
        "boat_type": "katamaran",
        "model": "Fountaine Pajot Isla 40",
        "length_m": 11.93,
        "engine": "2x Volvo Penta D1-30 (60 HP)",
        "year": 2022,
        "marina": "Göcek D-Marin",
    },
    {
        "name": "Yakamoz",
        "boat_type": "trawler",
        "model": "Beneteau Swift Trawler 41",
        "length_m": 13.43,
        "engine": "2x Yanmar 8LV320 (640 HP)",
        "year": 2020,
        "marina": "Tuzla Marina",
    },
    {
        "name": "Kutup",
        "boat_type": "motoryat",
        "model": "Sirena 58",
        "length_m": 18.58,
        "engine": "2x CAT C8.7 (1300 HP)",
        "year": 2022,
        "marina": "Kalamış Marina",
    },
    {
        "name": "Pusula",
        "boat_type": "yelkenli",
        "model": "Elan Impression 45",
        "length_m": 13.85,
        "engine": "Volvo Penta D2-60 (60 HP)",
        "year": 2019,
        "marina": "Ataköy Marina",
    },
    {
        "name": "Zıpkın",
        "boat_type": "motoryat",
        "model": "Saxdor 320 GTO",
        "length_m": 10.28,
        "engine": "2x Mercury V8 AMS 300 (600 HP)",
        "year": 2024,
        "marina": "Çeşme Marina",
    },
    {
        "name": "Yelkovan",
        "boat_type": "trawler",
        "model": "Grand Banks 42 Classic",
        "length_m": 13.18,
        "engine": "2x Cummins 6BT5.9M (420 HP)",
        "year": 2016,
        "marina": "Pendik Marinturk Marina",
    },
]

# Ustalar (6 usta; ilk 3'ü `backend/app/assistant/fake_data.py` ile aynı isimlerdir).
CRAFTSMEN_CATALOG: list[dict[str, str]] = [
    {
        "code": "craft_001",
        "full_name": "Mehmet Şimşek",
        "specialty": "Makine, ana motor, jeneratör ve yakıt sistemi",
        "phone": "+90 532 101 10 01",
    },
    {
        "code": "craft_002",
        "full_name": "Hakan Aksoy",
        "specialty": "Elektrik & Elektronik, akü, redresör ve navigasyon",
        "phone": "+90 532 101 10 02",
    },
    {
        "code": "craft_003",
        "full_name": "Selim Kaya",
        "specialty": "Makine, enjektör, turbo ve periyodik motor bakımı",
        "phone": "+90 532 101 10 03",
    },
    {
        "code": "craft_004",
        "full_name": "Murat Demirci",
        "specialty": "Temizlik & Tekne Bakımı, gövde, osmoz ve karina boyası",
        "phone": "+90 532 101 10 04",
    },
    {
        "code": "craft_005",
        "full_name": "Kadir Öztürk",
        "specialty": "Su & Sıhhi Tesisat, sintine, hidrofor ve güvenlik ekipmanı",
        "phone": "+90 532 101 10 05",
    },
    {
        "code": "craft_006",
        "full_name": "Serkan Aydın",
        "specialty": "Mekanik & Hidrolik, dümen, şaft, pervane ve iklimlendirme",
        "phone": "+90 532 101 10 06",
    },
]

# #7'de kesinleşen RequestCategory değerlerine göre servis açıklamaları ve usta notları.
SERVICE_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    RequestCategory.MAKINE.value: [
        {
            "description": "250 saatlik periyodik motor bakımı (yağ, yağ filtresi, yakıt filtresi, impeller)",
            "amount_try": 18500,
            "craftsman_code": "craft_001",
            "note": (
                "Ana makine 250 saatlik periyodik bakımı tamamlandı; motor yağı, yağ ve yakıt "
                "filtreleri ile impeller yenilendi. Altı ay sonra yakıt filtresi kontrolü önerilir."
            ),
        },
        {
            "description": "Ana makine devir düşüklüğü tespiti, Racor yakıt filtresi ve turbo kontrolü",
            "amount_try": 14800,
            "craftsman_code": "craft_003",
            "note": (
                "Yakıt filtresi değişti, 6 ay sonra tekrar kontrol önerilir. Egzoz karışım "
                "dirseğindeki kurum temizlendi, motor 2800 devire sorunsuz çıkıyor."
            ),
        },
        {
            "description": "Sezon sonu motor kışlama, tatlı su devridaim antifriz basımı ve enjektör kontrolü",
            "amount_try": 21000,
            "craftsman_code": "craft_003",
            "note": (
                "Ana makine ve jeneratör deniz suyu devreleri tatlı suyla yıkanıp -25 derece "
                "organik antifriz ile kışlandı. Bahar başında servis açılışı yapılacak."
            ),
        },
    ],
    RequestCategory.MEKANIK_HIDROLIK.value: [
        {
            "description": "Dümen hidrolik piston keçesi değişimi, hava alma ve hidrolik yağ yenileme",
            "amount_try": 13600,
            "craftsman_code": "craft_006",
            "note": (
                "Dümen hidrolik silindirindeki yağ terlemesi keçe takımı değiştirilerek giderildi. "
                "Sistemin havası alındı, sancak-iskele tam alabanda tepkisi normal."
            ),
        },
        {
            "description": "Şanzıman yağ değişimi, şaft kaplin hizalama ve pervane balans kontrolü",
            "amount_try": 15400,
            "craftsman_code": "craft_006",
            "note": (
                "Şanzıman ATF yağı ve süzgeci değiştirildi, şaft kaplini 0.05 mm toleransla "
                "hizalandı. Seyirde titreşim tamamen kesildi."
            ),
        },
    ],
    RequestCategory.ELEKTRIK_ELEKTRONIK.value: [
        {
            "description": "Servis akü grubu değişimi (3x 140Ah AGM) ve şarj regülatörü kalibrasyonu",
            "amount_try": 24500,
            "craftsman_code": "craft_002",
            "note": (
                "Servis aküleri kapasite testinde %40'ın altına düştüğü için 3 adet yeni AGM akü "
                "ile değiştirildi. Şarj regülatörü normal çalışıyor, sezon sonunda yük testi yapılmalı."
            ),
        },
        {
            "description": "Sahil besleme redresörü onarımı, galvanik izolatör ve sigorta panosu kontrolü",
            "amount_try": 9600,
            "craftsman_code": "craft_002",
            "note": (
                "Sahil elektriği giriş prizindeki yanık klemensler yenilendi ve redresör çıkış "
                "sigortası değiştirildi. Kaçak akım rölesi ve galvanik izolatör test edildi."
            ),
        },
    ],
    RequestCategory.SU_SIHHI_TESISAT.value: [
        {
            "description": "Sintine pompası, otomatik şamandıra şalteri ve geri dönüş çekvalf yenileme",
            "amount_try": 7800,
            "craftsman_code": "craft_005",
            "note": (
                "Sintine pompası şamandırası temizlendi ve yedek otomatik pompa devreye alındı. "
                "Su seviye alarmı çalışma testi başarılı."
            ),
        },
        {
            "description": "Tatlı su hidrofor pompası diyafram değişimi ve boiler emniyet ventili bakımı",
            "amount_try": 6900,
            "craftsman_code": "craft_005",
            "note": (
                "Hidrofor basınç şalteri ve diyafram takımı yenilendi, su hattındaki basınç "
                "dalgalanması giderildi. Sıcak su boileri kireçten arındırıldı."
            ),
        },
    ],
    RequestCategory.IKLIMLENDIRME.value: [
        {
            "description": "Marin klima deniz suyu sirkülasyon pompası temizliği ve gaz basıncı kontrolü",
            "amount_try": 11500,
            "craftsman_code": "craft_006",
            "note": (
                "Klima deniz suyu süzgeci ve kondenser boruları kimyasal sıvıyla temizlendi. "
                "Salon ve baş kabin ünitelerinde R410A gaz basıncı tamamlandı, soğutma normal."
            ),
        },
    ],
    RequestCategory.TEKNE_GUVENLIGI.value: [
        {
            "description": "Makine dairesi otomatik yangın söndürme tüpü dolumu ve duman dedektörü testi",
            "amount_try": 9400,
            "craftsman_code": "craft_005",
            "note": (
                "Makine dairesi FM200 otomatik yangın söndürme tüpü basınç kontrolünden geçti, "
                "duman ve ısı sensörleri test edildi. Can salı hidrostatik kilit tarihi doğrulandı."
            ),
        },
    ],
    RequestCategory.TEMIZLIK_BAKIM.value: [
        {
            "description": "Gövde pasta-cila, tik güverte bakımı ve bimini tente dikiş yenileme",
            "amount_try": 19200,
            "craftsman_code": "craft_004",
            "note": (
                "Bordaya 2 aşamalı pasta ve UV koruyucu marin wax uygulandı. Tik güverte "
                "temizlenip koruyucu yağ sürüldü, tente fermuarları yenilendi."
            ),
        },
    ],
    RequestCategory.DIGER.value: [
        {
            "description": "Karina yüksek basınçlı yıkama, osmoz nem ölçümü, 2 kat zehirli boya ve tutya değişimi",
            "amount_try": 32000,
            "craftsman_code": "craft_004",
            "note": (
                "Karina kekamozlardan arındırıldı, epoksi astar kontrolü sonrası iki kat zehirli "
                "boya uygulandı. Şaft ve dümen palası çinko tutyaları tamamen yenilendi."
            ),
        },
    ],
}

# Ek bağımsız usta notları (tekne karnesi zenginliği ve en az 60+ not hedefi için).
STANDALONE_NOTE_TEMPLATES: list[tuple[str, str]] = [
    (
        "craft_001",
        "Şaft salmastrası (PSS) körüğü kontrol edildi, su damlatma yok. Kelepçeler çift "
        "paslanmaz kelepçe olarak yenilendi, 2 yıl sonra körük değişimi önerilir.",
    ),
    (
        "craft_002",
        "Navigasyon lambaları ve direk tepesi demir feneri LED modüllerle yenilendi. "
        "VHF telsiz anten kablosu SWR ölçümü 1.2 çıktı, haberleşme menzili normal.",
    ),
    (
        "craft_003",
        "Ana yakıt tankı havalandırma filtresi temizlendi ve yakıt kesme valfi tel "
        "mekanizması yağlandı. Uzun seyir öncesi yedek Racor filtre teknede bırakıldı.",
    ),
    (
        "craft_004",
        "Tik güverte (teak deck) derz dolgularında güneş kaynaklı açılmalar tespit edildi. "
        "Su sızıntısı olmaması için sonbaharda lokal sika yenilemesi ve zımpara önerilir.",
    ),
    (
        "craft_005",
        "Deniz suyu alış kinistin vanaları (seacock) hareket ettirilip greslendi. "
        "Mutfak gider vanası sertleşmiş, bir sonraki karaya çekmede değiştirilmesi tavsiye edilir.",
    ),
    (
        "craft_006",
        "Baş pervane (bow thruster) tünel pervanesi ve kesme pimi kontrol edildi. "
        "Pervane üzerindeki kalker temizlendi, tutya %80 durumda.",
    ),
]

SUBSCRIPTION_PLANS: list[dict[str, Any]] = [
    {"plan_name": "Miço Başlangıç", "total_services": 2},
    {"plan_name": "Miço Standart", "total_services": 4},
    {"plan_name": "Miço VIP", "total_services": 6},
    {"plan_name": "Gold", "total_services": 3},
]


def _slug_ascii(text: str) -> str:
    """Türkçe metni e-posta ve sabit tanımlayıcı için küçük harf ASCII'ye çevirir."""
    tr_map = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    normalized = unicodedata.normalize("NFKD", text.translate(tr_map))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return ".".join(ascii_text.split())


def deterministic_uuid(kind: str, code: str) -> str:
    """Her varlık türü ve kodu için sabit UUIDv5 üretir."""
    return str(uuid5(NAMESPACE_URL, f"mico-synthetic/{kind}/{code}"))


def _iso_dt(d: date, hour: int = 10, minute: int = 0) -> str:
    return datetime.combine(d, time(hour, minute), tzinfo=UTC).isoformat()


def generate_dataset(seed: int = SEED) -> dict[str, Any]:
    """Tüm sentetik veri kümesini bellekte deterministik olarak üretir."""
    Faker.seed(seed)
    fake = Faker("tr_TR")
    fake.seed_instance(seed)
    rng = random.Random(seed)

    customers: list[dict[str, Any]] = []
    boats: list[dict[str, Any]] = []

    # 1. İlk 10 müşteri ve tekne (Berkay'ın calls_meta.json listesinden)
    for idx, item in enumerate(ANCHOR_CUSTOMERS_AND_BOATS, start=1):
        cust_id = deterministic_uuid("customer", item["customer_code"])
        email = f"{_slug_ascii(item['full_name'])}@example.com"
        created_day = date(2024, 11, 1) + timedelta(days=idx * 5)

        customers.append(
            {
                "id": cust_id,
                "code": item["customer_code"],
                "full_name": item["full_name"],
                "phone": item["phone"],
                "email": email,
                "marina": item["marina"],
                "created_at": _iso_dt(created_day, 9, 30),
            }
        )

        boat_id = deterministic_uuid("boat", item["boat_code"])
        boats.append(
            {
                "id": boat_id,
                "code": item["boat_code"],
                "owner_id": cust_id,
                "owner_code": item["customer_code"],
                "owner_name": item["full_name"],
                "name": item["boat_name"],
                "boat_type": item["boat_type"],
                "model": item["boat_model"],
                "length_m": item["length_m"],
                "engine": item["engine"],
                "year": item["year"],
                "marina": item["marina"],
                "created_at": _iso_dt(created_day, 10, 0),
            }
        )

    # 2. Ek 8 müşteri (toplam 18 müşteri; Faker('tr_TR') ile üretilir)
    used_names = {c["full_name"] for c in customers}
    for idx in range(11, 19):
        cust_code = f"cust_{idx:03d}"
        cust_id = deterministic_uuid("customer", cust_code)
        full_name = f"{fake.first_name()} {fake.last_name()}"
        while full_name in used_names:
            full_name = f"{fake.first_name()} {fake.last_name()}"
        used_names.add(full_name)

        marina_name = MARINAS[(idx - 1) % len(MARINAS)]["name"]
        phone = (
            f"+90 5{rng.choice(['32', '33', '35', '42', '44', '55'])} "
            f"{rng.randint(200, 999)} {rng.randint(10, 99)} {rng.randint(10, 99)}"
        )
        email = f"{_slug_ascii(full_name)}@example.com"
        created_day = date(2025, 1, 10) + timedelta(days=(idx - 10) * 7)

        customers.append(
            {
                "id": cust_id,
                "code": cust_code,
                "full_name": full_name,
                "phone": phone,
                "email": email,
                "marina": marina_name,
                "created_at": _iso_dt(created_day, 11, 0),
            }
        )

    # 3. Ek 13 tekne (toplam 23 tekne: 8'i yeni müşterilere, 5'i ilk 5 müşterinin 2. teknesi)
    owner_indices = [*range(10, 18), 0, 1, 2, 4, 7]
    for offset, boat_spec in enumerate(EXTRA_BOATS_CATALOG, start=11):
        boat_code = f"boat_{offset:03d}"
        boat_id = deterministic_uuid("boat", boat_code)
        owner = customers[owner_indices[offset - 11]]
        created_day = date(2025, 2, 1) + timedelta(days=(offset - 10) * 4)

        boats.append(
            {
                "id": boat_id,
                "code": boat_code,
                "owner_id": owner["id"],
                "owner_code": owner["code"],
                "owner_name": owner["full_name"],
                "name": boat_spec["name"],
                "boat_type": boat_spec["boat_type"],
                "model": boat_spec["model"],
                "length_m": boat_spec["length_m"],
                "engine": boat_spec["engine"],
                "year": boat_spec["year"],
                "marina": boat_spec["marina"],
                "created_at": _iso_dt(created_day, 14, 0),
            }
        )

    # 4. Ustalar (6 usta)
    craftsmen: list[dict[str, Any]] = []
    craftsman_by_code: dict[str, dict[str, Any]] = {}
    for idx, c_spec in enumerate(CRAFTSMEN_CATALOG, start=1):
        c_row = {
            "id": deterministic_uuid("craftsman", c_spec["code"]),
            "code": c_spec["code"],
            "full_name": c_spec["full_name"],
            "specialty": c_spec["specialty"],
            "phone": c_spec["phone"],
            "created_at": _iso_dt(date(2024, 10, 1) + timedelta(days=idx), 8, 30),
        }
        craftsmen.append(c_row)
        craftsman_by_code[c_spec["code"]] = c_row

    # 5. Servis kayıtları, usta notları ve giderler
    service_orders: list[dict[str, Any]] = []
    boat_notes: list[dict[str, Any]] = []
    expenses: list[dict[str, Any]] = []

    categories = [c.value for c in RequestCategory]

    # Önce `fake_data.py` içindeki bilinen kayıtları Poyraz (boat_008) ve Albatros (boat_002)
    # için birebir ekleyelim ki asistan testleri ve gerçek DB sorguları tutarlı olsun.
    poyraz = next(b for b in boats if b["code"] == "boat_008")
    albatros = next(b for b in boats if b["code"] == "boat_002")

    pinned_services: list[dict[str, Any]] = [
        {
            "srv_code": "srv_001",
            "boat": poyraz,
            "on": date(2026, 8, 15),
            "category": RequestCategory.MAKINE.value,
            "description": "250 saatlik periyodik bakım",
            "craftsman_code": "craft_001",
            "status": ServiceOrderStatus.TAMAMLANDI.value,
            "amount_try": "18500.00",
            "note": (
                "Ana makine 250 saatlik bakımı tamamlandı, impeller yenilendi. "
                "Altı ay sonra yakıt filtresi kontrolü önerilir."
            ),
        },
        {
            "srv_code": "srv_002",
            "boat": poyraz,
            "on": date(2026, 3, 10),
            "category": RequestCategory.ELEKTRIK_ELEKTRONIK.value,
            "description": "Akü grubu değişimi",
            "craftsman_code": "craft_002",
            "status": ServiceOrderStatus.TAMAMLANDI.value,
            "amount_try": "9200.00",
            "note": (
                "Servis aküleri değiştirildi. Şarj regülatörü normal çalışıyor, "
                "bir sonraki akü kontrolü sezon sonunda yapılmalı."
            ),
        },
        {
            "srv_code": "srv_003",
            "boat": albatros,
            "on": date(2026, 6, 2),
            "category": RequestCategory.MAKINE.value,
            "description": "Yakıt filtresi ve enjektör temizliği",
            "craftsman_code": "craft_003",
            "status": ServiceOrderStatus.TAMAMLANDI.value,
            "amount_try": "6400.00",
            "note": (
                "Yakıt filtresi tıkanmıştı, değiştirildi. Enjektörler temizlendi, "
                "devir sorunu giderildi."
            ),
        },
    ]

    srv_counter = 0
    note_counter = 0
    exp_counter = 0

    for item in pinned_services:
        srv_counter += 1
        note_counter += 1
        exp_counter += 1
        srv_id = deterministic_uuid("service_order", item["srv_code"])
        craft = craftsman_by_code[item["craftsman_code"]]
        b = item["boat"]
        d: date = item["on"]

        service_orders.append(
            {
                "id": srv_id,
                "code": item["srv_code"],
                "boat_id": b["id"],
                "boat_name": b["name"],
                "customer_id": b["owner_id"],
                "craftsman_id": craft["id"],
                "craftsman_name": craft["full_name"],
                "category": item["category"],
                "description": item["description"],
                "status": item["status"],
                "scheduled_at": _iso_dt(d, 9, 0),
                "completed_at": _iso_dt(d, 15, 30),
                "amount_try": item["amount_try"],
                "note": item["note"],
                "created_at": _iso_dt(d - timedelta(days=2), 10, 0),
            }
        )
        boat_notes.append(
            {
                "id": deterministic_uuid("boat_note", f"note_{note_counter:03d}"),
                "code": f"note_{note_counter:03d}",
                "boat_id": b["id"],
                "boat_name": b["name"],
                "owner_id": b["owner_id"],
                "author_id": craft["id"],
                "author_name": craft["full_name"],
                "content": item["note"],
                "note_date": d.isoformat(),
                "created_at": _iso_dt(d, 16, 0),
            }
        )
        expenses.append(
            {
                "id": deterministic_uuid("expense", f"exp_{exp_counter:03d}"),
                "code": f"exp_{exp_counter:03d}",
                "boat_id": b["id"],
                "boat_name": b["name"],
                "owner_id": b["owner_id"],
                "service_order_id": srv_id,
                "amount": item["amount_try"],
                "currency": "TRY",
                "description": item["description"],
                "expense_date": d.isoformat(),
                "created_at": _iso_dt(d, 17, 0),
            }
        )

    # Poyraz için ek not ve marina gideri (`fake_data.py` uyumu)
    note_counter += 1
    boat_notes.append(
        {
            "id": deterministic_uuid("boat_note", f"note_{note_counter:03d}"),
            "code": f"note_{note_counter:03d}",
            "boat_id": poyraz["id"],
            "boat_name": poyraz["name"],
            "owner_id": poyraz["owner_id"],
            "author_id": craftsman_by_code["craft_005"]["id"],
            "author_name": craftsman_by_code["craft_005"]["full_name"],
            "content": "Sintine pompası şamandırası temizlendi, çalışma testi başarılı.",
            "note_date": date(2026, 8, 15).isoformat(),
            "created_at": _iso_dt(date(2026, 8, 15), 16, 30),
        }
    )
    exp_counter += 1
    expenses.append(
        {
            "id": deterministic_uuid("expense", f"exp_{exp_counter:03d}"),
            "code": f"exp_{exp_counter:03d}",
            "boat_id": poyraz["id"],
            "boat_name": poyraz["name"],
            "owner_id": poyraz["owner_id"],
            "service_order_id": None,
            "amount": "14250.00",
            "currency": "TRY",
            "description": "Marina bağlama ve elektrik/su",
            "expense_date": date(2026, 10, 1).isoformat(),
            "created_at": _iso_dt(date(2026, 10, 1), 12, 0),
        }
    )

    # Tüm tekneler için geçmiş 1–2 yıla yayılan servis emirleri, usta notları ve giderler
    base_date = date(2025, 1, 15)
    for b_idx, boat in enumerate(boats):
        num_services = 3 if b_idx % 2 == 0 else 2
        for s_idx in range(num_services):
            srv_counter += 1
            srv_code = f"srv_{srv_counter:03d}"
            srv_id = deterministic_uuid("service_order", srv_code)

            cat = categories[(b_idx + s_idx) % len(categories)]
            templates = SERVICE_TEMPLATES[cat]
            tpl = templates[(b_idx + s_idx) % len(templates)]
            craft = craftsman_by_code[tpl["craftsman_code"]]

            day_offset = (b_idx * 23 + s_idx * 140) % 610
            srv_date = base_date + timedelta(days=day_offset)

            if srv_date > date(2026, 9, 20) and s_idx == num_services - 1:
                status = SERVICE_STATUSES[(b_idx + s_idx) % 4]
                completed_at = None
            else:
                status = ServiceOrderStatus.TAMAMLANDI.value
                completed_at = _iso_dt(srv_date, 16, 0)

            price_variation = rng.choice([-600, -300, 0, 400, 750])
            amount_val = max(3500, tpl["amount_try"] + price_variation)
            amount_str = f"{amount_val:.2f}"

            service_orders.append(
                {
                    "id": srv_id,
                    "code": srv_code,
                    "boat_id": boat["id"],
                    "boat_name": boat["name"],
                    "customer_id": boat["owner_id"],
                    "craftsman_id": craft["id"],
                    "craftsman_name": craft["full_name"],
                    "category": cat,
                    "description": tpl["description"],
                    "status": status,
                    "scheduled_at": _iso_dt(srv_date, 9, 30),
                    "completed_at": completed_at,
                    "amount_try": amount_str,
                    "note": tpl["note"],
                    "created_at": _iso_dt(srv_date - timedelta(days=3), 11, 0),
                }
            )

            note_counter += 1
            boat_notes.append(
                {
                    "id": deterministic_uuid("boat_note", f"note_{note_counter:03d}"),
                    "code": f"note_{note_counter:03d}",
                    "boat_id": boat["id"],
                    "boat_name": boat["name"],
                    "owner_id": boat["owner_id"],
                    "author_id": craft["id"],
                    "author_name": craft["full_name"],
                    "content": f"{boat['name']} ({boat['marina']}): {tpl['note']}",
                    "note_date": srv_date.isoformat(),
                    "created_at": _iso_dt(srv_date, 16, 30),
                }
            )

            if status == ServiceOrderStatus.TAMAMLANDI.value:
                exp_counter += 1
                expenses.append(
                    {
                        "id": deterministic_uuid("expense", f"exp_{exp_counter:03d}"),
                        "code": f"exp_{exp_counter:03d}",
                        "boat_id": boat["id"],
                        "boat_name": boat["name"],
                        "owner_id": boat["owner_id"],
                        "service_order_id": srv_id,
                        "amount": amount_str,
                        "currency": "TRY",
                        "description": tpl["description"],
                        "expense_date": srv_date.isoformat(),
                        "created_at": _iso_dt(srv_date, 17, 15),
                    }
                )

        # Her tekneye ek 1 bağımsız usta kontrol notu (en az 60+ not hedefini garanti eder)
        note_counter += 1
        extra_craft_code, extra_note_text = STANDALONE_NOTE_TEMPLATES[
            b_idx % len(STANDALONE_NOTE_TEMPLATES)
        ]
        extra_craft = craftsman_by_code[extra_craft_code]
        extra_date = date(2026, 4, 1) + timedelta(days=(b_idx * 7) % 160)
        boat_notes.append(
            {
                "id": deterministic_uuid("boat_note", f"note_{note_counter:03d}"),
                "code": f"note_{note_counter:03d}",
                "boat_id": boat["id"],
                "boat_name": boat["name"],
                "owner_id": boat["owner_id"],
                "author_id": extra_craft["id"],
                "author_name": extra_craft["full_name"],
                "content": f"{boat['name']} genel sörvey notu: {extra_note_text}",
                "note_date": extra_date.isoformat(),
                "created_at": _iso_dt(extra_date, 15, 0),
            }
        )

    # 6. Abonelik / Bakım paketleri (15 tekne/müşteri için)
    subscriptions: list[dict[str, Any]] = []
    subscriptions.append(
        {
            "id": deterministic_uuid("subscription", "sub_001"),
            "code": "sub_001",
            "customer_id": poyraz["owner_id"],
            "customer_name": poyraz["owner_name"],
            "boat_id": poyraz["id"],
            "boat_name": poyraz["name"],
            "plan_name": "Gold",
            "total_services": 2,
            "used_services": 1,
            "starts_at": "2026-04-01",
            "expires_at": "2027-03-31",
            "created_at": _iso_dt(date(2026, 4, 1), 10, 0),
        }
    )

    sub_counter = 1
    for b_idx, boat in enumerate(boats):
        if boat["code"] in {"boat_008", "boat_002"}:
            continue
        if sub_counter >= 15:
            break
        sub_counter += 1
        plan = SUBSCRIPTION_PLANS[b_idx % len(SUBSCRIPTION_PLANS)]
        total_srv = plan["total_services"]
        used_srv = b_idx % total_srv
        start_d = date(2026, 1, 1) + timedelta(days=(b_idx * 15) % 180)
        end_d = start_d + timedelta(days=365)

        subscriptions.append(
            {
                "id": deterministic_uuid("subscription", f"sub_{sub_counter:03d}"),
                "code": f"sub_{sub_counter:03d}",
                "customer_id": boat["owner_id"],
                "customer_name": boat["owner_name"],
                "boat_id": boat["id"],
                "boat_name": boat["name"],
                "plan_name": plan["plan_name"],
                "total_services": total_srv,
                "used_services": used_srv,
                "starts_at": start_d.isoformat(),
                "expires_at": end_d.isoformat(),
                "created_at": _iso_dt(start_d, 9, 0),
            }
        )

    # 7. Berkay'ın #12 çağrı diyalogları için birleşik müşteri + tekne referans listesi
    boats_by_owner: dict[str, list[dict[str, Any]]] = {}
    for b in boats:
        boats_by_owner.setdefault(b["owner_id"], []).append(
            {
                "boat_id": b["id"],
                "boat_code": b["code"],
                "name": b["name"],
                "boat_type": b["boat_type"],
                "model": b["model"],
                "length_m": b["length_m"],
                "engine": b["engine"],
                "year": b["year"],
                "marina": b["marina"],
            }
        )

    customers_boats = [
        {
            "customer_id": c["id"],
            "customer_code": c["code"],
            "full_name": c["full_name"],
            "phone": c["phone"],
            "email": c["email"],
            "marina": c["marina"],
            "boats": boats_by_owner.get(c["id"], []),
        }
        for c in customers
    ]

    return {
        "marinas": MARINAS,
        "customers": customers,
        "boats": boats,
        "customers_boats": customers_boats,
        "craftsmen": craftsmen,
        "service_orders": service_orders,
        "boat_notes": boat_notes,
        "expenses": expenses,
        "subscriptions": subscriptions,
    }


def write_synthetic_files(out_dir: Path = DATA_DIR, seed: int = SEED) -> dict[str, Path]:
    """Sentetik veri kümelerini `data/synthetic/` altına JSON dosyaları olarak yazar."""
    out_dir.mkdir(parents=True, exist_ok=True)
    dataset = generate_dataset(seed=seed)

    written: dict[str, Path] = {}
    for name, records in dataset.items():
        target = out_dir / f"{name}.json"
        target.write_text(
            json.dumps(records, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        written[name] = target
    return written


def load_calls_bundle(data_dir: Path = DATA_DIR) -> list[dict[str, Any]]:
    """Berkay'ın `data/synthetic/calls/`, `truth/` ve `calls_meta.json` verisini okur."""
    meta_path = data_dir / "calls_meta.json"
    if not meta_path.exists():
        return []

    meta_list: list[dict[str, Any]] = json.loads(meta_path.read_text(encoding="utf-8"))
    bundle: list[dict[str, Any]] = []

    for meta in meta_list:
        cid = meta["call_id"]
        call_path = data_dir / "calls" / f"{cid}.json"
        truth_path = data_dir / "truth" / f"{cid}.truth.json"
        if not call_path.exists():
            continue

        dialogue = json.loads(call_path.read_text(encoding="utf-8"))
        truth = json.loads(truth_path.read_text(encoding="utf-8")) if truth_path.exists() else None
        bundle.append(
            {
                "call_id": cid,
                "uuid": UUID(str(uuid5(NAMESPACE_URL, f"synthetic/{cid}"))),
                "meta": meta,
                "turns": dialogue.get("turns", []),
                "truth": truth,
            }
        )
    return bundle
