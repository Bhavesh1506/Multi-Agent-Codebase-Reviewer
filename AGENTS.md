# AGENTS.md — Zero-Cost Multi-Agent PR Review & Impact Engine

## 1. Project Mission & Non-Generic Design Principles
Build **DiffPulse** (or keep repo name flexible), a **zero-cost, locally runnable Multi-Agent Codebase PR Reviewer & Impact Engine** designed for backend and full-stack repositories.

This is **not** a generic "chat with your codebase" or "ask an LLM to review a diff" wrapper. It must follow four core engineering principles:
1. **Deterministic Context Before LLM Reasoning:** Extract git hunks, modified functions/classes/symbols, import/caller relationships, and related test files deterministically before invoking any LLM agent.
2. **Specialized, Bounded Multi-Agent Pipeline:** Use distinct, single-responsibility agents with strict JSON schemas, bounded step counts, and explicit confidence thresholds so low-signal opinions are filtered out rather than posted as noise.
3. **Zero Paid SaaS / Zero Credit Card Requirement:** Everything must run locally for free by default (using local/open-source models such as Ollama, local SQLite/FAISS/BM25, and local git/pytest execution), with optional environment-variable adapters for free-tier APIs. Never hardcode paid APIs or require credit cards.
4. **Measurable Evaluation Harness:** Include an offline benchmark dataset of sample PRs/diffs with planted bugs and expected findings, plus a CLI command that reports precision, recall, false-positive rate, token count, and wall-clock latency.

---

## 2. Tech Stack & Zero-Cost Constraints
- **Language & Runtime:** Python 3.11+
- **Web / Webhook API:** FastAPI + Uvicorn (supports GitHub PR webhook payloads as well as local diff/PR fixture runs without needing ngrok or paid tunnels)
- **Validation & Schemas:** Pydantic v2
- **Storage & Retrieval (100% Local & Free):**
  - SQLite for run metadata, PR review history, agent traces, and benchmark results
  - Local lexical (BM25 / rank-bm25) + AST/symbol indexing (plus optional local sentence-transformers / Ollama embeddings; gracefully degrade to AST + BM25 if embeddings are unavailable)
- **LLM Provider (Zero-Cost Default):**
  - Primary local default: **Ollama** HTTP client (`http://localhost:11434`) with configurable model names via env vars (e.g., `OLLAMA_MODEL=qwen2.5-coder:7b` or `llama3.2:3b`), plus a deterministic **Mock/Heuristic LLM provider** for offline CI/unit tests where Ollama is not installed.
  - Optional free-tier OpenAI-compatible endpoint support via env vars (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`), defaulting to local Ollama with zero cost.
- **Testing:** `pytest` + `pytest-asyncio` + `httpx`

---

## 3. Repository Layout
Keep modules clean, modular, and easy to inspect:

```text
├── AGENTS.md
├── pyproject.toml
├── .env.example
├── README.md
├── src/
│   └── pr_reviewer/
│       ├── config.py                # Env-based config (zero-cost defaults)
│       ├── schemas.py               # Strict Pydantic models for diffs, findings, verdicts
│       ├── ingestion/
│       │   ├── diff_parser.py       # Parses unified diffs, hunks, added/removed/modified lines
│       │   ├── symbol_graph.py      # Python AST + regex fallback symbol/caller/import mapper
│       │   └── local_index.py       # Free local BM25 + symbol lookup over repo files
│       ├── llm/
│       │   ├── base.py              # Provider interface + token/latency accounting
│       │   ├── ollama_client.py     # Local Ollama adapter with timeout & retry handling
│       │   └── mock_client.py       # Deterministic offline provider for fast tests
│       ├── agents/
│       │   ├── base_agent.py        # Bounded execution, JSON schema validation, budget guard
│       │   ├── scope_analyst.py     # Agent 1: Maps changed symbols, callers, and risk surfaces
│       │   ├── contract_auditor.py  # Agent 2: Checks API/schema/state/auth/error invariants
│       │   ├── concurrency_guard.py # Agent 3: Detects race conditions, lock/idempotency/resource leaks
│       │   ├── test_gap_finder.py   # Agent 4: Identifies untested branches & missing regression tests
│       │   └── critic_synthesizer.py# Agent 5: Deduplicates, scores confidence, drops low-signal noise
│       ├── pipeline/
│       │   └── orchestrator.py      # Runs deterministic extraction -> bounded agents -> verdict
│       ├── api/
│       │   └── app.py               # FastAPI endpoints (/health, /review/diff, /webhooks/github)
│       ├── eval/
│       │   ├── fixtures.py          # Synthetic PRs with planted real bugs & clean PRs
│       │   └── runner.py            # Computes precision, recall, FP rate, latency, token usage
│       └── cli.py                   # Typer/argparse CLI for local PR review & eval runs
└── tests/
    ├── test_diff_parser.py
    ├── test_symbol_graph.py
    ├── test_agents_and_schema.py
    ├── test_pipeline_end_to_end.py
    └── test_eval_harness.py
```
