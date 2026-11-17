"""Yetki haritası (OWASP API5 işlev düzeyi yetki): durum değiştiren her uç hangi kimliği ister?

Yeni bir yazma ucu eklenip yönetici/sahip denetimi unutulursa bu test kırılır. Bilinen açık uçlar
`BILINEN_ACIK` içinde adı ve gerekçesiyle durur; rol sistemi (#275) bunları kapatınca liste boşalır.
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

# Yazma uçlarından yalnızca servis anahtarı isteyenler. Rol denetimi (#275) gelene kadar bilinen
# sınırlama: tekne sahibi kimliğiyle gelen çağrı bunlara erişebilir (docs/guvenlik_testi.md).
BILINEN_ACIK = {
    ("POST", "/api/v1/calls"),
    ("POST", "/api/v1/calls/audio"),
    ("POST", "/api/v1/calls/{call_id}/analyze"),
    ("PUT", "/api/v1/calls/{call_id}/match"),
    ("POST", "/api/v1/crm/{call_id}/approve"),
    ("POST", "/api/v1/crm/{call_id}/reject"),
    ("PATCH", "/api/v1/service-orders/{order_id}/status"),
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


def test_unguarded_mutating_routes_match_the_documented_gap_exactly() -> None:
    unguarded = {
        (method, path)
        for method, path, deps in _mutating_routes()
        if not deps & {"require_admin", "require_owner_id"}
    }

    # Yeni açık uç eklenirse fazlalık, #275 bir ucu kapatırsa eksiklik listelenir; ikisi de kırar.
    assert unguarded == BILINEN_ACIK, {
        "belgelenmemis_acik": sorted(unguarded - BILINEN_ACIK),
        "artik_kapali_listeden_cikar": sorted(BILINEN_ACIK - unguarded),
    }
