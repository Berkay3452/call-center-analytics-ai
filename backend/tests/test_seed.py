"""Sentetik veri üretimi ve tohumlama (seed) testleri (#23)."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from app.domain.enums import RequestCategory
from scripts.seed.generator import (
    DATA_DIR,
    SERVICE_STATUSES,
    generate_dataset,
    load_calls_bundle,
    write_synthetic_files,
)


def test_generator_is_deterministic() -> None:
    """Aynı tohumla iki kez çalıştırıldığında birebir aynı veriyi üretmeli."""
    first = generate_dataset(seed=42)
    second = generate_dataset(seed=42)
    assert first == second


def test_counts_and_ranges_match_issue_23() -> None:
    """Issue #23'teki adet ve kapsam kurallarını doğrular."""
    ds = generate_dataset()

    assert len(ds["marinas"]) >= 8
    assert 15 <= len(ds["customers"]) <= 20
    assert 20 <= len(ds["boats"]) <= 25
    assert 5 <= len(ds["craftsmen"]) <= 6
    assert len(ds["boat_notes"]) >= 60
    assert len(ds["service_orders"]) >= 50
    assert len(ds["expenses"]) >= 50
    assert len(ds["subscriptions"]) >= 10


def test_customers_and_boats_match_calls_meta() -> None:
    """Berkay'ın `calls_meta.json` dosyasındaki tüm müşteri/tekne çiftleri listede bulunmalı."""
    ds = generate_dataset()
    meta = json.loads((DATA_DIR / "calls_meta.json").read_text(encoding="utf-8"))

    customer_names = {c["full_name"] for c in ds["customers"]}
    boat_pairs = {(b["owner_name"], b["name"], b["marina"]) for b in ds["boats"]}

    new_callers = set()
    for item in meta:
        ref = item["customer_ref"]
        if ref["customer"] not in customer_names:
            new_callers.add(ref["customer"])  # ilk kez arayan: CRM'de henüz kayıtlı değil
            continue
        assert (ref["customer"], ref["boat"], ref["marina"]) in boat_pairs

    # Kayıtlı olmayan arayanlar bilinçli: eşleşmeyen çağrı için CRM önerisi senaryosu.
    assert new_callers == {
        "Volkan Tekin",
        "Ece Aksoy",
        "Tuncay Erdem",
        "Hakan Özdemir",  # call_035
        "Engin Taşkıran",  # call_046
        "Serkan Bulut",  # call_050
    }

    # Hocanın örnek çağrısı için Tuzla Marina'da tekne bulunmalı
    tuzla_boats = [b for b in ds["boats"] if b["marina"] == "Tuzla Marina"]
    assert any(b["name"] == "Rüzgar" for b in tuzla_boats)


def test_referential_integrity_and_enums() -> None:
    """Üretilen kayıtların yabancı anahtarları ve enum değerleri (#7) geçerli olmalı."""
    ds = generate_dataset()

    customer_ids = {c["id"] for c in ds["customers"]}
    boat_ids = {b["id"] for b in ds["boats"]}
    craftsman_ids = {cr["id"] for cr in ds["craftsmen"]}
    valid_categories = {c.value for c in RequestCategory}

    for c in ds["customers"]:
        assert c["email"].endswith("@example.com")
        assert c["phone"].startswith("+90 5")

    boat_types = {b["boat_type"] for b in ds["boats"]}
    assert {"motoryat", "yelkenli", "gulet", "katamaran"}.issubset(boat_types)
    for b in ds["boats"]:
        assert b["owner_id"] in customer_ids
        assert b["length_m"] > 0
        assert b["engine"]

    service_ids = set()
    for srv in ds["service_orders"]:
        service_ids.add(srv["id"])
        assert srv["boat_id"] in boat_ids
        assert srv["customer_id"] in customer_ids
        assert srv["craftsman_id"] in craftsman_ids
        assert srv["category"] in valid_categories
        assert srv["status"] in SERVICE_STATUSES

    for note in ds["boat_notes"]:
        assert note["boat_id"] in boat_ids
        assert note["owner_id"] in customer_ids
        assert note["author_id"] in craftsman_ids
        assert len(note["content"].strip()) > 20

    for exp in ds["expenses"]:
        assert exp["boat_id"] in boat_ids
        assert Decimal(exp["amount"]) >= 0
        if exp["service_order_id"] is not None:
            assert exp["service_order_id"] in service_ids

    for sub in ds["subscriptions"]:
        assert sub["customer_id"] in customer_ids
        assert sub["boat_id"] in boat_ids
        assert 0 <= sub["used_services"] <= sub["total_services"]


def test_write_synthetic_files_and_calls_bundle(tmp_path: Path) -> None:
    """JSON dosyalarının diske yazılışını ve çağrı paketinin okunuşunu denetler."""
    written = write_synthetic_files(out_dir=tmp_path)
    assert set(written) == {
        "marinas",
        "customers",
        "boats",
        "customers_boats",
        "craftsmen",
        "service_orders",
        "boat_notes",
        "expenses",
        "subscriptions",
    }
    for path in written.values():
        assert path.exists()
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(loaded, list) and len(loaded) > 0

    bundle = load_calls_bundle(data_dir=DATA_DIR)
    assert len(bundle) == 50
    assert bundle[0]["call_id"] == "call_001"


def test_readme_counts_match_generated_and_saved_files() -> None:
    """`data/synthetic/README.md` kayıt sayıları ile generator ve JSON'lar aynı olmalı (#82)."""
    import re

    readme_text = (DATA_DIR / "README.md").read_text(encoding="utf-8")
    ds = generate_dataset()
    bundle = load_calls_bundle(data_dir=DATA_DIR)

    expected_file_counts = {
        "marinas.json": len(ds["marinas"]),
        "customers.json": len(ds["customers"]),
        "boats.json": len(ds["boats"]),
        "craftsmen.json": len(ds["craftsmen"]),
        "service_orders.json": len(ds["service_orders"]),
        "boat_notes.json": len(ds["boat_notes"]),
        "expenses.json": len(ds["expenses"]),
        "subscriptions.json": len(ds["subscriptions"]),
    }

    for filename, expected_count in expected_file_counts.items():
        # Diskteki JSON dosyasındaki gerçek kayıt sayısı
        disk_file = DATA_DIR / filename
        assert disk_file.exists(), f"{filename} bulunamadı"
        disk_data = json.loads(disk_file.read_text(encoding="utf-8"))
        assert len(disk_data) == expected_count, (
            f"{filename} diskteki kayıt sayısı ({len(disk_data)}) "
            f"generator çıktısıyla ({expected_count}) eşleşmiyor"
        )

        # README.md tablosundaki parantez içindeki sayı: ör. `expenses.json` | ... (56 kayıt ...)
        pattern = rf"`{re.escape(filename)}`\s*\|\s*[^|\n]*?\((\d+)"
        match = re.search(pattern, readme_text)
        assert match is not None, f"README.md içinde `{filename}` satırında kayıt sayısı bulunamadı"
        readme_count = int(match.group(1))
        assert readme_count == expected_count, (
            f"README.md içindeki {filename} sayısı ({readme_count}) "
            f"generator ile ({expected_count}) eşleşmiyor"
        )

    # Çağrılar: "50 sahte telefon görüşmesi"
    calls_match = re.search(r"(\d+)\s+sahte telefon görüşmesi", readme_text)
    assert calls_match is not None
    assert int(calls_match.group(1)) == len(bundle) == 50
