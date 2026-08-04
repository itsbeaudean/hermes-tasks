"""Native Hermes Tasks plugin backend.

The configured Markdown task file remains the sole canonical store; this module
does not introduce a database or synchronization layer.
"""
from __future__ import annotations

import hashlib
import functools
import fcntl
import os
import re
import secrets
import tempfile
import threading
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
SECTIONS = ("Next", "Doing", "Waiting", "Later", "Done")
LEGACY_SECTION_ALIASES = {"Now": "Next"}
TASK_RE = re.compile(r"^- \[(?P<mark>[ xX])\] (?P<title>.+)$")
SECTION_RE = re.compile(r"^## (?P<section>.+?)\s*$")
TASK_ID_RE = re.compile(r"\s*<!--\s*task:(?P<id>[A-Za-z0-9_-]+)\s*-->\s*$")
AREA_RE = re.compile(r"(?:^|\s)#area:(?P<area>[a-z0-9][a-z0-9_-]*)\b", re.IGNORECASE)
COMPLETED_RE = re.compile(r"\s+\(completed (?P<date>\d{4}-\d{2}-\d{2})\)\s*$")
AREAS_LINE_RE = re.compile(r"^Areas:[ \t]*(?P<areas>[^\r\n]*)(?P<cr>\r?)$", re.IGNORECASE | re.MULTILINE)
DOING_LIMIT_RE = re.compile(r"^Doing limit:[ \t]*(?P<limit>\d+)[ \t]*\r?$", re.IGNORECASE | re.MULTILINE)


class ConflictError(RuntimeError):
    """Raised when a mutation targets a stale board revision."""


_MUTATION_LOCK = threading.RLock()


def _serialized_mutation(function):
    @functools.wraps(function)
    def wrapped(*args: Any, **kwargs: Any):
        with _MUTATION_LOCK:
            store = args[0]
            store.path.parent.mkdir(parents=True, exist_ok=True)
            lock_path = store.path.with_name(f".{store.path.name}.lock")
            with lock_path.open("a+b") as lock_handle:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
                try:
                    return function(*args, **kwargs)
                finally:
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

    return wrapped


def _task_id(section: str, raw: str, occurrence: int) -> str:
    value = f"{section}\0{raw}\0{occurrence}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()[:16]


def parse_board(markdown: str) -> dict[str, Any]:
    sections: OrderedDict[str, list[dict[str, Any]]] = OrderedDict(
        (section, []) for section in SECTIONS
    )
    current_section: str | None = None
    occurrences: dict[tuple[str, str], int] = {}

    configured_areas: list[str] = []
    has_area_config = False
    doing_limit = 3
    explicit_ids: set[str] = set()

    for line_number, raw in enumerate(markdown.splitlines(), start=1):
        areas_match = AREAS_LINE_RE.match(raw)
        if areas_match:
            has_area_config = True
            configured_areas = list(dict.fromkeys(
                clean
                for area in areas_match.group("areas").split(",")
                if (clean := _normalize_area(area))
            ))
            continue

        limit_match = DOING_LIMIT_RE.match(raw)
        if limit_match:
            doing_limit = max(1, int(limit_match.group("limit")))
            continue

        section_match = SECTION_RE.match(raw)
        if section_match:
            name = section_match.group("section")
            name = LEGACY_SECTION_ALIASES.get(name, name)
            current_section = name if name in sections else None
            continue

        task_match = TASK_RE.match(raw)
        if current_section is None or task_match is None:
            continue

        key = (current_section, raw)
        occurrence = occurrences.get(key, 0)
        occurrences[key] = occurrence + 1
        raw_title = task_match.group("title")
        id_match = TASK_ID_RE.search(raw_title)
        if id_match and id_match.group("id") in explicit_ids:
            raise ValueError(f"Duplicate task id: {id_match.group('id')}")
        if id_match:
            explicit_ids.add(id_match.group("id"))
        task_id = id_match.group("id") if id_match else _task_id(current_section, raw, occurrence)
        metadata_free = TASK_ID_RE.sub("", raw_title)
        completed_match = COMPLETED_RE.search(metadata_free)
        completed_at = completed_match.group("date") if completed_match else None
        metadata_free = COMPLETED_RE.sub("", metadata_free)
        area_match = AREA_RE.search(metadata_free)
        if area_match:
            area = area_match.group("area").lower()
        elif re.search(r"(?:^|\s)#work\b", metadata_free, re.IGNORECASE):
            area = "work"
        elif re.search(r"(?:^|\s)#life\b", metadata_free, re.IGNORECASE):
            area = "life"
        else:
            area = None
        priority = bool(re.search(r"(?:^|\s)!(?=\s|$)", metadata_free))
        title = AREA_RE.sub("", metadata_free)
        title = re.sub(r"(?:^|\s)#(?:work|life)\b", "", title, flags=re.IGNORECASE)
        title = re.sub(r"(?:^|\s)!(?=\s|$)", "", title)
        title = re.sub(r"\s{2,}", " ", title).strip()
        sections[current_section].append(
            {
                "id": task_id,
                "title": title,
                "done": task_match.group("mark").lower() == "x",
                "priority": priority,
                "area": area,
                "section": current_section,
                "line": line_number,
                "raw": raw,
                "raw_title": raw_title,
                "completed_at": completed_at,
            }
        )

    discovered_areas = [
        task["area"]
        for tasks in sections.values()
        for task in tasks
        if task["area"]
    ]
    default_areas = [] if has_area_config else ["work", "life"]
    areas = list(dict.fromkeys([*default_areas, *configured_areas, *discovered_areas]))
    return {"sections": sections, "areas": areas, "doing_limit": doing_limit}


def board_payload(markdown: str) -> dict[str, Any]:
    board = parse_board(markdown)
    tasks = [task for section in board["sections"].values() for task in section]
    board["counts"] = {
        "open": sum(not task["done"] for task in tasks),
        "priority": sum(not task["done"] and task["priority"] for task in tasks),
        "done": sum(task["done"] for task in tasks),
    }
    board["counts_by_section"] = {
        section: len(section_tasks)
        for section, section_tasks in board["sections"].items()
    }
    doing = [task for task in board["sections"]["Doing"] if not task["done"]]
    next_tasks = [task for task in board["sections"]["Next"] if not task["done"]]

    def first_priority(tasks_in_order: list[dict[str, Any]]) -> dict[str, Any] | None:
        return next(
            (task for task in tasks_in_order if task["priority"]),
            tasks_in_order[0] if tasks_in_order else None,
        )

    focus = first_priority(doing)
    next_task = first_priority(next_tasks)
    board["focus_task_id"] = focus["id"] if focus else None
    board["next_task_id"] = next_task["id"] if next_task else None
    board["wip"] = {
        "count": len(doing),
        "limit": board["doing_limit"],
        "over_limit": len(doing) > board["doing_limit"],
    }
    board["waiting_count"] = len(board["sections"]["Waiting"])
    board["revision"] = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    return board


def _validate_title(title: str) -> str:
    clean = title.strip()
    if not clean or "\n" in clean or "\r" in clean:
        raise ValueError("Task title must be a non-empty single line")
    return clean


def _normalize_area(area: str | None) -> str | None:
    if area is None or not area.strip():
        return None
    clean = re.sub(r"[^a-z0-9_-]+", "-", area.strip().lower()).strip("-_")
    if not clean:
        raise ValueError("Area must contain a letter or number")
    return clean


def _line_ending(markdown: str) -> str:
    return "\r\n" if "\r\n" in markdown else "\n"


def _join_lines(lines: list[str], original: str) -> str:
    newline = _line_ending(original)
    trailing = newline if original.endswith(("\n", "\r")) else ""
    return newline.join(lines) + trailing


def _new_task_id() -> str:
    return f"t_{secrets.token_hex(6)}"


def _format_task(
    title: str,
    *,
    task_id: str,
    area: str | None = None,
    priority: bool = False,
    done: bool = False,
    completed_at: str | None = None,
) -> str:
    parts = [_validate_title(title)]
    if area:
        parts.append(f"#area:{_normalize_area(area)}")
    if priority:
        parts.append("!")
    if completed_at:
        parts.append(f"(completed {completed_at})")
    parts.append(f"<!-- task:{task_id} -->")
    mark = "x" if done else " "
    return f"- [{mark}] {' '.join(parts)}"


def _register_area(markdown: str, area: str | None) -> str:
    clean = _normalize_area(area)
    if not clean:
        return markdown
    match = AREAS_LINE_RE.search(markdown)
    if match:
        areas = [clean_area for item in match.group("areas").split(",") if (clean_area := _normalize_area(item))]
        if clean in areas:
            return markdown
        replacement = f"Areas: {', '.join([*areas, clean])}{match.group('cr')}"
        return markdown[: match.start()] + replacement + markdown[match.end() :]
    updated_match = re.search(r"(?m)^Updated:", markdown)
    insertion = updated_match.start() if updated_match else 0
    prefix = markdown[:insertion]
    newline = _line_ending(markdown)
    separator = "" if prefix.endswith(newline * 2) or not prefix else newline
    return prefix + separator + f"Areas: work, life, {clean}{newline * 2}" + markdown[insertion:]


def _configured_areas(markdown: str) -> list[str]:
    match = AREAS_LINE_RE.search(markdown)
    if match is None:
        return []
    return list(
        dict.fromkeys(
            clean
            for item in match.group("areas").split(",")
            if (clean := _normalize_area(item))
        )
    )


def _set_configured_areas(markdown: str, areas: list[str]) -> str:
    clean_areas = list(dict.fromkeys(_normalize_area(area) for area in areas if _normalize_area(area)))
    replacement = f"Areas: {', '.join(clean_areas)}"
    match = AREAS_LINE_RE.search(markdown)
    if match:
        return markdown[: match.start()] + replacement + match.group("cr") + markdown[match.end() :]
    updated_match = re.search(r"(?m)^Updated:", markdown)
    insertion = updated_match.start() if updated_match else 0
    prefix = markdown[:insertion]
    newline = _line_ending(markdown)
    separator = "" if prefix.endswith(newline * 2) or not prefix else newline
    return prefix + separator + replacement + newline * 2 + markdown[insertion:]


def _replace_task_area(markdown: str, old_area: str, new_area: str | None) -> str:
    lines = markdown.splitlines()
    managed_lines = {
        task["line"] - 1
        for tasks in parse_board(markdown)["sections"].values()
        for task in tasks
        if task["area"] == old_area
    }
    for index in managed_lines:
        line = lines[index]

        def replacement(match: re.Match[str]) -> str:
            if _normalize_area(match.group("area")) != old_area:
                return match.group(0)
            if new_area is None:
                return ""
            prefix = " " if match.group(0)[0].isspace() else ""
            return f"{prefix}#area:{new_area}"

        updated_line = AREA_RE.sub(replacement, line)
        if updated_line == line and old_area in {"work", "life"}:
            legacy_re = re.compile(rf"(?:^|\s)#{re.escape(old_area)}\b", re.IGNORECASE)

            def replace_legacy(match: re.Match[str]) -> str:
                if new_area is None:
                    return ""
                prefix = " " if match.group(0)[0].isspace() else ""
                return f"{prefix}#area:{new_area}"

            updated_line = legacy_re.sub(replace_legacy, line, count=1)
        lines[index] = updated_line
    return _join_lines(lines, markdown)


def _update_date(markdown: str) -> str:
    today = date.today().isoformat()
    updated, count = re.subn(
        r"(?m)^Updated: \d{4}-\d{2}-\d{2}(?P<cr>\r?)$",
        lambda match: f"Updated: {today}{match.group('cr')}",
        markdown,
        count=1,
    )
    return updated if count else markdown


def _insert_raw_task(
    markdown: str,
    raw_task: str,
    section: str,
    position: int | None = None,
) -> str:
    if section not in SECTIONS:
        raise ValueError(f"Unknown task section: {section}")

    lines = markdown.splitlines()
    heading_index = next(
        (
            index
            for index, line in enumerate(lines)
            if (match := SECTION_RE.match(line))
            and LEGACY_SECTION_ALIASES.get(match.group("section"), match.group("section")) == section
        ),
        None,
    )
    if heading_index is None:
        raise ValueError(f"Missing task section: {section}")

    boundary = len(lines)
    for index in range(heading_index + 1, len(lines)):
        if lines[index].startswith("## "):
            boundary = index
            break

    task_indices = [
        index
        for index in range(heading_index + 1, boundary)
        if TASK_RE.match(lines[index])
    ]
    if position is not None:
        if position < 0:
            raise ValueError("Task position cannot be negative")
        insertion = task_indices[position] if position < len(task_indices) else boundary
    else:
        insertion = boundary
    while insertion > heading_index + 1 and not lines[insertion - 1].strip():
        insertion -= 1
    lines.insert(insertion, raw_task)
    return _join_lines(lines, markdown)


def _insert_task(
    markdown: str,
    title: str,
    section: str,
    *,
    area: str | None = None,
    priority: bool = False,
) -> str:
    task_id = _new_task_id()
    is_done = section == "Done"
    raw = _format_task(
        title,
        task_id=task_id,
        area=area,
        priority=priority,
        done=is_done,
        completed_at=date.today().isoformat() if is_done else None,
    )
    return _insert_raw_task(_register_area(markdown, area), raw, section)


def _repair_duplicate_ids(markdown: str) -> str:
    lines = markdown.splitlines()
    seen: set[str] = set()
    for index, line in enumerate(lines):
        task_match = TASK_RE.match(line)
        if task_match is None:
            continue
        id_match = TASK_ID_RE.search(task_match.group("title"))
        if id_match is None:
            continue
        task_id = id_match.group("id")
        if task_id in seen:
            lines[index] = TASK_ID_RE.sub(f" <!-- task:{_new_task_id()} -->", line)
        else:
            seen.add(task_id)
    return _join_lines(lines, markdown)


def _find_task(markdown: str, task_id: str) -> dict[str, Any]:
    board = parse_board(markdown)
    for tasks in board["sections"].values():
        for task in tasks:
            if task["id"] == task_id:
                return task
    raise KeyError("Task no longer exists; refresh and try again")


def _assert_revision(markdown: str, revision: str | None) -> None:
    if revision is None:
        return
    current = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    if revision != current:
        raise ConflictError("Tasks changed elsewhere; refresh and try again")


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

    def _read(self) -> str:
        with self.path.open("r", encoding="utf-8", newline="") as handle:
            return handle.read()

    def read(self) -> dict[str, Any]:
        return board_payload(self._read())

    @_serialized_mutation
    def create_area(self, area: str, revision: str | None = None) -> dict[str, Any]:
        markdown = self._read()
        _assert_revision(markdown, revision)
        clean = _normalize_area(area)
        if clean is None:
            raise ValueError("Area must contain a letter or number")
        if clean in parse_board(markdown)["areas"]:
            raise ValueError("An area with that name already exists")
        updated = _update_date(_register_area(markdown, clean))
        if updated != markdown:
            self._commit(markdown, updated)
        return board_payload(updated)

    @_serialized_mutation
    def rename_area(
        self,
        area: str,
        new_area: str,
        revision: str | None = None,
    ) -> dict[str, Any]:
        markdown = self._read()
        _assert_revision(markdown, revision)
        old_clean = _normalize_area(area)
        new_clean = _normalize_area(new_area)
        if old_clean is None or new_clean is None:
            raise ValueError("Area names must contain a letter or number")
        board = parse_board(markdown)
        if old_clean not in board["areas"]:
            raise KeyError("Area no longer exists; refresh and try again")
        if new_clean != old_clean and new_clean in board["areas"]:
            raise ValueError("An area with that name already exists")
        if new_clean == old_clean:
            return board_payload(markdown)

        configured = _configured_areas(markdown)
        configured = [new_clean if item == old_clean else item for item in configured]
        if old_clean not in _configured_areas(markdown):
            configured.append(new_clean)
        updated = _set_configured_areas(markdown, configured)
        updated = _replace_task_area(updated, old_clean, new_clean)
        updated = _update_date(updated)
        self._commit(markdown, updated)
        return board_payload(updated)

    @_serialized_mutation
    def remove_area(
        self,
        area: str,
        *,
        replacement: str | None = None,
        revision: str | None = None,
    ) -> dict[str, Any]:
        markdown = self._read()
        _assert_revision(markdown, revision)
        clean = _normalize_area(area)
        replacement_clean = _normalize_area(replacement)
        if clean is None:
            raise ValueError("Area must contain a letter or number")
        board = parse_board(markdown)
        if clean not in board["areas"]:
            raise KeyError("Area no longer exists; refresh and try again")
        if replacement_clean == clean:
            raise ValueError("Replacement area must be different")
        if replacement_clean and replacement_clean not in board["areas"]:
            raise ValueError("Replacement area does not exist")

        configured = [item for item in _configured_areas(markdown) if item != clean]
        if replacement_clean and replacement_clean not in configured:
            configured.append(replacement_clean)
        updated = _set_configured_areas(markdown, configured)
        updated = _replace_task_area(updated, clean, replacement_clean)
        updated = _update_date(updated)
        self._commit(markdown, updated)
        return board_payload(updated)

    def _commit(self, original: str, updated: str) -> None:
        if self._read() != original:
            raise ConflictError("Tasks changed elsewhere; refresh and try again")
        self._write(updated)

    @_serialized_mutation
    def migrate(self, revision: str | None = None) -> dict[str, Any]:
        original = self._read()
        _assert_revision(original, revision)
        updated = re.sub(r"(?m)^## Now[ \t]*(?P<cr>\r?)$", lambda match: f"## Next{match.group('cr')}", original, count=1)
        updated = _repair_duplicate_ids(updated)

        if not AREAS_LINE_RE.search(updated):
            match = re.search(r"(?m)^Updated:", updated)
            insertion = match.start() if match else 0
            newline = _line_ending(updated)
            metadata = f"Areas: work, life{newline}Doing limit: 3{newline * 2}"
            updated = updated[:insertion] + metadata + updated[insertion:]
        elif not DOING_LIMIT_RE.search(updated):
            area_match = AREAS_LINE_RE.search(updated)
            assert area_match is not None
            insertion = area_match.end()
            if updated[insertion : insertion + 1] == "\n":
                insertion += 1
            newline = _line_ending(updated)
            updated = updated[:insertion] + f"Doing limit: 3{newline}" + updated[insertion:]

        if not re.search(r"(?m)^## Doing[ \t]*\r?$", updated):
            waiting_match = re.search(r"(?m)^## Waiting[ \t]*\r?$", updated)
            if waiting_match:
                newline = _line_ending(updated)
                updated = updated[: waiting_match.start()] + f"## Doing{newline * 2}" + updated[waiting_match.start() :]
            else:
                raise ValueError("Missing task section: Waiting")

        parsed = parse_board(updated)
        lines = updated.splitlines()
        for tasks in parsed["sections"].values():
            for task in tasks:
                if TASK_ID_RE.search(task["raw_title"]):
                    continue
                lines[task["line"] - 1] = _format_task(
                    task["title"],
                    task_id=_new_task_id(),
                    area=task["area"],
                    priority=task["priority"],
                    done=task["done"],
                    completed_at=task["completed_at"],
                )
        updated = _join_lines(lines, updated)

        parsed = parse_board(updated)
        misplaced_done = [
            task
            for section, tasks in parsed["sections"].items()
            if section != "Done"
            for task in tasks
            if task["done"]
        ]
        if misplaced_done:
            lines = updated.splitlines()
            for task in sorted(misplaced_done, key=lambda item: item["line"], reverse=True):
                del lines[task["line"] - 1]
            updated = _join_lines(lines, updated)
            for task in misplaced_done:
                updated = _insert_raw_task(updated, task["raw"], "Done")

        updated = _update_date(updated)
        if updated != original:
            self._commit(original, updated)
        return board_payload(updated)

    @_serialized_mutation
    def add(
        self,
        title: str,
        section: str = "Next",
        area: str | None = None,
        priority: bool = False,
        revision: str | None = None,
    ) -> dict[str, Any]:
        markdown = self._read()
        _assert_revision(markdown, revision)
        section = LEGACY_SECTION_ALIASES.get(section, section)
        updated = _insert_task(
            markdown,
            _validate_title(title),
            section,
            area=area,
            priority=priority,
        )
        updated = _update_date(updated)
        self._commit(markdown, updated)
        return board_payload(updated)

    @_serialized_mutation
    def update(
        self,
        task_id: str,
        *,
        title: str | None = None,
        section: str | None = None,
        area: str | None = None,
        priority: bool | None = None,
        position: int | None = None,
        revision: str | None = None,
    ) -> dict[str, Any]:
        markdown = self._read()
        _assert_revision(markdown, revision)
        task = _find_task(markdown, task_id)
        target_section = LEGACY_SECTION_ALIASES.get(section or task["section"], section or task["section"])
        if target_section not in SECTIONS:
            raise ValueError(f"Unknown task section: {target_section}")

        target_title = task["title"] if title is None else _validate_title(title)
        target_area = task["area"] if area is None else _normalize_area(area)
        target_priority = task["priority"] if priority is None else bool(priority)
        source_tasks = parse_board(markdown)["sections"][task["section"]]
        source_position = next(
            index for index, source_task in enumerate(source_tasks) if source_task["id"] == task_id
        )
        if position is None and target_section == task["section"]:
            position = source_position
        is_done = target_section == "Done"
        completed_at = task["completed_at"] if is_done else None
        if is_done and not completed_at:
            completed_at = date.today().isoformat()

        lines = markdown.splitlines()
        del lines[task["line"] - 1]
        updated = _join_lines(lines, markdown)
        updated = _register_area(updated, target_area)
        updated = _insert_raw_task(
            updated,
            _format_task(
                target_title,
                task_id=task_id,
                area=target_area,
                priority=target_priority,
                done=is_done,
                completed_at=completed_at,
            ),
            target_section,
            position=position,
        )
        updated = _update_date(updated)
        self._commit(markdown, updated)
        return board_payload(updated)

    def complete(
        self,
        task_id: str,
        done: bool,
        revision: str | None = None,
    ) -> dict[str, Any]:
        return self.update(
            task_id,
            section="Done" if done else "Next",
            revision=revision,
        )

    @_serialized_mutation
    def delete(self, task_id: str, revision: str | None = None) -> dict[str, Any]:
        markdown = self._read()
        _assert_revision(markdown, revision)
        task = _find_task(markdown, task_id)
        lines = markdown.splitlines()
        del lines[task["line"] - 1]
        updated = _join_lines(lines, markdown)
        updated = _update_date(updated)
        self._commit(markdown, updated)
        return board_payload(updated)


def _configured_store() -> TaskStore:
    path = os.environ.get("HERMES_TASKS_PATH", str(Path.home() / "tasks.md"))
    return TaskStore(path)


def _required_revision(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("A non-empty revision is required")
    return value


def _required_name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("A non-empty area name is required")
    return value


def _optional_boolean(body: dict[str, Any], key: str, default: bool | None) -> bool | None:
    if key not in body:
        return default
    value = body[key]
    if type(value) is not bool:
        raise ValueError(f"{key} must be a boolean")
    return value


@router.get("/board")
def get_board() -> dict[str, Any]:
    try:
        return _configured_store().read()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=f"Task file is invalid: {exc}") from exc
    except OSError as exc:
        raise HTTPException(status_code=503, detail=f"Task file unavailable: {exc}") from exc


@router.post("/migrate")
def migrate_board(body: dict[str, Any]) -> dict[str, Any]:
    try:
        return _configured_store().migrate(
            revision=_required_revision(body.get("revision")),
        )
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/areas")
def create_area(body: dict[str, Any]) -> dict[str, Any]:
    try:
        return _configured_store().create_area(
            _required_name(body.get("name")),
            revision=_required_revision(body.get("revision")),
        )
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/areas/{area}")
def rename_area(area: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        return _configured_store().rename_area(
            area,
            _required_name(body.get("name")),
            revision=_required_revision(body.get("revision")),
        )
    except (ConflictError, KeyError) as exc:
        detail = str(exc.args[0]) if isinstance(exc, KeyError) else str(exc)
        raise HTTPException(status_code=409, detail=detail) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/areas/{area}")
def delete_area(
    area: str,
    revision: str | None = None,
    replacement: str | None = None,
) -> dict[str, Any]:
    try:
        return _configured_store().remove_area(
            area,
            replacement=replacement,
            revision=_required_revision(revision),
        )
    except (ConflictError, KeyError) as exc:
        detail = str(exc.args[0]) if isinstance(exc, KeyError) else str(exc)
        raise HTTPException(status_code=409, detail=detail) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/tasks")
def add_task(body: dict[str, Any]) -> dict[str, Any]:
    try:
        return _configured_store().add(
            str(body.get("title", "")),
            str(body.get("section", "Next")),
            area=None if body.get("area") is None else str(body.get("area")),
            priority=bool(_optional_boolean(body, "priority", False)),
            revision=_required_revision(body.get("revision")),
        )
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/tasks/{task_id}")
def update_task(task_id: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        return _configured_store().update(
            task_id,
            title=None if "title" not in body else str(body.get("title", "")),
            section=None if "section" not in body else str(body.get("section", "")),
            area=None if "area" not in body else str(body.get("area") or ""),
            priority=_optional_boolean(body, "priority", None),
            position=None if "position" not in body else int(body.get("position")),
            revision=_required_revision(body.get("revision")),
        )
    except (ConflictError, KeyError) as exc:
        detail = str(exc.args[0]) if isinstance(exc, KeyError) else str(exc)
        raise HTTPException(status_code=409, detail=detail) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/tasks/{task_id}/complete")
def complete_task(task_id: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        return _configured_store().complete(
            task_id,
            bool(_optional_boolean(body, "done", True)),
            revision=_required_revision(body.get("revision")),
        )
    except (ConflictError, KeyError) as exc:
        detail = str(exc.args[0]) if isinstance(exc, KeyError) else str(exc)
        raise HTTPException(status_code=409, detail=detail) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/tasks/{task_id}")
def delete_task(task_id: str, revision: str | None = None) -> dict[str, Any]:
    try:
        return _configured_store().delete(task_id, revision=_required_revision(revision))
    except (ConflictError, KeyError) as exc:
        detail = str(exc.args[0]) if isinstance(exc, KeyError) else str(exc)
        raise HTTPException(status_code=409, detail=detail) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
