"""Identify concrete impact from changed symbols and their callers."""

from pr_reviewer.agents.base_agent import BaseAgent


class ScopeAnalyst(BaseAgent):
    name = "scope_analyst"
    instruction = (
        "Use the supplied changed symbols, imports, callers and test hints to identify "
        "specific downstream behavior at risk. Do not report a generic impact warning. "
        "Only return a finding when the diff supplies evidence of a real defect."
    )
