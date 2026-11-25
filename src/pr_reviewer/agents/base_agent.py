"""Schema-checked, budgeted agent execution."""

import json
import time

from pydantic import Field, ValidationError

from pr_reviewer.pipeline.events import report_retry, report_step
from pr_reviewer.llm.base import LLMError, LLMProvider
from pr_reviewer.schemas import Finding, StrictModel


class AgentOutput(StrictModel):
    findings: list[Finding] = Field(default_factory=list)


class AgentRun(StrictModel):
    agent: str
    output: AgentOutput = Field(default_factory=AgentOutput)
    steps: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_seconds: float = 0
    error: str | None = None


class BaseAgent:
    name = "base"
    instruction = "Report only actionable, evidence-backed findings."

    def __init__(self, provider: LLMProvider, max_steps: int = 3, max_tokens: int = 8192) -> None:
        if max_steps < 1 or max_tokens < 1:
            raise ValueError("agent budgets must be positive")
        self.provider = provider
        self.max_steps = max_steps
        self.max_tokens = max_tokens

    async def run(self, context: dict) -> AgentRun:
        result = AgentRun(agent=self.name)
        started = time.monotonic()
        prompt = (
            f"Agent: {self.name}\n{self.instruction}\n"
            "Return JSON matching the supplied schema. Cite concrete changed lines; abstain if unsure.\n"
            f"Context: {json.dumps(context, sort_keys=True, default=str)}"
        )
        schema = AgentOutput.model_json_schema()
        try:
            for step in range(1, self.max_steps + 1):
                result.steps = step
                step_started = time.monotonic()
                response = None
                status = "failed"
                report_step(step, "analyzing")
                try:
                    response = await self.provider.generate(prompt, schema)
                    result.prompt_tokens += response.prompt_tokens
                    result.completion_tokens += response.completion_tokens
                    if result.prompt_tokens + result.completion_tokens > self.max_tokens:
                        result.error = "agent token budget exceeded"
                        break
                    try:
                        result.output = AgentOutput.model_validate_json(response.content)
                        if any(finding.agent != self.name for finding in result.output.findings):
                            raise ValueError("finding agent does not match executing agent")
                        result.error = None
                        status = "completed"
                        break
                    except (ValidationError, ValueError) as exc:
                        result.output = AgentOutput()
                        result.error = f"invalid agent JSON: {exc.__class__.__name__}"
                        prompt += "\nPrevious response failed schema validation. Return only valid JSON."
                finally:
                    report_step(step, status, prompt_tokens=response.prompt_tokens if response else None,
                                completion_tokens=response.completion_tokens if response else None,
                                latency_seconds=time.monotonic() - step_started)
                if step < self.max_steps:
                    report_retry(result.error)
        except LLMError as exc:
            result.error = str(exc)
        finally:
            result.latency_seconds = time.monotonic() - started
        return result
