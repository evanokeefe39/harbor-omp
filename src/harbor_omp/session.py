"""Reading an omp session directory: usage, cost, and step counts.

Stdlib only: this module imports nothing but the standard library, and without
Harbor installed it is loaded straight from its file — ``import
harbor_omp.session`` runs the package ``__init__``, which needs Harbor. These
numbers are the trial's token and cost evidence, and any harness must be able
to read them.

The layout this reads is what a real omp run writes: one or more ``*.jsonl``
session files whose usage arrives in one of two places.

* A ``message.usage`` record on an assistant message — the trial's own model,
  one record per model turn, attributed to the message's ``model``.
* A ``model_usage`` event — an auxiliary model's turn, for example the one
  behind a ``find`` tool, or a ``typesafe`` role. These are **additional**: the
  assistant messages carry the main model only, so a reader that sums only
  ``message.usage`` under-reports the trial's tokens and cost.

The two classes are summed together. A ``model_usage`` record whose (model,
timestamp) an assistant message already covered is dropped, because that pair
is the same turn reported twice.

This module is also the reader the ATIF trajectory converter uses
(``harbor_omp.trajectory``, whose module docstring states the encoding). A
malformed line, an unreadable file, or a non-numeric usage field is counted
rather than raised here: the totals must stay readable, and the counts are how
a caller notices that the totals are low. That tolerance is exactly wrong for a
trajectory, so the converter reads through ``read_session_lines`` instead — the
same parsing, reporting every non-blank line whether or not it decoded, so a
caller that must account for every line can prove it did.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ModelTotals:
    """One model's usage, summed over the records attributed to it."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    records: int = 0

    @property
    def total_input_tokens(self) -> int:
        """Input tokens including cached tokens (``AgentContext`` semantics)."""

        return self.input_tokens + self.cache_read_tokens + self.cache_write_tokens


@dataclass(frozen=True)
class SessionUsage:
    """A session directory's totals, summed over its JSONL files."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    #: Model turns: one per ``message.usage`` record. An auxiliary model's
    #: ``model_usage`` record is not a turn of the trial's own model, so it is
    #: counted in the totals and in ``models``, never here.
    steps: int = 0
    files_read: int = 0
    skipped_files: int = 0
    skipped_lines: int = 0
    skipped_values: int = 0
    unattributed_records: int = 0
    models: dict[str, ModelTotals] = field(default_factory=dict)

    @property
    def total_input_tokens(self) -> int:
        """Input tokens including cached tokens (``AgentContext`` semantics)."""

        return self.input_tokens + self.cache_read_tokens + self.cache_write_tokens


def session_files(session_dir: Path) -> list[Path]:
    """The session JSONL files in ``session_dir``, in stable order."""

    if not session_dir.is_dir():
        return []
    return sorted(session_dir.glob("*.jsonl"))


def reported_cost(cost_usd: float) -> float | None:
    """A summed cost as Harbor reports it: ``None`` when omp reported none.

    A zero cost is omp saying "not reported", not a free run, so it must not be
    published as a confident ``0.0``. Both the adapter's ``AgentContext`` and
    the trajectory's totals go through this one rule, at the precision the
    adapter has always published.
    """

    return round(cost_usd, 6) if cost_usd > 0 else None


def number(value: object) -> float | None:
    """A token/cost value as a float, or None when it is not numeric.

    Booleans are not numbers here: ``true`` in a usage field is malformed
    input, not one token. The metric path and the trajectory share this one
    coercion, so a value the reader counts as unreadable cannot be read as a
    number somewhere else.
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


def iter_session_events(session_dir: Path) -> Iterator[dict[str, Any]]:
    """Yield every JSON object event in the directory, in file order.

    Undecodable lines and unreadable files are skipped, so a caller that must
    know about them uses ``sum_session_usage`` (which counts them) or reads the
    files itself. Yields nothing when the directory holds no JSONL, or when
    every file it holds failed to read.
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


@dataclass(frozen=True)
class SessionLine:
    """One non-blank line of a session file, and the event it decoded to.

    ``event`` is None when the line is not a JSON object — a torn write, a
    truncated tail, or a document that is not an object. The line is reported
    anyway: a caller that has to account for every line needs to see the ones
    that carry no event, or it cannot say that it accounted for them.
    """

    #: The session file the line came from (its name, not its path).
    file_name: str
    #: The line's 1-based number within its file.
    number: int
    #: The decoded event, or None when the line is not a JSON object.
    event: dict[str, Any] | None

    @property
    def site(self) -> str:
        """The line's site as ``file:line``, for a message that names it."""

        return f"{self.file_name}:{self.number}"


def read_session_lines(session_dir: Path) -> tuple[list[SessionLine], int]:
    """Every non-blank line of the directory's JSONL, and unreadable file count.

    ``iter_session_events`` is the streaming view — decoded events only, junk
    dropped. This is the accounting view: one entry per non-blank line, in file
    order, whether or not the line decoded, so a caller can prove that every
    line became something. A file that could not be read at all is *counted* in
    the returned total rather than dropped, because the lines a caller cannot
    see are exactly the ones that would go missing silently.

    Blank lines are not lines: they carry nothing, and the summer has always
    ignored them. Returns ``([], 0)`` for a directory with no JSONL.

    Unlike the streaming reader this materialises the directory. That is the
    price of the accounting — a caller that pairs lines with its own output
    needs all of them — so it is kept apart from the metric path, which stays a
    single streaming pass.
    """

    lines: list[SessionLine] = []
    unreadable_files = 0
    for session_file in session_files(session_dir):
        try:
            text = session_file.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            unreadable_files += 1
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            lines.append(
                SessionLine(
                    file_name=session_file.name,
                    number=number,
                    event=_parse_event(line),
                )
            )
    return lines, unreadable_files


def sum_session_usage(session_dir: Path) -> SessionUsage | None:
    """Sum the usage records of a session directory.

    Returns ``None`` when there is nothing to sum: the directory holds no JSONL
    at all (the run never started omp, or wrote its session somewhere else), or
    every JSONL it holds failed to read. A caller must treat that as *absent*,
    not as zero — an unread session and a free session are different facts.
    """

    files = session_files(session_dir)
    if not files:
        return None

    accumulator = _Accumulator()
    for session_file in files:
        try:
            text = session_file.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            accumulator.skipped_files += 1
            continue
        accumulator.files_read += 1
        for line in text.splitlines():
            if not line.strip():
                continue
            event = _parse_event(line)
            if event is None:
                accumulator.skipped_lines += 1
                continue
            accumulator.add(event)
    if accumulator.files_read == 0:
        return None
    return accumulator.usage()


class _Accumulator:
    """The running totals of one session directory."""

    def __init__(self) -> None:
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_read_tokens = 0
        self.cache_write_tokens = 0
        self.cost_usd = 0.0
        self.steps = 0
        self.files_read = 0
        self.skipped_files = 0
        self.skipped_lines = 0
        self.skipped_values = 0
        self.unattributed_records = 0
        self.models: dict[str, ModelTotals] = {}
        #: The (model, timestamp) pairs a message usage record already covered.
        self._covered: set[tuple[str, str]] = set()

    def add(self, event: dict[str, Any]) -> None:
        """Add one event's usage, if it carries any."""

        usage = _usage_of(event)
        if usage is not None:
            model = _model_name((event.get("message") or {}).get("model"))
            self._covered.add((model or "", _timestamp_key(event)))
            self._add_record(usage, model)
            self.steps += 1
            return
        if event.get("type") != "model_usage":
            return
        usage = event.get("usage")
        if not isinstance(usage, dict):
            # A model_usage event the reader cannot read: counted, not guessed.
            self.skipped_values += 1
            return
        model = _model_name(event.get("model"))
        if (model or "", _timestamp_key(event)) in self._covered:
            return
        self._add_record(usage, model)

    def _add_record(self, usage: dict[str, Any], model: str | None) -> None:
        """Add one usage record to the totals and to its model's bucket."""

        values: dict[str, int] = {}
        for field_name in ("input", "output", "cacheRead", "cacheWrite"):
            raw = usage.get(field_name)
            value = number(raw)
            if value is None:
                if raw is not None:
                    self.skipped_values += 1
                value = 0.0
            values[field_name] = int(value)
        cost = 0.0
        cost_field = usage.get("cost")
        if isinstance(cost_field, dict):
            raw_total = cost_field.get("total")
            total = number(raw_total)
            if total is None:
                if raw_total is not None:
                    self.skipped_values += 1
            else:
                cost = total

        self.input_tokens += values["input"]
        self.output_tokens += values["output"]
        self.cache_read_tokens += values["cacheRead"]
        self.cache_write_tokens += values["cacheWrite"]
        self.cost_usd += cost

        if model is None:
            self.unattributed_records += 1
            return
        previous = self.models.get(model, ModelTotals())
        self.models[model] = ModelTotals(
            input_tokens=previous.input_tokens + values["input"],
            output_tokens=previous.output_tokens + values["output"],
            cache_read_tokens=previous.cache_read_tokens + values["cacheRead"],
            cache_write_tokens=previous.cache_write_tokens + values["cacheWrite"],
            cost_usd=previous.cost_usd + cost,
            records=previous.records + 1,
        )

    def usage(self) -> SessionUsage:
        """The totals as the frozen values a caller reads."""

        return SessionUsage(
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            cache_read_tokens=self.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens,
            cost_usd=self.cost_usd,
            steps=self.steps,
            files_read=self.files_read,
            skipped_files=self.skipped_files,
            skipped_lines=self.skipped_lines,
            skipped_values=self.skipped_values,
            unattributed_records=self.unattributed_records,
            models=dict(self.models),
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


def _model_name(value: object) -> str | None:
    """A usage record's model name, or None when it does not name one."""

    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _timestamp_key(event: dict[str, Any]) -> str:
    """The event's timestamp as a dedupe key, ``""`` when it has none."""

    value = event.get("timestamp")
    if isinstance(value, bool) or value is None:
        return ""
    if isinstance(value, (str, int, float)):
        return str(value)
    return ""
