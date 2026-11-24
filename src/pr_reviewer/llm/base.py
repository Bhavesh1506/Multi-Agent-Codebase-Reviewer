"""Provider contract and per-call accounting."""

from abc import ABC, abstractmethod

from pydantic import Field

from pr_reviewer.schemas import StrictModel


class LLMError(RuntimeError):
    """A provider failed after its bounded retry policy."""


class LLMResponse(StrictModel):
    content: str
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    latency_seconds: float = Field(default=0, ge=0)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, schema: dict) -> LLMResponse:
        """Produce one JSON response conforming to schema."""
