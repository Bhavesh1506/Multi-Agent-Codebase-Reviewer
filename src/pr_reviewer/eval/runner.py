"""Offline benchmark runner and measurable review quality metrics."""

import json
import tempfile
import time
from pathlib import Path

from pydantic import Field

from pr_reviewer.config import Settings
from pr_reviewer.eval.fixtures import BenchmarkFixture, benchmark_fixtures
from pr_reviewer.llm.base import LLMProvider
from pr_reviewer.llm.mock_client import MockClient
from pr_reviewer.pipeline.orchestrator import ReviewOrchestrator
from pr_reviewer.schemas import StrictModel


class CaseResult(StrictModel):
    name: str
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    token_count: int = 0
    latency_seconds: float = 0


class BenchmarkMetrics(StrictModel):
    provider: str
    token_count_is_estimate: bool
    precision: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)
    false_positive_rate: float = Field(ge=0, le=1)
    true_positives: int
    false_positives: int
    false_negatives: int
    clean_cases_with_findings: int
    clean_cases: int
    token_count: int
    latency_seconds: float
    cases: list[CaseResult]


def heuristic_response(prompt: str, _schema: dict) -> dict:
    """Transparent offline baseline; only changed-line patterns are inspected."""
    agent = prompt.splitlines()[0].removeprefix("Agent: ")
    context = json.loads(prompt.split("Context: ", 1)[1].split("\nPrevious response", 1)[0])
    findings = []
    for file in context["files"]:
        removed = "\n".join(line["text"] for line in file["changed_lines"] if line["kind"] == "removed")
        added = [line for line in file["changed_lines"] if line["kind"] == "added"]
        trigger = None
        if agent == "concurrency_guard" and "with lock" in removed:
            trigger = next((line for line in added if "+=" in line["text"]), None)
            title = "Unguarded shared update"
        elif agent == "contract_auditor" and '"amount"' in removed:
            trigger = next((line for line in added if '"total"' in line["text"]), None)
            title = "Response field changed"
        elif agent == "concurrency_guard" and "processed.add" in removed:
            trigger = next((line for line in added if "send_charge(" in line["text"]), None)
            title = "Idempotency guard removed"
        elif agent == "test_gap_finder" and not file["related_tests"]:
            trigger = next((line for line in added if "if count == 0:" in line["text"]), None)
            title = "Zero-count branch lacks regression test"
        if trigger:
            findings.append({
                "agent": agent,
                "path": file["path"],
                "line": trigger["line"],
                "title": title,
                "explanation": "Changed behavior matches a high-risk offline benchmark pattern.",
                "confidence": 0.85,
                "evidence": [f"{file['path']}:{trigger['line']}: {trigger['text']}"],
            })
    return {"findings": findings}


async def run_benchmark(
    settings: Settings | None = None,
    provider: LLMProvider | None = None,
    fixtures: tuple[BenchmarkFixture, ...] | None = None,
) -> BenchmarkMetrics:
    """Score unique (path, line) matches per fixture; FPR is affected clean cases / clean cases."""
    settings = settings or Settings()
    fixtures = benchmark_fixtures() if fixtures is None else fixtures
    if provider is None and settings.llm_provider == "mock":
        provider = MockClient(heuristic_response)
        provider_name = "heuristic_mock"
    else:
        provider_name = type(provider).__name__ if provider is not None else settings.llm_provider
    started = time.monotonic()
    cases = []
    clean_cases = clean_cases_with_findings = 0
    for fixture in fixtures:
        with tempfile.TemporaryDirectory(prefix="diffpulse-eval-") as temporary:
            root = Path(temporary)
            for path, content in fixture.files.items():
                target = root / path
                if not target.resolve().is_relative_to(root):
                    raise ValueError(f"fixture path escapes root: {path}")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            result = await ReviewOrchestrator(root, provider=provider, settings=settings).review_diff(fixture.diff)
        expected = {(finding.path, finding.line) for finding in fixture.expected}
        predicted = [(finding.path, finding.line) for finding in result.verdict.findings]
        matches = set(predicted) & expected
        cases.append(CaseResult(
            name=fixture.name,
            true_positives=len(matches),
            false_positives=len(predicted) - len(matches),
            false_negatives=len(expected) - len(matches),
            token_count=result.total_tokens,
            latency_seconds=result.latency_seconds,
        ))
        if not fixture.expected:
            clean_cases += 1
            clean_cases_with_findings += bool(predicted)
    tp = sum(case.true_positives for case in cases)
    fp = sum(case.false_positives for case in cases)
    fn = sum(case.false_negatives for case in cases)
    return BenchmarkMetrics(
        provider=provider_name,
        token_count_is_estimate=isinstance(provider, MockClient),
        precision=tp / (tp + fp) if tp + fp else 0,
        recall=tp / (tp + fn) if tp + fn else 0,
        false_positive_rate=clean_cases_with_findings / clean_cases if clean_cases else 0,
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        clean_cases_with_findings=clean_cases_with_findings,
        clean_cases=clean_cases,
        token_count=sum(case.token_count for case in cases),
        latency_seconds=time.monotonic() - started,
        cases=cases,
    )
