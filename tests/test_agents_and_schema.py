import httpx
import pytest

from pr_reviewer.agents.base_agent import BaseAgent
from pr_reviewer.llm.base import LLMError
from pr_reviewer.llm.mock_client import MockClient
from pr_reviewer.llm.ollama_client import OllamaClient


@pytest.mark.asyncio
async def test_agent_retries_invalid_json_and_tracks_usage():
    values = iter(["not json", {"findings": []}])
    provider = MockClient(lambda _prompt, _schema: next(values))
    agent = BaseAgent(provider, max_steps=2)
    run = await agent.run({"changed": ["x.py"]})
    assert run.steps == 2 and run.error is None
    assert run.prompt_tokens > 0 and run.completion_tokens > 0
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_agent_rejects_bad_schema_and_budget():
    bad = MockClient(lambda _prompt, _schema: {"findings": [], "unexpected": True})
    run = await BaseAgent(bad, max_steps=2).run({})
    assert run.steps == 2 and run.error and run.output.findings == []
    budget = await BaseAgent(MockClient(), max_tokens=1).run({})
    assert budget.error == "agent token budget exceeded"


@pytest.mark.asyncio
async def test_ollama_retries_server_error_and_accounts_tokens():
    attempts = 0

    def handler(_request):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"response": '{"findings": []}', "prompt_eval_count": 12, "eval_count": 4})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await OllamaClient(client=client).generate("review", {"type": "object"})
    assert attempts == 2
    assert response.total_tokens == 16 and response.latency_seconds >= 0


@pytest.mark.asyncio
async def test_ollama_does_not_retry_client_errors():
    attempts = 0

    def handler(_request):
        nonlocal attempts
        attempts += 1
        return httpx.Response(400)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(LLMError, match="HTTP 400"):
            await OllamaClient(client=client).generate("review", {})
    assert attempts == 1
