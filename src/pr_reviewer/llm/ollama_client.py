"""Local Ollama HTTP adapter with bounded retries and timeouts."""

import asyncio
import time

import httpx

from pr_reviewer.pipeline.events import report_retry
from pr_reviewer.llm.base import LLMError, LLMProvider, LLMResponse


class OllamaClient(LLMProvider):
    def __init__(
        self, model: str = "qwen2.5-coder:7b", base_url: str = "http://localhost:11434",
        timeout_seconds: float = 60, max_attempts: int = 3, client: httpx.AsyncClient | None = None,
    ) -> None:
        if timeout_seconds <= 0 or max_attempts < 1:
            raise ValueError("timeout_seconds and max_attempts must be positive")
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.client = client

    async def generate(self, prompt: str, schema: dict) -> LLMResponse:
        started = time.monotonic()
        payload = {"model": self.model, "prompt": prompt, "stream": False, "format": schema}
        for attempt in range(1, self.max_attempts + 1):
            try:
                if self.client is None:
                    async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                        response = await client.post(f"{self.base_url}/api/generate", json=payload)
                else:
                    response = await self.client.post(
                        f"{self.base_url}/api/generate", json=payload, timeout=self.timeout_seconds
                    )
                response.raise_for_status()
                data = response.json()
                if not isinstance(data.get("response"), str):
                    raise LLMError("Ollama returned no response text")
                return LLMResponse(
                    content=data["response"],
                    prompt_tokens=data.get("prompt_eval_count") or 0,
                    completion_tokens=data.get("eval_count") or 0,
                    latency_seconds=time.monotonic() - started,
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                reason = f"Ollama unavailable: {exc.__class__.__name__}"
            except httpx.HTTPStatusError as exc:
                reason = f"Ollama HTTP {exc.response.status_code}"
                if exc.response.status_code < 500:
                    raise LLMError(reason) from exc
            except ValueError as exc:
                raise LLMError("Ollama returned invalid JSON") from exc
            if attempt == self.max_attempts:
                raise LLMError(f"{reason} after {attempt} attempts")
            report_retry(reason)
            await asyncio.sleep(min(0.25 * 2 ** (attempt - 1), 1.0))
        raise AssertionError("unreachable")
