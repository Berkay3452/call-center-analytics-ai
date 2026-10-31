"""Çağrı listesi ve KPI saat dilimi tutarlılığı birim testleri (#156).

İstanbul saati (Europe/Istanbul, UTC+3) sınır durumu testleri:
Gece 00:00-03:00 arası çağrılarda liste filtresi (CallFilters) ve KPI
filtresinin (PeriodFilter) aynı günlere ayırdığını, sınır çağrılarının
(ör. 00:30 çağrısı) doğru tarihe atandığını doğrular.
"""

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from app.schemas.api import CallFilters
from app.services.analytics_service import ISTANBUL_TZ as KPI_ISTANBUL_TZ
from app.services.call_reader import ISTANBUL_TZ as CALLS_ISTANBUL_TZ
from app.services.call_reader import _build_filter_conditions, _latest_analysis_subquery
from app.services.service_orders import ISTANBUL_TZ as SO_ISTANBUL_TZ

ISTANBUL = ZoneInfo("Europe/Istanbul")


def test_timezone_constants_consistent() -> None:
    """Tüm servislerde kullanılan saat dilimi Europe/Istanbul olmalıdır."""
    assert CALLS_ISTANBUL_TZ == ISTANBUL
    assert KPI_ISTANBUL_TZ == ISTANBUL
    assert SO_ISTANBUL_TZ == ISTANBUL


def test_call_filters_and_kpi_date_boundaries_identical() -> None:
    """CallFilters ve KPI aynı gün sınırlarını (Europe/Istanbul) üretir."""
    target_day = date(2026, 10, 15)
    filters = CallFilters(date_from=target_day, date_to=target_day)
    latest_analysis = _latest_analysis_subquery()
    conditions = _build_filter_conditions(filters, latest_analysis)

    # 2 adet tarih koşulu üretilmeli: Call.started_at >= start_dt ve Call.started_at <= end_dt
    date_conditions = [c for c in conditions if hasattr(c, "left") and c.left.name == "started_at"]
    assert len(date_conditions) == 2

    # start_dt ve end_dt değerlerini alalım
    start_dt = date_conditions[0].right.value
    end_dt = date_conditions[1].right.value

    # Başlangıç: 2026-10-15 00:00:00 Europe/Istanbul == 2026-10-14 21:00:00 UTC
    assert start_dt == datetime.combine(target_day, time.min, tzinfo=ISTANBUL)
    assert start_dt.astimezone(UTC) == datetime(2026, 10, 14, 21, 0, 0, tzinfo=UTC)

    # Bitiş: 2026-10-15 23:59:59.999999 Europe/Istanbul == 2026-10-15 20:59:59.999999 UTC
    assert end_dt == datetime.combine(target_day, time.max, tzinfo=ISTANBUL)
    assert end_dt.astimezone(UTC) == datetime(2026, 10, 15, 20, 59, 59, 999999, tzinfo=UTC)


def test_midnight_call_0030_belongs_to_correct_istanbul_day() -> None:
    """Türkiye saatiyle 00:30 çağrısı (UTC 21:30 önceki gün) 15 Ekim gününe aittir (#156).

    Eski UTC hatasında bu çağrı UTC 14 Ekim'e düşüyor ve 15 Ekim sorgusunda
    kayboluyordu; 14 Ekim sorgusunda ise yanlışlıkla sayılıyordu.
    """
    # 2026-10-15 00:30:00 Europe/Istanbul == 2026-10-14 21:30:00 UTC
    call_dt_istanbul = datetime(2026, 10, 15, 0, 30, tzinfo=ISTANBUL)
    call_dt_utc = call_dt_istanbul.astimezone(UTC)
    assert call_dt_utc == datetime(2026, 10, 14, 21, 30, tzinfo=UTC)

    latest_analysis = _latest_analysis_subquery()

    # 1. 15 Ekim filtresi çağrıyı içermelidir
    filters_oct15 = CallFilters(date_from=date(2026, 10, 15), date_to=date(2026, 10, 15))
    conds_oct15 = _build_filter_conditions(filters_oct15, latest_analysis)
    start_oct15 = conds_oct15[0].right.value
    end_oct15 = conds_oct15[1].right.value

    assert call_dt_utc >= start_oct15
    assert call_dt_utc <= end_oct15

    # 2. 14 Ekim filtresi bu çağrıyı İÇERMEMELİDİR (bitiş 20:59:59 UTC, çağrı 21:30 UTC)
    filters_oct14 = CallFilters(date_from=date(2026, 10, 14), date_to=date(2026, 10, 14))
    conds_oct14 = _build_filter_conditions(filters_oct14, latest_analysis)
    end_oct14 = conds_oct14[1].right.value

    assert not (call_dt_utc <= end_oct14)


def test_late_night_call_2330_belongs_to_correct_istanbul_day() -> None:
    """Türkiye saatiyle 23:30 çağrısı (UTC 20:30 aynı gün) 15 Ekim gününe aittir."""
    # 2026-10-15 23:30:00 Europe/Istanbul == 2026-10-15 20:30:00 UTC
    call_dt_istanbul = datetime(2026, 10, 15, 23, 30, tzinfo=ISTANBUL)
    call_dt_utc = call_dt_istanbul.astimezone(UTC)
    assert call_dt_utc == datetime(2026, 10, 15, 20, 30, tzinfo=UTC)

    latest_analysis = _latest_analysis_subquery()

    # 1. 15 Ekim filtresi çağrıyı içermelidir
    filters_oct15 = CallFilters(date_from=date(2026, 10, 15), date_to=date(2026, 10, 15))
    conds_oct15 = _build_filter_conditions(filters_oct15, latest_analysis)
    start_oct15 = conds_oct15[0].right.value
    end_oct15 = conds_oct15[1].right.value

    assert call_dt_utc >= start_oct15
    assert call_dt_utc <= end_oct15

    # 2. 16 Ekim filtresi bu çağrıyı İÇERMEMELİDİR
    filters_oct16 = CallFilters(date_from=date(2026, 10, 16), date_to=date(2026, 10, 16))
    conds_oct16 = _build_filter_conditions(filters_oct16, latest_analysis)
    start_oct16 = conds_oct16[0].right.value

    assert not (call_dt_utc >= start_oct16)


def test_call_between_0000_and_0300_not_leaking_to_previous_day() -> None:
    """02:30 İstanbul saati (UTC 23:30 önceki gün), 16 Ekim'e aittir, 15 Ekim'e sızmaz."""
    # 2026-10-16 02:30:00 Europe/Istanbul == 2026-10-15 23:30:00 UTC
    call_dt_istanbul = datetime(2026, 10, 16, 2, 30, tzinfo=ISTANBUL)
    call_dt_utc = call_dt_istanbul.astimezone(UTC)

    latest_analysis = _latest_analysis_subquery()

    # 15 Ekim sorgusu: UTC bitişi 20:59:59 olduğundan, 23:30 UTC'deki çağrı dışarıda kalır
    filters_oct15 = CallFilters(date_from=date(2026, 10, 15), date_to=date(2026, 10, 15))
    conds_oct15 = _build_filter_conditions(filters_oct15, latest_analysis)
    end_oct15 = conds_oct15[1].right.value
    assert call_dt_utc > end_oct15

    # 16 Ekim sorgusu: çağrıyı içine alır
    filters_oct16 = CallFilters(date_from=date(2026, 10, 16), date_to=date(2026, 10, 16))
    conds_oct16 = _build_filter_conditions(filters_oct16, latest_analysis)
    start_oct16 = conds_oct16[0].right.value
    end_oct16 = conds_oct16[1].right.value
    assert call_dt_utc >= start_oct16
    assert call_dt_utc <= end_oct16


def test_open_ended_date_filters_use_istanbul_timezone() -> None:
    """Tek taraflı filtrelerde (date_from veya date_to) İstanbul saati kullanılır."""
    latest_analysis = _latest_analysis_subquery()

    # Yalnızca date_from
    f_from = CallFilters(date_from=date(2026, 10, 15))
    cond_from = _build_filter_conditions(f_from, latest_analysis)
    assert len(cond_from) == 1
    start_val = cond_from[0].right.value
    assert start_val.tzinfo == ISTANBUL
    assert start_val == datetime(2026, 10, 15, 0, 0, 0, tzinfo=ISTANBUL)

    # Yalnızca date_to
    f_to = CallFilters(date_to=date(2026, 10, 15))
    cond_to = _build_filter_conditions(f_to, latest_analysis)
    assert len(cond_to) == 1
    end_val = cond_to[0].right.value
    assert end_val.tzinfo == ISTANBUL
    assert end_val == datetime(2026, 10, 15, 23, 59, 59, 999999, tzinfo=ISTANBUL)
