"""Reading an omp session directory: usage, cost, and step counts.

Stdlib only, and importable without Harbor installed: these numbers are the
trial's token and cost evidence, and any harness must be able to read them.

The layout this reads is what a real omp run writes (spike S2, measured): one
or more ``*.jsonl`` session files, each event optionally carrying a
``message.usage`` record — one per model turn. The trial points omp at the
directory with ``--session-dir``.

This module is also the reader the ATIF trajectory converter will use (the
converter is a follow-up; see ``docs/architecture.md``). A malformed line, an
unreadable file, or a non-numeric usage field is counted rather than raised:
the totals must stay readable, and the counts are how a caller notices that the
totals are low.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SessionUsage:
    """A session directory's totals, summed over its JSONL files."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    steps: int = 0
    files_read: int = 0
    skipped_files: int = 0
    skipped_lines: int = 0
    skipped_values: int = 0

    @property
    def total_input_tokens(self) -> int:
        """Input tokens including cached tokens (``AgentContext`` semantics)."""

        return self.input_tokens + self.cache_read_tokens + self.cache_write_tokens


def session_files(session_dir: Path) -> list[Path]:
    """The session JSONL files in ``session_dir``, in stable order."""

    if not session_dir.is_dir():
        return []
    return sorted(session_dir.glob("*.jsonl"))


def iter_session_events(session_dir: Path) -> Iterator[dict[str, Any]]:
    """Yield every JSON object event in the directory, in file order.

    Undecodable lines and unreadable files are skipped, so a caller that must
    know about them uses ``sum_session_usage`` (which counts them) or reads the
    files itself. Yields nothing when the directory holds no JSONL.
    """

    for session_file in session_files(session_dir):
        try:
            text = session_file.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        for line in text.splitlines():
            event = _parse_event(line)
            if event is not None:
                yield event


def sum_session_usage(session_dir: Path) -> SessionUsage | None:
    """Sum the usage records of a session directory.

    Returns ``None`` when the directory holds no JSONL at all — the run never
    started omp, or wrote its session somewhere else. A caller must treat that
    as *absent*, not as zero: an unread session and a free session are
    different facts.
    """

    files = session_files(session_dir)
    if not files:
        return None

    cost = 0.0
    steps = files_read = skipped_files = skipped_lines = skipped_values = 0
    totals = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
    for session_file in files:
        try:
            text = session_file.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            skipped_files += 1
            continue
        files_read += 1
        for line in text.splitlines():
            if not line.strip():
                continue
            event = _parse_event(line)
            if event is None:
                skipped_lines += 1
                continue
            usage = _usage_of(event)
            if usage is None:
                continue
            for field, attribute in (
                ("input", "input"),
                ("output", "output"),
                ("cacheRead", "cache_read"),
                ("cacheWrite", "cache_write"),
            ):
                raw = usage.get(field)
                value = _number(raw)
                if value is None:
                    if raw is not None:
                        skipped_values += 1
                    value = 0.0
                totals[attribute] += int(value)
            cost_field = usage.get("cost")
            if isinstance(cost_field, dict):
                raw_total = cost_field.get("total")
                total = _number(raw_total)
                if total is None:
                    if raw_total is not None:
                        skipped_values += 1
                else:
                    cost += total
            steps += 1

    return SessionUsage(
        input_tokens=totals["input"],
        output_tokens=totals["output"],
        cache_read_tokens=totals["cache_read"],
        cache_write_tokens=totals["cache_write"],
        cost_usd=cost,
        steps=steps,
        files_read=files_read,
        skipped_files=skipped_files,
        skipped_lines=skipped_lines,
        skipped_values=skipped_values,
    )


def _parse_event(line: str) -> dict[str, Any] | None:
    """One JSONL line as an event object, or None when it is not one."""

    line = line.strip()
    if not line:
        return None
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None
    return event if isinstance(event, dict) else None


def _usage_of(event: dict[str, Any]) -> dict[str, Any] | None:
    """The event's ``message.usage`` record, when it carries one."""

    message = event.get("message")
    if not isinstance(message, dict):
        return None
    usage = message.get("usage")
    return usage if isinstance(usage, dict) else None


def _number(value: object) -> float | None:
    """A token/cost value as a float, or None when it is not numeric.

    Booleans are not numbers here: ``true`` in a usage field is malformed
    input, not one token.
    """

    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None
