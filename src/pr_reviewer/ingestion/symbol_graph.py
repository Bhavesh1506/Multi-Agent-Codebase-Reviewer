"""Deterministic Python symbols, imports, calls, and changed-line impact."""

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Symbol:
    path: str
    name: str
    qualified_name: str
    kind: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class ImportRef:
    path: str
    module: str
    name: str | None
    alias: str
    line: int


@dataclass(frozen=True)
class CallRef:
    path: str
    caller: str | None
    target: str
    line: int


@dataclass
class SymbolGraph:
    symbols: list[Symbol] = field(default_factory=list)
    imports: list[ImportRef] = field(default_factory=list)
    calls: list[CallRef] = field(default_factory=list)
    parse_failures: set[str] = field(default_factory=set)

    def symbols_at_lines(self, path: str, lines: set[int]) -> list[Symbol]:
        """Return the innermost symbol containing each changed new-file line."""
        selected: set[Symbol] = set()
        candidates = [s for s in self.symbols if s.path == path]
        for line in lines:
            matches = [s for s in candidates if s.start_line <= line <= s.end_line]
            if matches:
                selected.add(min(matches, key=lambda s: (s.end_line - s.start_line, -s.start_line)))
        return sorted(selected, key=lambda s: (s.path, s.start_line, s.name))

    def callers_of(self, symbol: Symbol) -> list[CallRef]:
        """Resolve direct calls and imported aliases conservatively."""
        module = module_name(symbol.path)
        matching: list[CallRef] = []
        for call in self.calls:
            local_targets = {symbol.name, symbol.qualified_name}
            if "." in symbol.qualified_name:
                local_targets.add(f"self.{symbol.name}")
                local_targets.add(f"cls.{symbol.name}")
            if call.path == symbol.path and call.target in local_targets:
                matching.append(call)
                continue
            for imp in (i for i in self.imports if i.path == call.path):
                if imp.module == module and imp.name == symbol.name and call.target == imp.alias:
                    matching.append(call)
                    break
                if imp.module == module and imp.name is None and call.target in {
                    f"{imp.alias}.{symbol.name}", f"{imp.module}.{symbol.name}"
                }:
                    matching.append(call)
                    break
        return sorted(set(matching), key=lambda c: (c.path, c.line, c.target))


def module_name(path: str) -> str:
    parts = list(Path(path).with_suffix("").parts)
    if parts and parts[0] == "src":
        parts.pop(0)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_name(node.value)
        return f"{base}.{node.attr}" if base else None
    return None


def index_python_source(path: str, source: str) -> SymbolGraph:
    """Index one file. Syntax errors fall back to simple line-based hints."""
    graph = SymbolGraph()
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        graph.parse_failures.add(path)
        scope: str | None = None
        for number, line in enumerate(source.splitlines(), 1):
            match = re.match(r"\s*(?:async\s+)?(def|class)\s+(\w+)", line)
            if match:
                graph.symbols.append(Symbol(path, match[2], match[2], match[1], number, number))
                scope = match[2]
                continue
            match = re.match(r"\s*from\s+([\w.]+)\s+import\s+(\w+)", line)
            if match:
                graph.imports.append(ImportRef(path, match[1], match[2], match[2], number))
            match = re.match(r"\s*import\s+([\w.]+)", line)
            if match:
                graph.imports.append(ImportRef(path, match[1], None, match[1].split(".")[0], number))
            for call in re.finditer(r"\b([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?)\s*\(", line):
                graph.calls.append(CallRef(path, scope, call[1], number))
        return graph

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.scope: list[str] = []

        def _definition(self, node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            qualified = ".".join([*self.scope, node.name])
            kind = "class" if isinstance(node, ast.ClassDef) else "function"
            graph.symbols.append(Symbol(path, node.name, qualified, kind, node.lineno, node.end_lineno or node.lineno))
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        visit_ClassDef = _definition
        visit_FunctionDef = _definition
        visit_AsyncFunctionDef = _definition

        def visit_Import(self, node: ast.Import) -> None:
            for alias in node.names:
                graph.imports.append(ImportRef(path, alias.name, None, alias.asname or alias.name.split(".")[0], node.lineno))

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            module = "." * node.level + (node.module or "")
            for alias in node.names:
                graph.imports.append(ImportRef(path, module, alias.name, alias.asname or alias.name, node.lineno))

        def visit_Call(self, node: ast.Call) -> None:
            target = _call_name(node.func)
            if target:
                graph.calls.append(CallRef(path, ".".join(self.scope) or None, target, node.lineno))
            self.generic_visit(node)

    Visitor().visit(tree)
    return graph


def build_symbol_graph(root: Path, paths: list[str] | None = None) -> SymbolGraph:
    """Index repository Python files, skipping hidden/build directories."""
    root = root.resolve()
    graph = SymbolGraph()
    candidates = (root / path for path in paths) if paths is not None else root.rglob("*.py")
    for file in sorted(candidates):
        if not file.is_file() or file.suffix != ".py" or not file.resolve().is_relative_to(root):
            continue
        relative = file.relative_to(root)
        if any(part.startswith(".") or part in {"__pycache__", "build", "dist"} for part in relative.parts):
            continue
        try:
            source = file.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        partial = index_python_source(relative.as_posix(), source)
        graph.symbols.extend(partial.symbols)
        graph.imports.extend(partial.imports)
        graph.calls.extend(partial.calls)
        graph.parse_failures.update(partial.parse_failures)
    return graph
