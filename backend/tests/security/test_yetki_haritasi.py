"""Yetki haritası (OWASP API5 işlev düzeyi yetki): durum değiştiren her uç hangi kimliği ister?

Yeni bir yazma ucu eklenip yönetici/sahip denetimi unutulursa bu test kırılır.
Rol denetimi (#275) sonrası bilinen açık uç yoktur (`BILINEN_ACIK` boş);
eklenecek bir istisna gerekçesiyle burada durmalıdır.
"""

from fastapi.routing import APIRoute

from app.api.routes import (
    analytics,
    assistant,
    audit,
    auth,
    call_intake,
    calls,
    crm,
    customers,
    service_orders,
)

# Rol denetimi (#275) tüm açık uçları kapattı. Tek bilinçli istisna giriş ucudur (#369): henüz
# bir rol yoktur (rolü bu uç belirler), bu yüzden `require_admin`/`require_owner_id` aranmaz;
# yalnızca servis anahtarı gerekir (Next sunucusu çağırır) ve başarısızlıklar IP bütçesiyle,
# hesap kilidiyle ve denetim günlüğüyle sınırlıdır. Yeni bir yazma ucu yönetici/sahip denetimi
# olmadan eklenirse `test_no_mutating_route_is_left_unguarded` kırılır.
BILINEN_ACIK: set[tuple[str, str]] = {
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/register"),
}


def _dependency_names(route: APIRoute) -> set[str]:
    names: set[str] = set()

    def walk(dependant: object) -> None:
        for sub in dependant.dependencies:  # type: ignore[attr-defined]
            names.add(getattr(sub.call, "__name__", str(sub.call)))
            walk(sub)

    walk(route.dependant)
    return names


def _mutating_routes() -> list[tuple[str, str, set[str]]]:
    # Yeni FastAPI iç içe yönlendiricileri tembel tuttuğundan `app.routes` düz liste vermez;
    # uç tanımları modül yönlendiricilerinden okunur (yol, ön ek dahil olarak oradadır).
    modules = (
        analytics,
        assistant,
        audit,
        auth,
        call_intake,
        calls,
        crm,
        customers,
        service_orders,
    )
    out = []
    for module in modules:
        for route in module.router.routes:
            if isinstance(route, APIRoute):
                for method in sorted((route.methods or set()) - {"GET", "HEAD", "OPTIONS"}):
                    out.append((method, "/api/v1" + route.path, _dependency_names(route)))
    return out


def test_every_mutating_route_requires_a_known_identity_dependency() -> None:
    routes = _mutating_routes()
    assert len(routes) >= 8  # boş liste testi anlamsız kılar

    for method, path, deps in routes:
        assert "require_service_key" in deps, (method, path)


def test_no_mutating_route_is_left_unguarded() -> None:
    unguarded = {
        (method, path)
        for method, path, deps in _mutating_routes()
        if not deps & {"require_admin", "require_owner_id"}
    }

    # Yeni açık uç eklenirse fazlalık listelenir ve test kırılır.
    assert unguarded == BILINEN_ACIK, {
        "belgelenmemis_acik": sorted(unguarded - BILINEN_ACIK),
        "artik_kapali_listeden_cikar": sorted(BILINEN_ACIK - unguarded),
    }
