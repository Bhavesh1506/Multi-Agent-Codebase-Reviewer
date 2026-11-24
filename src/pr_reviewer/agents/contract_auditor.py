"""Check externally visible API and data contracts."""

from pr_reviewer.agents.base_agent import BaseAgent


class ContractAuditor(BaseAgent):
    name = "contract_auditor"
    instruction = (
        "Check changed lines against API, schema, state, auth and error-handling contracts. "
        "Only report a demonstrable regression with a concrete path and changed line."
    )
