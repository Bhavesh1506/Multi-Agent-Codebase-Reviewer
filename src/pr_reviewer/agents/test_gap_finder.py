"""Find concrete missing regression coverage for changed behavior."""

from pr_reviewer.agents.base_agent import BaseAgent


class TestGapFinder(BaseAgent):
    name = "test_gap_finder"
    instruction = (
        "Use changed branches and related test files to identify specific uncovered regression cases. "
        "Do not complain merely because a test file was not changed; cite the behavior and path."
    )
