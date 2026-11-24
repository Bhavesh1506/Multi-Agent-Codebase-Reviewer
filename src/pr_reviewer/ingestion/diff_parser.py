"""Parse unified git diffs without model calls or repository access."""

import re
import shlex

from pr_reviewer.schemas import DiffHunk, DiffLine, FileDiff, LineKind, ParsedDiff


_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")


def _path(value: str) -> str | None:
    value = value.split("\t", 1)[0]
    if value == "/dev/null":
        return None
    if value.startswith(('"', "'")):
        try:
            value = shlex.split(value)[0]
        except (ValueError, IndexError) as exc:
            raise ValueError(f"invalid diff path: {value}") from exc
    return value[2:] if value.startswith(("a/", "b/")) else value


def parse_diff(text: str) -> ParsedDiff:
    """Return changed files, hunks, and numbered lines from a unified diff.

    Raises ValueError for malformed hunk headers or line counts. Binary and
    metadata-only changes are retained as files with no hunks.
    """
    files: list[FileDiff] = []
    current: FileDiff | None = None
    hunk: DiffHunk | None = None
    old_line = new_line = 0
    old_seen = new_seen = 0

    def finish_hunk() -> None:
        if hunk is not None and (old_seen != hunk.old_count or new_seen != hunk.new_count):
            raise ValueError(
                f"hunk line count mismatch in {current.path if current else '<unknown>'}: "
                f"expected {hunk.old_count}/{hunk.new_count}, got {old_seen}/{new_seen}"
            )

    for raw in text.splitlines():
        if raw.startswith("diff --git "):
            finish_hunk()
            try:
                paths = shlex.split(raw[len("diff --git "):])
            except ValueError as exc:
                raise ValueError(f"invalid git diff header: {raw}") from exc
            if len(paths) != 2:
                raise ValueError(f"invalid git diff header: {raw}")
            current = FileDiff(old_path=_path(paths[0]), new_path=_path(paths[1]))
            files.append(current)
            hunk = None
            continue

        if raw.startswith("--- ") and hunk is None:
            if current is None:
                current = FileDiff()
                files.append(current)
            current.old_path = _path(raw[4:])
            continue
        if raw.startswith("+++ ") and hunk is None:
            if current is None:
                raise ValueError("new file marker without old file marker")
            current.new_path = _path(raw[4:])
            continue
        if raw.startswith("@@ "):
            if current is None:
                raise ValueError("hunk without file header")
            finish_hunk()
            match = _HUNK.fullmatch(raw)
            if match is None:
                raise ValueError(f"invalid hunk header: {raw}")
            old_start, old_count, new_start, new_count, section = match.groups()
            hunk = DiffHunk(
                old_start=int(old_start), old_count=int(old_count or 1),
                new_start=int(new_start), new_count=int(new_count or 1),
                section=section.strip(),
            )
            current.hunks.append(hunk)
            old_line, new_line = hunk.old_start, hunk.new_start
            old_seen = new_seen = 0
            continue

        if hunk is not None:
            if raw == r"\ No newline at end of file":
                continue
            if raw.startswith(" "):
                hunk.lines.append(DiffLine(kind=LineKind.CONTEXT, content=raw[1:], old_line=old_line, new_line=new_line))
                old_line += 1
                new_line += 1
                old_seen += 1
                new_seen += 1
            elif raw.startswith("+"):
                hunk.lines.append(DiffLine(kind=LineKind.ADDED, content=raw[1:], new_line=new_line))
                new_line += 1
                new_seen += 1
            elif raw.startswith("-"):
                hunk.lines.append(DiffLine(kind=LineKind.REMOVED, content=raw[1:], old_line=old_line))
                old_line += 1
                old_seen += 1
            else:
                raise ValueError(f"invalid hunk line: {raw}")
            continue

        if current is not None:
            if raw.startswith(("Binary files ", "GIT binary patch")):
                current.is_binary = True
            elif raw.startswith("rename from "):
                current.old_path = raw[len("rename from "):]
                current.is_rename = True
            elif raw.startswith("rename to "):
                current.new_path = raw[len("rename to "):]
                current.is_rename = True
    finish_hunk()
    return ParsedDiff(files=files)
