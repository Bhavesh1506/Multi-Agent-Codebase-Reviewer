"""Read-only HTTP access to complete records in a configured journal directory."""
import json
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles


def mount_visualizer(app: FastAPI, directory: Path | None):
    @app.get("/islands-data/runs")
    async def runs() -> list[str]:
        if directory is None or not directory.is_dir():
            return []
        files = []
        for file in directory.glob("*.jsonl"):
            try:
                if str(UUID(file.stem)) == file.stem and not file.is_symlink():
                    files.append((file.stat().st_mtime_ns, file.stem))
            except (ValueError, FileNotFoundError):
                continue
        return [run for _, run in sorted(files, reverse=True)]

    @app.get("/islands-data/runs/{run}")
    async def events(run: UUID, cursor: int = Query(default=0, ge=0)):
        file = directory / f"{run}.jsonl" if directory else None
        if not file or file.is_symlink() or not file.is_file():
            raise HTTPException(404, "Unknown run")
        records = []
        with file.open("rb") as stream:
            if cursor > file.stat().st_size:
                raise HTTPException(400, "Invalid cursor")
            stream.seek(cursor)
            for _ in range(128):
                line = stream.readline()
                if not line.endswith(b"\n"):
                    break
                try:
                    records.append(json.loads(line))
                except ValueError as exc:
                    raise HTTPException(422, "Invalid journal record or cursor") from exc
                cursor = stream.tell()
        return {"events": records, "cursor": cursor}

    app.mount("/islands", StaticFiles(directory=Path(__file__).with_name("islands"), html=True),
              name="islands")
