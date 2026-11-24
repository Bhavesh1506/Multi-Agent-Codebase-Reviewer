"""Deterministic offline provider for CI and local demos."""

import json
from collections.abc import Callable

from pr_reviewer.llm.base import LLMProvider, LLMResponse


class MockClient(LLMProvider):
    def __init__(self, responder: Callable[[str, dict], dict | str] | None = None) -> None:
        self.responder = responder or (lambda _prompt, _schema: {"findings": []})
        self.calls: list[str] = []

    async def generate(self, prompt: str, schema: dict) -> LLMResponse:
        self.calls.append(prompt)
        value = self.responder(prompt, schema)
        content = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
        # These are explicitly estimates, never presented as provider usage.
        return LLMResponse(
            content=content,
            prompt_tokens=max(1, len(prompt) // 4),
            completion_tokens=max(1, len(content) // 4),
        )
