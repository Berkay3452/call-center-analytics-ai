"""Yetkisiz araç ve aşırı yetki (OWASP LLM06, API5, API7): LLM yalnızca izin listesindeki
okuma araçlarını, yalnızca sunucunun bildiği sahip için çağırabilir.

Veritabanı gerekmez: geçersiz kimlikler sorgudan önce boş sonuçla kapanır.
"""

import ast
import inspect
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.assistant import tools
from app.assistant.planner import Plan
from app.assistant.tools import OwnerRequiredError
from app.schemas.assistant import AssistantTool

APP = Path(tools.__file__).parents[1]
INJECTION_IDS = [
    "1 OR 1=1",
    "'; DROP TABLE boats;--",
    "' UNION SELECT * FROM customers--",
    "../../etc/passwd",
    "00000000-0000-0000-0000-000000000000'--",
    "%s",
    "null",
    "{{7*7}}",
    "9" * 400,
]


@pytest.mark.parametrize(
    "name", ["run_sql", "shell", "send_email", "delete_call", "update_order", "eval"]
)
def test_planner_cannot_invent_a_tool(name: str) -> None:
    with pytest.raises(ValidationError):
        Plan.model_validate({"question_type": "sayisal", "tool": name})


def test_plan_has_no_field_through_which_the_model_could_choose_the_owner() -> None:
    fields = set(Plan.model_fields)

    assert not {"owner_id", "owner", "user_id", "customer_id", "sql", "query"} & fields


@pytest.mark.parametrize("owner", ["", " ", "\t", "\n"])
async def test_every_tool_refuses_a_blank_owner(owner: str) -> None:
    calls = (
        lambda: tools.get_expense_total(owner),
        lambda: tools.get_remaining_package(owner),
        lambda: tools.get_last_maintenance(owner),
        lambda: tools.get_upcoming_maintenance(owner, today=date.today()),
        lambda: tools.get_job_expenses(owner, ["akü"]),
    )
    for make_call in calls:
        with pytest.raises(OwnerRequiredError):
            await make_call()


@pytest.mark.parametrize("bad", INJECTION_IDS)
async def test_injection_in_ids_returns_nothing_and_never_reaches_the_database(bad: str) -> None:
    """Kimlik alanına SQL/şablon yerleştirme: UUID olmadığı için sorgu hiç çalışmaz."""
    total = await tools.get_expense_total(bad)
    boat_total = await tools.get_expense_total("11111111-1111-4111-8111-111111111111", boat_id=bad)

    assert total.total_try == Decimal("0") and total.item_count == 0
    assert boat_total.total_try == Decimal("0") and boat_total.sources == []
    assert await tools.get_remaining_package(bad) is None
    assert await tools.get_last_maintenance(bad, boat_id=bad) is None
    assert (await tools.get_job_expenses(bad, ["akü"])).items == []


def test_tool_surface_is_read_only_and_owner_first() -> None:
    allowed = {t.value for t in AssistantTool}

    for name in allowed:
        first = next(iter(inspect.signature(getattr(tools, name)).parameters))
        assert first == "owner_id", name
    module = ast.parse((APP / "assistant" / "tools.py").read_text(encoding="utf-8"))
    public = [
        n.name
        for n in module.body
        if isinstance(n, ast.AsyncFunctionDef) and not n.name.startswith("_")
    ]
    mutating = [n for n in public if n.startswith(("create", "insert", "update", "delete", "set_"))]
    assert mutating == []


def test_llm_never_receives_tool_bindings_or_a_database_handle() -> None:
    """Model araç çağırma yeteneği almaz; araçları yalnızca sunucu kodu çalıştırır."""
    offenders = []
    for path in (APP / "assistant").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "bind_tools" in text or "create_react_agent" in text or "AgentExecutor" in text:
            offenders.append(path.name)
    for path in (APP / "agents").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "bind_tools" in text or "create_react_agent" in text or "AgentExecutor" in text:
            offenders.append(path.name)

    assert offenders == []


def test_ssrf_surface_is_a_single_configured_http_client() -> None:
    """API7: dış HTTP çağrısı yapan modüller gömme ve reranker istemcileridir (#357); adresleri
    ortam ayarından gelir, kullanıcı girdisinden değil."""
    markers = ("import httpx", "import requests", "aiohttp")
    users = sorted(
        p.relative_to(APP).as_posix()
        for p in APP.rglob("*.py")
        if any(m in p.read_text(encoding="utf-8") for m in markers)
    )

    assert users == ["rag/embedders.py", "rag/rerankers.py"]
    for module in users:
        assert "settings." in (APP / module).read_text(encoding="utf-8")


def test_analysis_agents_cannot_import_the_write_layer() -> None:
    forbidden = ("app.services.crm_review_service", "app.services.service_orders", "app.db.session")
    offenders = []
    for path in (APP / "agents").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            offenders += [(path.name, n) for n in names if n.startswith(forbidden)]

    assert offenders == []
