"""Deterministically deduplicate and filter specialist findings."""

from pr_reviewer.schemas import Finding


class CriticSynthesizer:
    name = "critic_synthesizer"

    def synthesize(self, findings: list[Finding], min_confidence: float) -> list[Finding]:
        if not 0 <= min_confidence <= 1:
            raise ValueError("min_confidence must be between 0 and 1")
        best: dict[tuple[str, int | None, str], Finding] = {}
        for finding in findings:
            if finding.confidence < min_confidence or not finding.evidence:
                continue
            key = (finding.path, finding.line, finding.title.casefold().strip())
            if key not in best or finding.confidence > best[key].confidence:
                best[key] = finding
        return sorted(best.values(), key=lambda f: (-f.confidence, f.path, f.line or 0, f.title))
