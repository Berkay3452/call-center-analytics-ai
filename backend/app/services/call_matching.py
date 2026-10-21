"""Çağrı müşteri ve tekne eşleştirme servisi (#119).

Kurallar:
- Telefon (normalize, kesin eşleşme) -> Müşteri adı + tekne adı (normalize/yaklaşık).
- Birden fazla aday varsa belirsiz sayılır, yanlış bağlamak yerine boş bırakılır (`yok`).
- Çağrı bilgisinden (`customer_phone`, `customer_name`, `boat_name`, `marina`) ve
  yoksa CRM çıkarımındaki alanlardan yararlanılır.
- Analiz tamamlanınca otomatik çalışır; sonuç `calls.customer_id`, `calls.boat_id`
  ve `calls.match_method` olarak saklanır.
- Eşleşmeyen veya yanlış bağlanan çağrılar için elle eşleştirme: `manual_match_call` (`elle`).
"""

import re
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, NotFoundError
from app.db.models.ai import AnalysisResult as AnalysisRow
from app.db.models.ai import Call
from app.db.models.external import Boat, Customer
from app.domain.enums import MatchMethod
from app.schemas.api import CallDetail
from app.services.call_reader import get_call_detail

log = structlog.get_logger(__name__)


class InvalidBoatError(AppError):
    """Seçilen tekne müşteriye ait değilse fırlatılır."""

    code = "invalid_boat"


def normalize_phone(raw: str | None) -> str | None:
    """Telefon numarasından tüm boşluk ve karakterleri temizler; son 10 hanesini (TR no) döner."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) >= 10:
        return digits[-10:]
    if len(digits) >= 7:
        return digits
    return None


def normalize_text(text: str | None) -> str:
    """Türkçe karakterleri ve noktalama işaretlerini normalize ederek küçük harfe çevirir."""
    if not text:
        return ""
    # Türkçe I/İ dönüşümü
    s = text.replace("I", "ı").replace("İ", "i").lower()
    tr_map = str.maketrans(
        {
            "ı": "i",
            "ğ": "g",
            "ü": "u",
            "ş": "s",
            "ö": "o",
            "ç": "c",
        }
    )
    s = s.translate(tr_map)
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.split())


async def match_call(
    session: AsyncSession,
    call_id: UUID,
    *,
    force: bool = False,
) -> tuple[UUID | None, UUID | None, MatchMethod]:
    """Bir çağrıyı telefon veya müşteri adı + tekne adı ile eşleştirir.

    - Elle eşleştirilmiş (`match_method = elle`) çağrılar `force=True` olmadıkça korunur.
    - Zaten müşteri ve teknesi olan seed çağrıları bozulmaz.
    """
    call = await session.get(Call, call_id)
    if call is None:
        raise NotFoundError("Çağrı bulunamadı.")

    if not force:
        if call.match_method == MatchMethod.ELLE.value:
            return call.customer_id, call.boat_id, MatchMethod.ELLE
        if call.customer_id is not None and call.boat_id is not None:
            if not call.match_method:
                call.match_method = MatchMethod.TELEFON.value
                await session.flush()
            return call.customer_id, call.boat_id, MatchMethod(call.match_method)

    # En son analizi al (CRM çıkarımı ve konum bilgisi için)
    stmt = (
        select(AnalysisRow)
        .where(AnalysisRow.call_id == call_id)
        .order_by(AnalysisRow.version.desc())
        .limit(1)
    )
    latest_analysis = (await session.execute(stmt)).scalar_one_or_none()

    phone = call.customer_phone
    customer_name = call.customer_name
    boat_name = call.boat_name
    marina = call.marina or (latest_analysis.location if latest_analysis else None)

    # 1. YÖNTEM: Telefon ile eşleştirme (kesin eşleşme)
    if phone:
        norm_phone = normalize_phone(phone)
        if norm_phone:
            customers = (await session.execute(select(Customer))).scalars().all()
            matching_customers = [c for c in customers if normalize_phone(c.phone) == norm_phone]
            if len(matching_customers) == 1:
                c = matching_customers[0]
                boats = (
                    (await session.execute(select(Boat).where(Boat.owner_id == c.id)))
                    .scalars()
                    .all()
                )

                matched_boat: Boat | None = None
                if len(boats) == 1:
                    matched_boat = boats[0]
                elif len(boats) > 1:
                    target_boat_norm = normalize_text(boat_name)
                    if target_boat_norm:
                        b_matches = [
                            b
                            for b in boats
                            if target_boat_norm in normalize_text(b.name)
                            or normalize_text(b.name) in target_boat_norm
                        ]
                        if len(b_matches) == 1:
                            matched_boat = b_matches[0]

                    if not matched_boat and marina:
                        target_marina_norm = normalize_text(marina)
                        m_matches = [
                            b
                            for b in boats
                            if b.marina
                            and (
                                target_marina_norm in normalize_text(b.marina)
                                or normalize_text(b.marina) in target_marina_norm
                            )
                        ]
                        if len(m_matches) == 1:
                            matched_boat = m_matches[0]

                    if not matched_boat and latest_analysis:
                        combined_text = " ".join(
                            [
                                latest_analysis.problem or "",
                                latest_analysis.potential_job or "",
                                " ".join(
                                    str(v) for v in (latest_analysis.crm_evidence or {}).values()
                                ),
                            ]
                        )
                        combined_norm = normalize_text(combined_text)
                        b_matches = [b for b in boats if normalize_text(b.name) in combined_norm]
                        if len(b_matches) == 1:
                            matched_boat = b_matches[0]

                call.customer_id = c.id
                call.boat_id = matched_boat.id if matched_boat else None
                call.match_method = MatchMethod.TELEFON.value
                if not call.customer_name:
                    call.customer_name = c.full_name
                if matched_boat and not call.boat_name:
                    call.boat_name = matched_boat.name
                if matched_boat and not call.boat_model and matched_boat.model:
                    call.boat_model = matched_boat.model
                if matched_boat and not call.marina and matched_boat.marina:
                    call.marina = matched_boat.marina

                await session.flush()
                log.info(
                    "call.matched_by_phone",
                    call_id=str(call_id),
                    customer_id=str(c.id),
                    boat_id=str(matched_boat.id) if matched_boat else None,
                )
                return c.id, matched_boat.id if matched_boat else None, MatchMethod.TELEFON

    # 2. YÖNTEM: Müşteri Adı + Tekne Adı ile eşleştirme
    if customer_name and boat_name:
        norm_c = normalize_text(customer_name)
        norm_b = normalize_text(boat_name)
        norm_m = normalize_text(marina)

        stmt_pairs = select(Customer, Boat).join(Boat, Boat.owner_id == Customer.id)
        pairs = (await session.execute(stmt_pairs)).all()

        candidates: list[tuple[Customer, Boat]] = []
        for c, b in pairs:
            c_norm = normalize_text(c.full_name)
            b_norm = normalize_text(b.name)

            cust_matches = (norm_c == c_norm) or (
                len(norm_c) >= 3 and (norm_c in c_norm or c_norm in norm_c)
            )
            boat_matches = (norm_b == b_norm) or (
                len(norm_b) >= 3 and (norm_b in b_norm or b_norm in norm_b)
            )

            if cust_matches and boat_matches:
                if norm_m and b.marina:
                    bm_norm = normalize_text(b.marina)
                    if norm_m not in bm_norm and bm_norm not in norm_m:
                        continue
                candidates.append((c, b))

        if len(candidates) == 1:
            c, b = candidates[0]
            call.customer_id = c.id
            call.boat_id = b.id
            call.match_method = MatchMethod.AD_TEKNE.value
            if not call.customer_phone and c.phone:
                call.customer_phone = c.phone
            if not call.boat_model and b.model:
                call.boat_model = b.model
            if not call.marina and b.marina:
                call.marina = b.marina

            await session.flush()
            log.info(
                "call.matched_by_name_and_boat",
                call_id=str(call_id),
                customer_id=str(c.id),
                boat_id=str(b.id),
            )
            return c.id, b.id, MatchMethod.AD_TEKNE

    # 3. YÖNTEM: Eşleşme bulunamadı veya birden fazla aday belirsiz
    call.customer_id = None
    call.boat_id = None
    call.match_method = MatchMethod.YOK.value
    await session.flush()
    log.info("call.unmatched", call_id=str(call_id))
    return None, None, MatchMethod.YOK


async def manual_match_call(
    session: AsyncSession,
    call_id: UUID,
    customer_id: UUID,
    boat_id: UUID | None = None,
) -> CallDetail:
    """Çağrıyı belirli bir müşteri ve tekneye elle eşleştirir (`PUT /calls/{id}/match`)."""
    call = await session.get(Call, call_id)
    if call is None:
        raise NotFoundError("Çağrı bulunamadı.")

    customer = await session.get(Customer, customer_id)
    if customer is None:
        raise NotFoundError("Müşteri bulunamadı.")

    boat: Boat | None = None
    if boat_id is not None:
        boat = await session.get(Boat, boat_id)
        if boat is None:
            raise NotFoundError("Tekne bulunamadı.")
        if boat.owner_id != customer.id:
            raise InvalidBoatError(
                "Seçilen tekne bu müşteriye ait değil.",
                details={"customer_id": str(customer_id), "boat_id": str(boat_id)},
            )

    call.customer_id = customer.id
    call.boat_id = boat.id if boat else None
    call.match_method = MatchMethod.ELLE.value

    if not call.customer_name:
        call.customer_name = customer.full_name
    if not call.customer_phone and customer.phone:
        call.customer_phone = customer.phone
    if boat:
        if not call.boat_name:
            call.boat_name = boat.name
        if not call.boat_model and boat.model:
            call.boat_model = boat.model
        if not call.marina and boat.marina:
            call.marina = boat.marina

    await session.flush()
    log.info(
        "call.manually_matched",
        call_id=str(call_id),
        customer_id=str(customer.id),
        boat_id=str(boat.id) if boat else None,
    )
    return await get_call_detail(session, call_id)
