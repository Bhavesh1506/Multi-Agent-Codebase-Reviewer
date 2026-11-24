import json
import tempfile

import pytest

from pr_reviewer.cli import main
from pr_reviewer.config import Settings
from pr_reviewer.eval.fixtures import benchmark_fixtures
from pr_reviewer.eval.runner import run_benchmark
from pr_reviewer.ingestion.diff_parser import parse_diff
from pr_reviewer.llm.mock_client import MockClient


def test_fixtures_include_planted_bugs_and_clean_cases():
    fixtures = benchmark_fixtures()
    assert len(fixtures) == 6
    assert {expected.category for fixture in fixtures for expected in fixture.expected} == {
        "race_condition", "api_contract", "idempotency", "test_gap"
    }
    assert sum(not fixture.expected for fixture in fixtures) == 2
    for fixture in fixtures:
        parsed = parse_diff(fixture.diff)
        assert parsed.files
        changed = {(file.path, line.new_line) for file in parsed.files for line in file.added_lines}
        assert all((expected.path, expected.line) in changed for expected in fixture.expected)


@pytest.mark.asyncio
async def test_offline_heuristic_metrics_are_complete():
    metrics = await run_benchmark(settings=Settings(llm_provider="mock"))
    assert metrics.provider == "heuristic_mock"
    assert metrics.token_count_is_estimate
    assert (metrics.true_positives, metrics.false_positives, metrics.false_negatives) == (4, 0, 0)
    assert metrics.precision == 1 and metrics.recall == 1
    assert metrics.false_positive_rate == 0 and metrics.clean_cases == 2
    assert metrics.token_count > 0 and metrics.latency_seconds > 0


@pytest.mark.asyncio
async def test_empty_provider_reports_misses_without_division_error():
    metrics = await run_benchmark(settings=Settings(llm_provider="mock"), provider=MockClient())
    assert (metrics.precision, metrics.recall) == (0, 0)
    assert metrics.false_negatives == 4
    assert metrics.false_positive_rate == 0


@pytest.mark.asyncio
async def test_benchmark_accepts_aliased_temp_directory(tmp_path, monkeypatch):
    real_temp = tmp_path / "real"
    real_temp.mkdir()
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(real_temp, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")
    monkeypatch.setattr(tempfile, "tempdir", str(alias))

    metrics = await run_benchmark(
        settings=Settings(llm_provider="mock"), fixtures=benchmark_fixtures()[:1]
    )
    assert metrics.true_positives == 1


@pytest.mark.asyncio
async def test_clean_case_false_positive_rate():
    clean = tuple(fixture for fixture in benchmark_fixtures() if not fixture.expected)

    def noisy(prompt, _schema):
        context = json.loads(prompt.split("Context: ", 1)[1])
        file = context["files"][0]
        line = next(line for line in file["changed_lines"] if line["kind"] == "added")
        return {"findings": [{
            "agent": prompt.splitlines()[0].removeprefix("Agent: "),
            "path": file["path"], "line": line["line"], "title": "False alarm",
            "explanation": "No real bug", "confidence": 0.9, "evidence": ["changed line"],
        }]}

    metrics = await run_benchmark(
        settings=Settings(llm_provider="mock"), provider=MockClient(noisy), fixtures=clean
    )
    assert metrics.false_positive_rate == 1
    assert metrics.clean_cases_with_findings == 2
    assert metrics.false_positives == 2


def test_cli_eval_json(capsys):
    assert main(["eval", "--mock", "--json"]) == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["true_positives"] == 4
    assert metrics["provider"] == "heuristic_mock"
