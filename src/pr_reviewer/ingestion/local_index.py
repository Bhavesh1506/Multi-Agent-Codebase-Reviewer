"""Small, dependency-free BM25 and symbol retrieval over local files."""

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from pr_reviewer.ingestion.symbol_graph import SymbolGraph, build_symbol_graph


def _tokens(text: str) -> list[str]:
    # Split both word boundaries and common code names such as getUserId.
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    return re.findall(r"[a-zA-Z][a-zA-Z0-9]*", text.lower())


@dataclass(frozen=True)
class SearchHit:
    path: str
    score: float
    symbols: tuple[str, ...]


class LocalIndex:
    def __init__(self, documents: dict[str, str], graph: SymbolGraph) -> None:
        self.documents = dict(documents)
        self.graph = graph
        self.terms = {path: Counter(_tokens(path + " " + source)) for path, source in documents.items()}
        self.lengths = {path: sum(terms.values()) for path, terms in self.terms.items()}
        self.average_length = sum(self.lengths.values()) / len(self.lengths) if self.lengths else 0
        self.document_frequency = Counter(term for terms in self.terms.values() for term in terms)
        self.symbols_by_path: dict[str, tuple[str, ...]] = {
            path: tuple(sorted(s.qualified_name for s in graph.symbols if s.path == path))
            for path in documents
        }

    @classmethod
    def from_repository(cls, root: Path, paths: list[str] | None = None) -> "LocalIndex":
        root = root.resolve()
        documents: dict[str, str] = {}
        candidates = (root / path for path in paths) if paths is not None else root.rglob("*.py")
        for file in sorted(candidates):
            if not file.is_file() or file.suffix != ".py" or not file.resolve().is_relative_to(root):
                continue
            relative = file.relative_to(root)
            if any(part.startswith(".") or part in {"__pycache__", "build", "dist"} for part in relative.parts):
                continue
            try:
                documents[relative.as_posix()] = file.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
        return cls(documents, build_symbol_graph(root, list(documents)))

    def search(self, query: str, limit: int = 5) -> list[SearchHit]:
        if limit <= 0 or not self.documents:
            return []
        terms = set(_tokens(query))
        if not terms:
            return []
        count = len(self.documents)
        results: list[SearchHit] = []
        for path, frequencies in self.terms.items():
            score = 0.0
            length = self.lengths[path]
            for term in terms:
                frequency = frequencies[term]
                if not frequency:
                    continue
                df = self.document_frequency[term]
                idf = math.log(1 + (count - df + 0.5) / (df + 0.5))
                score += idf * frequency * 2.2 / (
                    frequency + 1.2 * (0.25 + 0.75 * length / (self.average_length or 1))
                )
            if score:
                results.append(SearchHit(path, score, self.symbols_by_path[path]))
        return sorted(results, key=lambda hit: (-hit.score, hit.path))[:limit]

    def lookup_symbol(self, name: str) -> list[SearchHit]:
        return [SearchHit(path, 1.0, symbols) for path, symbols in sorted(self.symbols_by_path.items())
                if any(symbol == name or symbol.endswith("." + name) for symbol in symbols)]

    def related_tests(self, path: str, limit: int = 5) -> list[SearchHit]:
        """Rank test files using filename and symbol terms from the target file."""
        target = Path(path)
        stem = target.stem.removeprefix("test_")
        test_paths = {p for p in self.documents if Path(p).name.startswith("test_") or "/tests/" in f"/{p}"}
        query = " ".join([stem, *(self.symbols_by_path.get(path, ()))])
        ranked = [hit for hit in self.search(query, limit=len(self.documents)) if hit.path in test_paths and hit.path != path]
        return ranked[:limit]
