import json

import pytest

from pr_reviewer.agents.critic_synthesizer import CriticSynthesizer
from pr_reviewer.config import Settings
from pr_reviewer.llm.mock_client import MockClient
from pr_reviewer.pipeline.orchestrator import ReviewOrchestrator
from pr_reviewer.schemas import Finding


DIFF = """diff --git a/src/billing/prices.py b/src/billing/prices.py
--- a/src/billing/prices.py
+++ b/src/billing/prices.py
@@ -1,2 +1,2 @@
 def total(amount):
-    return amount * 2
+    return amount * 3
"""


@pytest.mark.asyncio
async def test_context_precedes_agents_and_filters_findings(tmp_path):
    source = tmp_path / "src" / "billing"
    source.mkdir(parents=True)
    (source / "prices.py").write_text("def total(amount):\n    return amount * 3\n")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_prices.py").write_text("from billing.prices import total\nassert total(1) == 2\n")

    def respond(prompt, _schema):
        context = json.loads(prompt.split("Context: ", 1)[1])
        assert context["files"][0]["changed_symbols"] == ["total"]
        assert context["files"][0]["related_tests"] == ["tests/test_prices.py"]
        agent = prompt.splitlines()[0].split(": ", 1)[1]
        finding = {
            "agent": agent, "path": "src/billing/prices.py", "line": 2,
            "title": "Price regression", "explanation": "Multiplier changed from 2 to 3",
            "confidence": 0.9, "evidence": ["line 2 changes the multiplier"],
        }
        if agent == "scope_analyst":
            return {"findings": [finding]}
        if agent == "contract_auditor":
            return {"findings": [{**finding, "confidence": 0.8}]}
        if agent == "concurrency_guard":
            return {"findings": [{**finding, "confidence": 0.6, "title": "Low signal"}]}
        return {"findings": [{**finding, "line": 99, "title": "Wrong line"}]}

    provider = MockClient(respond)
    result = await ReviewOrchestrator(tmp_path, provider=provider, min_confidence=0.75).review_diff(DIFF)
    assert [finding.title for finding in result.verdict.findings] == ["Price regression"]
    assert result.verdict.findings[0].confidence == 0.9
    assert len(result.traces) == 4 and len(provider.calls) == 4
    assert result.total_tokens > 0 and result.latency_seconds >= 0


def test_critic_drops_unevidenced_findings_and_inclusive_threshold():
    finding = Finding(agent="a", path="x.py", line=1, title="Bug", explanation="Why", confidence=0.75)
    critic = CriticSynthesizer()
    assert critic.synthesize([finding], 0.75) == []
    assert critic.synthesize([finding.model_copy(update={"evidence": ["x.py:1"]})], 0.75)


@pytest.mark.asyncio
async def test_offline_mock_pipeline(tmp_path):
    settings = Settings(llm_provider="mock")
    result = await ReviewOrchestrator(tmp_path, settings=settings).review_diff(DIFF)
    assert result.verdict.findings == []
    assert result.verdict.changed_files == ["src/billing/prices.py"]
