"""Hermes Tasks plugin backend.

The task file is plain Markdown. Set ``HERMES_TASKS_PATH`` to use an existing
file; otherwise the plugin reads and writes ``~/tasks.md``.
"""
from __future__ import annotations

import hashlib
import os
import re
import tempfile
from collections import OrderedDict
from datetime import date
from pathlib import Path
from typing import Any

try:
    from fastapi import APIRouter, HTTPException
except Exception:  # pragma: no cover - permits dependency-free unit tests
    class APIRouter:  # type: ignore[no-redef]
        def get(self, *_args: Any, **_kwargs: Any):
            return lambda function: function

        def post(self, *_args: Any, **_kwargs: Any):
            return lambda function: function

        def patch(self, *_args: Any, **_kwargs: Any):
            return lambda function: function

        def delete(self, *_args: Any, **_kwargs: Any):
            return lambda function: function

    class HTTPException(Exception):  # type: ignore[no-redef]
        def __init__(self, status_code: int, detail: str):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail


router = APIRouter()
SECTIONS = ("Now", "Waiting", "Later", "Done")
TASK_RE = re.compile(r"^- \[(?P<mark>[ xX])\] (?P<title>.+)$")
SECTION_RE = re.compile(r"^## (?P<section>.+?)\s*$")


def _task_id(section: str, raw: str, occurrence: int) -> str:
    value = f"{section}\0{raw}\0{occurrence}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()[:16]


def parse_board(markdown: str) -> dict[str, Any]:
    sections: OrderedDict[str, list[dict[str, Any]]] = OrderedDict(
        (section, []) for section in SECTIONS
    )
    current_section: str | None = None
    occurrences: dict[tuple[str, str], int] = {}

    for line_number, raw in enumerate(markdown.splitlines(), start=1):
        section_match = SECTION_RE.match(raw)
        if section_match:
            name = section_match.group("section")
            current_section = name if name in sections else None
            continue

        task_match = TASK_RE.match(raw)
        if current_section is None or task_match is None:
            continue

        key = (current_section, raw)
        occurrence = occurrences.get(key, 0)
        occurrences[key] = occurrence + 1
        title = task_match.group("title")
        sections[current_section].append(
            {
                "id": _task_id(current_section, raw, occurrence),
                "title": title,
                "done": task_match.group("mark").lower() == "x",
                "priority": title.rstrip().endswith("!"),
                "area": "work" if "#work" in title else "life" if "#life" in title else None,
                "section": current_section,
                "line": line_number,
                "raw": raw,
            }
        )

    return {"sections": sections}


def board_payload(markdown: str) -> dict[str, Any]:
    board = parse_board(markdown)
    tasks = [task for section in board["sections"].values() for task in section]
    board["counts"] = {
        "open": sum(not task["done"] for task in tasks),
        "priority": sum(not task["done"] and task["priority"] for task in tasks),
        "done": sum(task["done"] for task in tasks),
    }
    board["revision"] = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    return board


def _validate_title(title: str) -> str:
    clean = title.strip()
    if not clean or "\n" in clean or "\r" in clean:
        raise ValueError("Task title must be a non-empty single line")
    return clean


def _update_date(markdown: str) -> str:
    today = date.today().isoformat()
    updated, count = re.subn(
        r"(?m)^Updated: \d{4}-\d{2}-\d{2}$",
        f"Updated: {today}",
        markdown,
        count=1,
    )
    return updated if count else markdown


def _insert_raw_task(markdown: str, raw_task: str, section: str) -> str:
    if section not in SECTIONS:
        raise ValueError(f"Unknown task section: {section}")

    lines = markdown.splitlines()
    heading = f"## {section}"
    try:
        heading_index = lines.index(heading)
    except ValueError as exc:
        raise ValueError(f"Missing task section: {section}") from exc

    boundary = len(lines)
    for index in range(heading_index + 1, len(lines)):
        if lines[index].startswith("## "):
            boundary = index
            break

    insertion = boundary
    while insertion > heading_index + 1 and not lines[insertion - 1].strip():
        insertion -= 1
    lines.insert(insertion, raw_task)
    return "\n".join(lines) + ("\n" if markdown.endswith("\n") else "")


def _insert_task(markdown: str, title: str, section: str) -> str:
    return _insert_raw_task(markdown, f"- [ ] {title}", section)


def _find_task(markdown: str, task_id: str) -> dict[str, Any]:
    board = parse_board(markdown)
    for tasks in board["sections"].values():
        for task in tasks:
            if task["id"] == task_id:
                return task
    raise KeyError("Task no longer exists; refresh and try again")


class TaskStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)

    def _write(self, markdown: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                handle.write(markdown)
                handle.flush()
                os.fsync(handle.fileno())
            if self.path.exists():
                os.chmod(temporary_name, self.path.stat().st_mode)
            os.replace(temporary_name, self.path)
        finally:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass

    def read(self) -> dict[str, Any]:
        return board_payload(self.path.read_text(encoding="utf-8"))

    def add(self, title: str, section: str = "Now") -> dict[str, Any]:
        markdown = self.path.read_text(encoding="utf-8")
        updated = _insert_task(markdown, _validate_title(title), section)
        updated = _update_date(updated)
        self._write(updated)
        return board_payload(updated)

    def complete(self, task_id: str, done: bool) -> dict[str, Any]:
        markdown = self.path.read_text(encoding="utf-8")
        task = _find_task(markdown, task_id)
        lines = markdown.splitlines()
        del lines[task["line"] - 1]
        updated = "\n".join(lines) + ("\n" if markdown.endswith("\n") else "")

        title = re.sub(r" \(completed \d{4}-\d{2}-\d{2}\)$", "", task["title"])
        if done:
            title = f"{title} (completed {date.today().isoformat()})"
            raw = f"- [x] {title}"
            section = "Done"
        else:
            raw = f"- [ ] {title}"
            section = "Now"

        updated = _insert_raw_task(updated, raw, section)
        updated = _update_date(updated)
        self._write(updated)
        return board_payload(updated)


def _configured_store() -> TaskStore:
    path = os.environ.get("HERMES_TASKS_PATH", str(Path.home() / "tasks.md"))
    return TaskStore(path)


@router.get("/board")
def get_board() -> dict[str, Any]:
    try:
        return _configured_store().read()
    except OSError as exc:
        raise HTTPException(status_code=503, detail=f"Task file unavailable: {exc}") from exc


@router.post("/tasks")
def add_task(body: dict[str, Any]) -> dict[str, Any]:
    try:
        return _configured_store().add(
            str(body.get("title", "")),
            str(body.get("section", "Now")),
        )
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/tasks/{task_id}/complete")
def complete_task(task_id: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        return _configured_store().complete(task_id, bool(body.get("done", True)))
    except KeyError as exc:
        raise HTTPException(status_code=409, detail=str(exc.args[0])) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
