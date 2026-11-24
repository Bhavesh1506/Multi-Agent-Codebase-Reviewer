"""Review unified diffs with bounded local context and specialist agents."""

import time
from pathlib import Path

from pydantic import Field

from pr_reviewer.agents.base_agent import AgentRun, BaseAgent
from pr_reviewer.agents.concurrency_guard import ConcurrencyGuard
from pr_reviewer.agents.contract_auditor import ContractAuditor
from pr_reviewer.agents.critic_synthesizer import CriticSynthesizer
from pr_reviewer.agents.scope_analyst import ScopeAnalyst
from pr_reviewer.agents.test_gap_finder import TestGapFinder
from pr_reviewer.config import Settings
from pr_reviewer.ingestion.diff_parser import parse_diff
from pr_reviewer.ingestion.local_index import LocalIndex
from pr_reviewer.llm.base import LLMProvider
from pr_reviewer.llm.mock_client import MockClient
from pr_reviewer.llm.ollama_client import OllamaClient
from pr_reviewer.schemas import FileDiff, ReviewVerdict, StrictModel


class PipelineResult(StrictModel):
    verdict: ReviewVerdict
    traces: list[AgentRun] = Field(default_factory=list)
    total_tokens: int = 0
    latency_seconds: float = 0


class ReviewOrchestrator:
    def __init__(
        self, root: Path, provider: LLMProvider | None = None,
        settings: Settings | None = None, min_confidence: float | None = None,
    ) -> None:
        self.root = root.resolve()
        self.settings = settings or Settings()
        self.min_confidence = (
            self.settings.review_confidence_threshold if min_confidence is None else min_confidence
        )
        if not 0 <= self.min_confidence <= 1:
            raise ValueError("min_confidence must be between 0 and 1")
        if provider is None:
            if self.settings.llm_provider == "openai_compatible":
                raise ValueError("openai_compatible provider is not implemented in this slice")
            provider = (MockClient() if self.settings.llm_provider == "mock" else OllamaClient(
                model=self.settings.ollama_model,
                base_url=self.settings.ollama_base_url,
                timeout_seconds=self.settings.llm_timeout_seconds,
            ))
        self.agents: list[BaseAgent] = [
            cls(provider, max_steps=self.settings.review_max_agent_steps)
            for cls in (ScopeAnalyst, ContractAuditor, ConcurrencyGuard, TestGapFinder)
        ]
        self.critic = CriticSynthesizer()

    def _file_context(self, file: FileDiff, index: LocalIndex) -> dict:
        path = file.path
        changed = {line.new_line for line in file.added_lines if line.new_line is not None}
        symbols = index.graph.symbols_at_lines(path, changed)
        calls = [call for symbol in symbols for call in index.graph.callers_of(symbol)]
        lines = [
            {"kind": line.kind.value, "line": line.new_line or line.old_line, "text": line.content[:240]}
            for hunk in file.hunks for line in hunk.lines if line.kind.value != "context"
        ][:50]
        return {
            "path": path,
            "binary": file.is_binary,
            "changed_symbols": [symbol.qualified_name for symbol in symbols[:20]],
            "callers": [f"{call.path}:{call.line}:{call.caller or '<module>'}" for call in calls[:20]],
            "imports": [imp.module for imp in index.graph.imports if imp.path == path][:20],
            "related_tests": [hit.path for hit in index.related_tests(path, limit=5)],
            "changed_lines": lines,
        }

    async def review_diff(self, diff_text: str) -> PipelineResult:
        started = time.monotonic()
        parsed = parse_diff(diff_text)
        index = LocalIndex.from_repository(self.root)
        context = {"files": [self._file_context(file, index) for file in parsed.files[:20]]}
        traces = [await agent.run(context) for agent in self.agents]
        changed_lines = {
            file.path: {line.new_line for line in file.added_lines}
            for file in parsed.files
        }
        findings = [
            finding for trace in traces for finding in trace.output.findings
            if finding.path in changed_lines and finding.line in changed_lines[finding.path]
        ]
        accepted = self.critic.synthesize(findings, self.min_confidence)
        verdict = ReviewVerdict(
            findings=accepted,
            summary=f"Reviewed {len(parsed.files)} changed file(s); {len(accepted)} actionable finding(s).",
            changed_files=[file.path for file in parsed.files],
        )
        return PipelineResult(
            verdict=verdict, traces=traces,
            total_tokens=sum(trace.prompt_tokens + trace.completion_tokens for trace in traces),
            latency_seconds=time.monotonic() - started,
        )
