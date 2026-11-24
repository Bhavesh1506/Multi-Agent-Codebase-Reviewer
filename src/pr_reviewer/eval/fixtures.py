"""Small synthetic pull requests with independently labelled findings."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ExpectedFinding:
    path: str
    line: int
    category: str


@dataclass(frozen=True)
class BenchmarkFixture:
    name: str
    diff: str
    files: dict[str, str]
    expected: tuple[ExpectedFinding, ...] = ()


def benchmark_fixtures() -> tuple[BenchmarkFixture, ...]:
    return (
        BenchmarkFixture(
            "unguarded_balance_update",
            """diff --git a/src/shop/wallet.py b/src/shop/wallet.py
--- a/src/shop/wallet.py
+++ b/src/shop/wallet.py
@@ -1,3 +1,2 @@
 def deposit(amount):
-    with lock:
-        balance += amount
+    balance += amount
""",
            {"src/shop/wallet.py": "def deposit(amount):\n    balance += amount\n"},
            (ExpectedFinding("src/shop/wallet.py", 2, "race_condition"),),
        ),
        BenchmarkFixture(
            "renamed_response_field",
            """diff --git a/src/shop/api.py b/src/shop/api.py
--- a/src/shop/api.py
+++ b/src/shop/api.py
@@ -1,2 +1,2 @@
 def response(amount):
-    return {"amount": amount}
+    return {"total": amount}
""",
            {"src/shop/api.py": "def response(amount):\n    return {\"total\": amount}\n"},
            (ExpectedFinding("src/shop/api.py", 2, "api_contract"),),
        ),
        BenchmarkFixture(
            "removed_idempotency_guard",
            """diff --git a/src/shop/charges.py b/src/shop/charges.py
--- a/src/shop/charges.py
+++ b/src/shop/charges.py
@@ -1,5 +1,3 @@
 def charge(request_id):
-    if request_id in processed:
-        return False
-    processed.add(request_id)
+    send_charge(request_id)
     return True
""",
            {"src/shop/charges.py": "def charge(request_id):\n    send_charge(request_id)\n    return True\n"},
            (ExpectedFinding("src/shop/charges.py", 2, "idempotency"),),
        ),
        BenchmarkFixture(
            "untested_zero_count_branch",
            """diff --git a/src/shop/average.py b/src/shop/average.py
--- a/src/shop/average.py
+++ b/src/shop/average.py
@@ -1,2 +1,4 @@
 def average(total, count):
+    if count == 0:
+        return 0
     return total / count
""",
            {"src/shop/average.py": "def average(total, count):\n    if count == 0:\n        return 0\n    return total / count\n"},
            (ExpectedFinding("src/shop/average.py", 2, "test_gap"),),
        ),
        BenchmarkFixture(
            "clean_comment_change",
            """diff --git a/src/shop/tax.py b/src/shop/tax.py
--- a/src/shop/tax.py
+++ b/src/shop/tax.py
@@ -1,2 +1,3 @@
 def tax(amount):
+    # Keep the tax calculation local.
     return amount * 0.1
""",
            {"src/shop/tax.py": "def tax(amount):\n    # Keep the tax calculation local.\n    return amount * 0.1\n"},
        ),
        BenchmarkFixture(
            "clean_renamed_local",
            """diff --git a/src/shop/formatting.py b/src/shop/formatting.py
--- a/src/shop/formatting.py
+++ b/src/shop/formatting.py
@@ -1,3 +1,3 @@
 def label(value):
-    result = str(value)
-    return result
+    text = str(value)
+    return text
""",
            {"src/shop/formatting.py": "def label(value):\n    text = str(value)\n    return text\n"},
        ),
    )
