"""Append-only, per-run telemetry. Each request owns a separate journal."""
import json
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def island_for(path: str, repo: str) -> str:
    dirs = path.split("/")[:-1]
    if dirs[:1] == ["src"]:
        dirs = dirs[2:] or dirs[1:]
    return dirs[0] if dirs else repo


class Journal:
    def __init__(self, directory: Path, repo: str):
        self.run_id = str(uuid4())
        self.file = directory / (self.run_id + ".jsonl")
        self.repo = repo
        self.seq = 0
        self.disabled = False

    def emit(self, event: str, status: str, *, path: str = "", agent: str = "", **details):
        if self.disabled:
            return
        self.seq += 1
        record = dict(event=event, status=status, run_id=self.run_id, seq=self.seq,
                      timestamp=datetime.now(timezone.utc).isoformat(), repo=self.repo,
                      island=island_for(path, self.repo), path=path, agent=agent, **details)
        try:
            if self.seq == 1:
                self.file.parent.mkdir(parents=True, exist_ok=True)
            with self.file.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(record) + "\n")
        except (OSError, ValueError, TypeError):
            self.disabled = True
            logging.getLogger(__name__).warning("Disabled unavailable review journal", exc_info=True)


# Provider objects may be shared between simultaneous API requests.
_active: ContextVar[tuple[Journal, str, str] | None] = ContextVar("review_agent", default=None)


@contextmanager
def observe_agent(journal: Journal, name: str, path: str):
    token = _active.set((journal, name, path))
    try:
        yield
    finally:
        _active.reset(token)


def report_retry(reason: str):
    if active := _active.get():
        journal, name, path = active
        journal.emit("stage_changed", "retrying", agent=name, path=path, detail=reason)
