"""FastAPI entry point and GitHub pull request webhook adapter."""

import hashlib
import hmac
import json
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import Field

from pr_reviewer.api.visualizer import mount_visualizer
from pr_reviewer.config import Settings
from pr_reviewer.llm.base import LLMProvider
from pr_reviewer.pipeline.orchestrator import PipelineResult, ReviewOrchestrator
from pr_reviewer.schemas import StrictModel


class DiffRequest(StrictModel):
    diff: str = Field(min_length=1, max_length=1_000_000)


def create_app(
    root: Path | None = None, provider: LLMProvider | None = None, settings: Settings | None = None,
) -> FastAPI:
    settings = settings or Settings()
    reviewer = ReviewOrchestrator(root or Path.cwd(), provider=provider, settings=settings)
    app = FastAPI(title="DiffPulse", version="0.1.0")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    async def review(diff: str) -> PipelineResult:
        try:
            result = await reviewer.review_diff(diff)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if result.traces and all(trace.error for trace in result.traces):
            raise HTTPException(status_code=503, detail="all review agents failed; check the model provider")
        return result

    @app.post("/review/diff", response_model=PipelineResult)
    async def review_diff(request: DiffRequest) -> PipelineResult:
        return await review(request.diff)

    @app.post("/webhooks/github")
    async def github_webhook(
        request: Request,
        x_github_event: str | None = Header(default=None),
        x_hub_signature_256: str | None = Header(default=None),
    ) -> dict | PipelineResult:
        body = await request.body()
        if len(body) > 1_000_000:
            raise HTTPException(status_code=413, detail="webhook payload too large")
        if settings.github_webhook_secret:
            expected = "sha256=" + hmac.new(
                settings.github_webhook_secret.encode(), body, hashlib.sha256
            ).hexdigest()
            if not x_hub_signature_256 or not hmac.compare_digest(x_hub_signature_256, expected):
                raise HTTPException(status_code=401, detail="invalid webhook signature")
        if x_github_event != "pull_request":
            return {"status": "ignored", "reason": "not a pull_request event"}
        try:
            payload = json.loads(body)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid JSON payload") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="webhook payload must be a JSON object")
        if payload.get("action") not in {"opened", "reopened", "synchronize"}:
            return {"status": "ignored", "reason": "unsupported action"}
        diff = payload.get("diff")
        if not isinstance(diff, str):
            pull_request = payload.get("pull_request")
            url = pull_request.get("diff_url") if isinstance(pull_request, dict) else None
            parsed_url = urlparse(url) if isinstance(url, str) else None
            if parsed_url is None or parsed_url.scheme != "https" or parsed_url.hostname != "github.com":
                raise HTTPException(status_code=422, detail="missing trusted GitHub diff URL or inline diff")
            headers = {"Accept": "application/vnd.github.v3.diff"}
            if settings.github_token:
                headers["Authorization"] = f"Bearer {settings.github_token}"
            try:
                async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
                    response = await client.get(url, headers=headers)
                    response.raise_for_status()
                    diff = response.text
            except httpx.HTTPError as exc:
                raise HTTPException(status_code=502, detail="could not fetch GitHub diff") from exc
        if not diff or len(diff) > 1_000_000:
            raise HTTPException(status_code=422, detail="diff is empty or too large")
        return await review(diff)

    mount_visualizer(app, settings.islands_events_dir)
    return app


app = create_app()
