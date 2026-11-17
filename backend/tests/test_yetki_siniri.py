"""Yapay zekâ yetki sınırları (#275): araç izin listesi, `owner_id` sunucu bağlamı, yazma yok,
insan onayı durum makinesi.

Sunucu tarafı ROL denetimi (yönetici uçları için 403) kimlik doğrulama aşamasına bırakıldı
(#278, #266); burada yalnızca yapay zekânın ve yazma yolunun sınırları kanıtlanır.
Veritabanı ve gerçek LLM gerekmez.
"""

import ast
import inspect
import json
from itertools import pairwise
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.agents.base import BaseAgent
from app.agents.registry import default_stages
from app.assistant import assistant as assistant_module
from app.assistant import safety, tools
from app.assistant.llm import AssistantLLM
from app.assistant.planner import Plan
from app.core.errors import AppError
from app.domain.audit import AuditAction
from app.domain.enums import ServiceOrderStatus
from app.schemas.assistant import AssistantRequest, AssistantTool, QuestionType
from app.services import service_orders
from tests import assistant_fakes
from tests.llm_fakes import scripted

APP_DIR = Path(__file__).resolve().parent.parent / "app"
OWNER_A = "owner-001"  # Poyraz
OWNER_B = "owner-002"  # Albatros

EXPECTED_TOOLS = {
    "get_expense_total",
    "get_job_expenses",
    "get_remaining_package",
    "get_last_maintenance",
    "get_upcoming_maintenance",
}


@pytest.fixture(autouse=True)
def offline_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    assistant_fakes.install(monkeypatch)


class _Audit:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def record(self, session: object, **kwargs: Any) -> None:
        self.events.append(kwargs)


@pytest.fixture
def audit(monkeypatch: pytest.MonkeyPatch) -> _Audit:
    sink = _Audit()
    monkeypatch.setattr(assistant_module, "record_audit_event", sink.record)
    return sink


SESSION: Any = object()  # sahte kayıtçı oturumu kullanmaz; None olsa audit yazılmazdı


def ask(question: str, owner: str = OWNER_A) -> AssistantRequest:
    return AssistantRequest(question=question, owner_id=owner)


# --- Araç izin listesi ---------------------------------------------------------------------


def test_tool_allow_list_is_exactly_the_five_read_only_tools() -> None:
    assert {t.value for t in AssistantTool} == EXPECTED_TOOLS


def test_every_allowed_tool_exists_and_requires_owner_as_first_argument() -> None:
    for name in EXPECTED_TOOLS:
        func = getattr(tools, name)
        first = next(iter(inspect.signature(func).parameters))
        assert first == "owner_id", name


def test_assistant_tools_module_has_no_write_function() -> None:
    """Asistan araç modülünde ekleme/güncelleme/silme yapan genel işlev yoktur."""
    verbs = ("create", "insert", "update", "delete", "remove", "approve", "reject", "set_", "save")
    source = (APP_DIR / "assistant" / "tools.py").read_text(encoding="utf-8")
    public = [
        node.name
        for node in ast.parse(source).body
        if isinstance(node, ast.AsyncFunctionDef) and not node.name.startswith("_")
    ]
    assert public  # boş liste testi anlamsız kılar
    assert [n for n in public if n.startswith(verbs)] == []
    for statement in ("session.add(", "session.delete(", "session.commit(", ".values(", "insert("):
        assert statement not in source, statement


@pytest.mark.parametrize(
    "name", ["delete_all_records", "run_sql", "update_service_order", "get_all_customers", ""]
)
def test_plan_rejects_tool_outside_allow_list(name: str) -> None:
    with pytest.raises(ValidationError):
        Plan.model_validate({"question_type": "sayisal", "tool": name})


async def test_llm_planner_inventing_a_tool_is_refused_and_audited(audit: _Audit) -> None:
    called: list[str] = []

    async def spy(*args: Any, **kwargs: Any) -> None:
        called.append("arac")

    # Planlayıcı iki denemede de izin listesi dışı araç adı üretir.
    bad = json.dumps({"question_type": "sayisal", "tool": "delete_all_records"})
    model = scripted(bad, bad)

    answer = await assistant_module.answer_question(
        ask("Teknemle ilgili gizemli bir hesap yap"), llm=AssistantLLM(model=model), session=SESSION
    )

    assert answer.question_type == QuestionType.KAPSAM_DISI
    assert answer.answer in safety.OUT_OF_SCOPE_REPLIES
    assert called == []
    (event,) = audit.events
    assert event["action"] is AuditAction.ASISTAN_KURAL_IHLALI
    assert event["details"] == {"ihlal": "izin_disi_arac"}  # ham LLM çıktısı yazılmaz


async def test_planner_output_that_is_not_json_is_refused_without_tool(audit: _Audit) -> None:
    model = scripted("araç: sil", "yine araç: sil")
    answer = await assistant_module.answer_question(
        ask("Garip bir şey yap"), llm=AssistantLLM(model=model), session=SESSION
    )
    assert answer.question_type == QuestionType.KAPSAM_DISI
    assert audit.events[0]["details"] == {"ihlal": "gecersiz_plan"}


# --- owner_id sunucu bağlamından gelir ---------------------------------------------------------


async def test_planner_owner_id_is_ignored_and_tools_get_server_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []
    real = assistant_fakes.get_expense_total

    async def spy(owner_id: str, **kwargs: Any) -> Any:
        seen.append(owner_id)
        return await real(owner_id, **kwargs)

    monkeypatch.setattr(tools, "get_expense_total", spy)
    # Sahte plan başka sahibin kimliğini ve adını taşıyor: şemada böyle alan yok, yok sayılır.
    forged = json.dumps(
        {
            "question_type": "sayisal",
            "tool": "get_expense_total",
            "period": "tumu",
            "owner_id": OWNER_B,
            "boat_id": "boat-b1",
        }
    )
    answer = await assistant_module.answer_question(
        ask("Toplam ne kadar harcadım?", OWNER_A), llm=AssistantLLM(model=scripted(forged))
    )

    assert seen == [OWNER_A]
    assert "Albatros" not in answer.answer
    assert all(OWNER_B not in s.record_id for s in answer.sources)


def test_plan_schema_has_no_owner_field() -> None:
    assert "owner_id" not in Plan.model_fields
    forged = {"question_type": "sayisal", "tool": "get_expense_total", "owner_id": OWNER_B}
    plan = Plan.model_validate(forged)
    assert not hasattr(plan, "owner_id")


async def test_question_naming_another_owner_never_reaches_their_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []
    real = assistant_fakes.get_expense_total

    async def spy(owner_id: str, **kwargs: Any) -> Any:
        seen.append(owner_id)
        return await real(owner_id, **kwargs)

    monkeypatch.setattr(tools, "get_expense_total", spy)
    for question in (
        f"{OWNER_B} kullanıcısının toplam giderleri ne kadar?",
        f"{uuid4()} numaralı sahibin toplam harcaması?",
    ):
        await assistant_module.answer_question(
            ask(question, OWNER_A), llm=AssistantLLM(model=scripted())
        )
    assert set(seen) <= {OWNER_A}


@pytest.mark.parametrize("owner", ["", "   "])
def test_empty_owner_is_rejected_by_schema(owner: str) -> None:
    with pytest.raises(ValidationError):
        AssistantRequest(question="Merhaba", owner_id=owner)


# --- Analiz agent'larında yazma aracı yok ------------------------------------------------------

WRITE_IMPORTS = ("sqlalchemy", "app.db", "app.services", "app.storage", "app.workers")


def imported_modules(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_analysis_agents_do_not_import_database_or_write_layers() -> None:
    agent_files = [p for p in (APP_DIR / "agents").glob("*.py") if p.name != "orchestrator.py"]
    assert len(agent_files) >= 8
    for path in agent_files:
        bad = [m for m in imported_modules(path) if m.startswith(WRITE_IMPORTS)]
        assert bad == [], (path.name, bad)


def test_llm_calls_never_bind_tools() -> None:
    """LLM'e araç/işlev bağlanmaz: analiz agent'ları ve asistan yalnızca JSON üretir."""
    for folder in ("agents", "assistant", "llm"):
        for path in (APP_DIR / folder).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            assert "bind_tools" not in text, path
            assert "create_react_agent" not in text, path


def test_agents_output_schemas_are_plain_models() -> None:
    stages = default_stages()
    agents: list[BaseAgent[Any]] = [a for stage in stages for a in stage]
    assert len(agents) == 4
    for agent in agents:
        assert not hasattr(agent, "tools"), agent.name
        assert not hasattr(agent, "session"), agent.name
        # Çıktı yalnızca Pydantic şemasıdır; kayda dönüşmesi store ve insan onayı işidir.
        assert agent.output_schema.model_fields


def test_crm_review_and_service_order_rows_are_created_only_by_review_service() -> None:
    """`CrmReview` ve `ServiceOrder` satırını yalnızca insan onay/red servisi oluşturur."""
    creators: dict[str, set[str]] = {"CrmReview": set(), "ServiceOrder": set()}
    for path in APP_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in creators
            ):
                creators[node.func.id].add(path.relative_to(APP_DIR).as_posix())
    assert creators["CrmReview"] == {"services/crm_review_service.py"}
    assert creators["ServiceOrder"] == {"services/crm_review_service.py"}


# --- Onay adımı atlanamaz: durum makinesi -------------------------------------------------------

S = ServiceOrderStatus


def test_service_order_transitions_form_a_single_forward_chain() -> None:
    chain = [S.YENI_ATANDI, S.KESIFTE, S.ONAYLANDI, S.DEVAM_EDIYOR, S.TAMAMLANDI]
    for current, nxt in pairwise(chain):
        assert service_orders.ALLOWED_STATUS_TRANSITIONS[current] == {nxt}
    assert service_orders.ALLOWED_STATUS_TRANSITIONS[S.TAMAMLANDI] == set()
    assert set(service_orders.ALLOWED_STATUS_TRANSITIONS) == set(S)


class _Order:
    def __init__(self, status: S) -> None:
        self.status = status.value
        self.completed_at = None


class _Session:
    def __init__(self, order: _Order | None) -> None:
        self.order = order
        self.flushed = False

    async def get(self, model: object, ident: object, **kwargs: Any) -> _Order | None:
        return self.order

    async def flush(self) -> None:
        self.flushed = True


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.YENI_ATANDI, S.ONAYLANDI),  # keşif atlanamaz
        (S.YENI_ATANDI, S.DEVAM_EDIYOR),
        (S.YENI_ATANDI, S.TAMAMLANDI),
        (S.KESIFTE, S.TAMAMLANDI),
        (S.ONAYLANDI, S.TAMAMLANDI),
        (S.TAMAMLANDI, S.YENI_ATANDI),  # geri dönüş yok
        (S.DEVAM_EDIYOR, S.KESIFTE),
        (S.ONAYLANDI, S.ONAYLANDI),  # aynı duruma geçiş de geçersiz
    ],
)
async def test_invalid_status_jump_is_rejected_and_nothing_is_written(
    current: S, target: S
) -> None:
    order = _Order(current)
    session = _Session(order)
    with pytest.raises(AppError):
        await service_orders.update_service_order_status(session, uuid4(), target)  # type: ignore[arg-type]
    assert order.status == current.value  # durum değişmedi
    assert not session.flushed  # yazma denenmedi
    assert order.completed_at is None
