import asyncio
import json

import httpx
import pytest

from pr_reviewer.api.app import create_app
from pr_reviewer.config import Settings
from pr_reviewer.llm.mock_client import MockClient
from pr_reviewer.pipeline.orchestrator import ReviewOrchestrator


PATH = "src/pkg/api/price.py"
DIFF = f"--- /dev/null\n+++ b/{PATH}\n@@ -0,0 +1,2 @@\n+def price():\n+    return 3\n"


def responder():
    attempts = 0

    def respond(prompt, _schema):
        nonlocal attempts
        agent = prompt.splitlines()[0].removeprefix("Agent: ")
        if agent == "scope_analyst" and attempts == 0:
            attempts += 1
            return "invalid"
        return {"findings": [{
            "agent": agent, "path": PATH, "line": 77 if agent == "test_gap_finder" else 2,
            "confidence": 0.5 if agent == "concurrency_guard" else 0.75,
            "title": "Price changed", "explanation": "New price", "evidence": ["return 3"],
            "severity": "high",
        }]}
    return MockClient(respond)


@pytest.mark.asyncio
async def test_event_history_matches_unobserved_verdict(tmp_path):
    directory = tmp_path / "journals"
    path = tmp_path / PATH
    path.parent.mkdir(parents=True)
    path.write_text("def price():\n    return 3\n")
    async def review(events_dir):
        return await ReviewOrchestrator(tmp_path, responder(), Settings(
            islands_events_dir=events_dir)).review_diff(DIFF)

    plain = await review(None)
    assert not directory.exists()
    observed = await review(directory)
    assert observed.verdict == plain.verdict
    assert observed.total_tokens == plain.total_tokens
    events = [json.loads(line) for line in next(directory.glob("*.jsonl")).read_text().splitlines()]
    assert events[0]["event"] == "run_started"
    assert events[-1]["event"] == "run_completed"
    assert [e["seq"] for e in events] == list(range(1, len(events)+1))
    assert any(e.get("symbols") == ["price"] and e["island"] == "api" for e in events)
    assert any(e["status"] == "retrying" and e["agent"] == "scope_analyst" for e in events)
    assert len({e["agent"] for e in events if e["event"] == "agent_moved"}) == 5
    raised = {e["finding_id"] for e in events if e["event"] == "finding_raised"}
    dropped = {e["finding_id"] for e in events if e["event"] == "finding_filtered"}
    assert len(raised) == 4 and raised - dropped == {"scope_analyst/0"}
    kept = [event for event in events if event["event"] == "finding_kept"]
    assert [event["finding_id"] for event in kept] == list(raised - dropped)
    assert kept[0]["severity"] == "high" and kept[0]["evidence"] == ["return 3"]
    assert "confidence threshold" in kept[0]["detail"]
    assert {event["detail"] for event in events if event["event"] == "finding_filtered"} == {
        "Duplicate finding", "Below confidence threshold", "Outside changed lines",
    }
    steps = [event for event in events if event["event"] == "agent_step"
             and "latency_seconds" in event]
    assert [event["status"] for event in steps if event["agent"] == "scope_analyst"] == [
        "failed", "completed",
    ]
    assert sum(event["prompt_tokens"] + event["completion_tokens"] for event in steps) == observed.total_tokens
    assert all(event["latency_seconds"] >= 0 for event in steps)
    assert events[-1]["total_tokens"] == observed.total_tokens
    # An unavailable recorder must not break a normal review.
    assert (await review(path)).verdict == plain.verdict


@pytest.mark.asyncio
async def test_read_only_feed_and_concurrent_run_isolation(tmp_path):
    provider = MockClient()
    app = create_app(tmp_path, provider, Settings(islands_events_dir=tmp_path / "logs"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local") as client:
        assert (await client.get("/islands-data/runs")).json() == []
        assert not provider.calls
        ok, bad = await asyncio.gather(*[
            client.post("/review/diff", json={"diff": value}) for value in [DIFF, "@@ -1 +1 @@\n"]
        ])
        assert (ok.status_code, bad.status_code) == (200, 422)
        ids = (await client.get("/islands-data/runs")).json()
        assert len(ids) == 2
        terminal = set()
        for run in ids:
            url = f"/islands-data/runs/{run}"
            page = (await client.get(url)).json()
            assert all(e["run_id"] == run for e in page["events"])
            terminal.add(page["events"][-1]["event"])
            assert (await client.get(url, params={"cursor": page["cursor"]})).json()["events"] == []
            assert (await client.post(url)).status_code == 405
        assert terminal == {"run_completed", "run_failed"}


@pytest.mark.asyncio
async def test_transport_timeout_reports_real_agent_and_preserves_outcome(tmp_path):
    from pr_reviewer.llm.ollama_client import OllamaClient

    attempts = 0

    def timeout_then_success(request):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ReadTimeout("timeout", request=request)
        return httpx.Response(200, json={"response": '{"findings":[]}'})

    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout_then_success)) as client:
        reviewer = ReviewOrchestrator(tmp_path, OllamaClient(client=client),
                                      Settings(islands_events_dir=tmp_path / "runs"))
        result = await reviewer.review_diff(DIFF)
    records = [json.loads(line) for line in next((tmp_path / "runs").glob("*.jsonl")).read_text().splitlines()]
    retries = [record for record in records if record["status"] == "retrying"]
    assert len(retries) == 1
    assert retries[0]["agent"] == "scope_analyst" and "ReadTimeout" in retries[0]["detail"]
    assert all(trace.error is None for trace in result.traces)
    assert attempts == 5
