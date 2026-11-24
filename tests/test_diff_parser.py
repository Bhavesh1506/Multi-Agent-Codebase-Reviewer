import pytest

from pr_reviewer.ingestion.diff_parser import parse_diff
from pr_reviewer.schemas import LineKind


def test_multiple_files_and_hunks_with_line_numbers():
    diff = """diff --git a/app.py b/app.py
index abc..def 100644
--- a/app.py
+++ b/app.py
@@ -2,3 +2,4 @@ def run():
 keep
-old
+new
+extra
 end
@@ -10 +11 @@
-before
+after
diff --git a/other.py b/other.py
--- a/other.py
+++ b/other.py
@@ -1 +1 @@
-x
+y
"""
    parsed = parse_diff(diff)
    assert [file.path for file in parsed.files] == ["app.py", "other.py"]
    first = parsed.files[0]
    assert len(first.hunks) == 2
    assert first.hunks[0].section == "def run():"
    assert [(line.kind, line.old_line, line.new_line) for line in first.hunks[0].lines] == [
        (LineKind.CONTEXT, 2, 2),
        (LineKind.REMOVED, 3, None),
        (LineKind.ADDED, None, 3),
        (LineKind.ADDED, None, 4),
        (LineKind.CONTEXT, 4, 5),
    ]
    assert [line.content for line in first.added_lines] == ["new", "extra", "after"]


def test_added_deleted_rename_and_binary_files():
    diff = """diff --git a/new.py b/new.py
new file mode 100644
--- /dev/null
+++ b/new.py
@@ -0,0 +1,2 @@
+one
+two
diff --git a/old.py b/old.py
deleted file mode 100644
--- a/old.py
+++ /dev/null
@@ -1 +0,0 @@
-gone
diff --git a/old_name.py b/new_name.py
similarity index 100%
rename from old_name.py
rename to new_name.py
diff --git a/logo.png b/logo.png
Binary files a/logo.png and b/logo.png differ
"""
    new, deleted, renamed, binary = parse_diff(diff).files
    assert (new.old_path, new.new_path) == (None, "new.py")
    assert (deleted.old_path, deleted.new_path) == ("old.py", None)
    assert (renamed.old_path, renamed.new_path, renamed.is_rename) == ("old_name.py", "new_name.py", True)
    assert binary.is_binary and binary.hunks == []


def test_plain_unified_diff_and_no_newline_marker():
    diff = """--- a/file.txt
+++ b/file.txt
@@ -1 +1 @@
-old
\\ No newline at end of file
+new
\\ No newline at end of file
"""
    result = parse_diff(diff)
    assert result.files[0].path == "file.txt"
    assert len(result.files[0].hunks[0].lines) == 2


@pytest.mark.parametrize("diff", [
    "diff --git a/x b/x\n@@ -1,2 +1,2 @@\n-a\n+b\n",
    "diff --git a/x b/x\n@@ malformed @@\n",
    "@@ -1 +1 @@\n-x\n+y\n",
])
def test_malformed_diff_rejected(diff):
    with pytest.raises(ValueError):
        parse_diff(diff)


def test_empty_diff():
    assert parse_diff("").files == []
