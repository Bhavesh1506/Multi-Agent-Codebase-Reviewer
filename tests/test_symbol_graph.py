from pr_reviewer.ingestion.local_index import LocalIndex
from pr_reviewer.ingestion.symbol_graph import build_symbol_graph, index_python_source


def test_ast_symbols_imports_calls_and_changed_lines(tmp_path):
    package = tmp_path / "src" / "billing"
    package.mkdir(parents=True)
    (package / "prices.py").write_text(
        "class PriceService:\n"
        "    def total(self, amount):\n"
        "        return amount * 2\n\n"
        "def discount(amount):\n"
        "    return amount - 1\n"
    )
    (package / "api.py").write_text(
        "from billing.prices import discount as apply_discount\n\n"
        "def checkout(amount):\n"
        "    return apply_discount(amount)\n"
    )
    graph = build_symbol_graph(tmp_path)
    names = {symbol.qualified_name for symbol in graph.symbols}
    assert names == {"PriceService", "PriceService.total", "discount", "checkout"}
    changed = graph.symbols_at_lines("src/billing/prices.py", {3, 6})
    assert [symbol.qualified_name for symbol in changed] == ["PriceService.total", "discount"]
    discount = next(symbol for symbol in graph.symbols if symbol.name == "discount")
    assert [(call.path, call.caller, call.line) for call in graph.callers_of(discount)] == [
        ("src/billing/api.py", "checkout", 4)
    ]


def test_syntax_error_falls_back_without_aborting_index():
    graph = index_python_source("broken.py", "import os\ndef helper(:\n    run()\n")
    assert graph.parse_failures == {"broken.py"}
    assert [symbol.name for symbol in graph.symbols] == ["helper"]
    assert graph.imports[0].module == "os"
    assert [(call.caller, call.target) for call in graph.calls] == [("helper", "run")]


def test_bm25_symbol_lookup_and_test_hints(tmp_path):
    source = tmp_path / "src" / "billing"
    tests = tmp_path / "tests"
    source.mkdir(parents=True)
    tests.mkdir()
    (source / "prices.py").write_text("def calculate_invoice_total():\n    return 42\n")
    (source / "auth.py").write_text("def verify_token():\n    return True\n")
    (tests / "test_prices.py").write_text(
        "from billing.prices import calculate_invoice_total\n"
        "def test_calculate_invoice_total():\n    assert calculate_invoice_total() == 42\n"
    )
    index = LocalIndex.from_repository(tmp_path)
    assert index.search("verify token")[0].path == "src/billing/auth.py"
    assert index.lookup_symbol("calculate_invoice_total")[0].path == "src/billing/prices.py"
    assert index.related_tests("src/billing/prices.py")[0].path == "tests/test_prices.py"
    assert index.search("no_matching_term_zz") == []


def test_explicit_paths_cannot_escape_repository(tmp_path):
    outside = tmp_path.parent / "external.py"
    outside.write_text("def secret():\n    pass\n")
    index = LocalIndex.from_repository(tmp_path, ["../external.py"])
    assert index.documents == {}
    assert build_symbol_graph(tmp_path, ["../external.py"]).symbols == []
