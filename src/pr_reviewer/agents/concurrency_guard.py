"""Check concurrency, idempotency and resource lifetime."""

from pr_reviewer.agents.base_agent import BaseAgent


class ConcurrencyGuard(BaseAgent):
    name = "concurrency_guard"
    instruction = (
        "Check changed code for races, unsafe locks, lost idempotency, and resource leaks. "
        "Abstain unless a specific execution path proves the risk."
    )
