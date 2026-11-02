"""Sahte LLM sunucusu (scripts/fake_llm.py): her agent'ın şemasına uyan cevap döner (#157)."""

import httpx
import pytest
from pydantic import BaseModel

from app.agents.call_classifier import CallClassifierAgent
from app.agents.crm_extraction import CrmExtractionAgent
from app.agents.llm_agent import LLMAgent
from app.agents.sales_analyzer import SalesAnalyzerAgent
from app.agents.summarizer import SummarizerAgent
from scripts import fake_llm
from tests.test_agents import tuzla_ctx

AGENTS: list[type[LLMAgent]] = [
    CallClassifierAgent,
    CrmExtractionAgent,
    SalesAnalyzerAgent,
    SummarizerAgent,
]


@pytest.mark.parametrize("agent_cls", AGENTS, ids=lambda c: c.name)
def test_canned_reply_validates_against_agent_schema(agent_cls: type[LLMAgent]) -> None:
    agent = agent_cls()
    messages = agent.build_messages(tuzla_ctx())
    request = {"messages": [{"role": "user", "content": str(m.content)} for m in messages]}

    schema: type[BaseModel] = agent.output_schema
    schema.model_validate_json(fake_llm.canned_reply(request))


def test_server_answers_chat_completions() -> None:
    server = fake_llm.start()
    try:
        port = server.server_address[1]
        resp = httpx.post(
            f"http://127.0.0.1:{port}/v1/chat/completions",
            json={"model": "x", "messages": [{"role": "user", "content": "merhaba"}]},
        )
    finally:
        server.shutdown()
        server.server_close()
    assert resp.status_code == 200
    assert resp.json()["choices"][0]["message"]["role"] == "assistant"
