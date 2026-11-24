"""Strict contracts shared by ingestion and later review stages."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LineKind(StrEnum):
    CONTEXT = "context"
    ADDED = "added"
    REMOVED = "removed"


class DiffLine(StrictModel):
    kind: LineKind
    content: str
    old_line: int | None = Field(default=None, ge=1)
    new_line: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def check_line_numbers(self) -> "DiffLine":
        if self.kind != LineKind.ADDED and self.old_line is None:
            raise ValueError("context and removed lines require old_line")
        if self.kind != LineKind.REMOVED and self.new_line is None:
            raise ValueError("context and added lines require new_line")
        if self.kind == LineKind.ADDED and self.old_line is not None:
            raise ValueError("added lines cannot have old_line")
        if self.kind == LineKind.REMOVED and self.new_line is not None:
            raise ValueError("removed lines cannot have new_line")
        return self


class DiffHunk(StrictModel):
    old_start: int = Field(ge=0)
    old_count: int = Field(ge=0)
    new_start: int = Field(ge=0)
    new_count: int = Field(ge=0)
    section: str = ""
    lines: list[DiffLine] = Field(default_factory=list)


class FileDiff(StrictModel):
    old_path: str | None = None
    new_path: str | None = None
    hunks: list[DiffHunk] = Field(default_factory=list)
    is_binary: bool = False
    is_rename: bool = False

    @property
    def path(self) -> str:
        return self.new_path or self.old_path or ""

    @property
    def added_lines(self) -> list[DiffLine]:
        return [line for hunk in self.hunks for line in hunk.lines if line.kind == LineKind.ADDED]

    @property
    def removed_lines(self) -> list[DiffLine]:
        return [line for hunk in self.hunks for line in hunk.lines if line.kind == LineKind.REMOVED]


class ParsedDiff(StrictModel):
    files: list[FileDiff] = Field(default_factory=list)


class Finding(StrictModel):
    agent: str
    path: str
    line: int | None = Field(default=None, ge=1)
    title: str
    explanation: str
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)


class ReviewVerdict(StrictModel):
    findings: list[Finding] = Field(default_factory=list)
    summary: str
    changed_files: list[str] = Field(default_factory=list)
