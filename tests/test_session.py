"""The session reader: what a session directory sums to, and what it refuses to
pretend about.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from harbor_omp import session

FIXTURE = Path(__file__).parent / "fixtures" / "omp_session.jsonl"

#: The fixture's literal totals: two usage records, one file.
FIXTURE_INPUT = 150
FIXTURE_OUTPUT = 60
FIXTURE_CACHE_READ = 3500
FIXTURE_CACHE_WRITE = 200
FIXTURE_COST = 0.04
FIXTURE_STEPS = 2


def _sessions_dir(tmp_path: Path, name: str = "sessions") -> Path:
    directory = tmp_path / name
    directory.mkdir()
    return directory


def test_the_fixture_sums_its_tokens_cost_and_steps(tmp_path: Path) -> None:
    """The whole point of the module: omp's own numbers, summed."""
    directory = _sessions_dir(tmp_path)
    shutil.copy(FIXTURE, directory / "session.jsonl")

    usage = session.sum_session_usage(directory)

    assert usage is not None
    assert usage.input_tokens == FIXTURE_INPUT
    assert usage.output_tokens == FIXTURE_OUTPUT
    assert usage.cache_read_tokens == FIXTURE_CACHE_READ
    assert usage.cache_write_tokens == FIXTURE_CACHE_WRITE
    assert usage.cost_usd == FIXTURE_COST
    assert usage.steps == FIXTURE_STEPS
    assert usage.total_input_tokens == (
        FIXTURE_INPUT + FIXTURE_CACHE_READ + FIXTURE_CACHE_WRITE
    )
    assert (usage.skipped_files, usage.skipped_lines, usage.skipped_values) == (0, 0, 0)


def test_an_empty_directory_is_absent_not_zero(tmp_path: Path) -> None:
    """An unread session and a free session are different facts."""
    assert session.sum_session_usage(_sessions_dir(tmp_path)) is None
    assert session.sum_session_usage(tmp_path / "never-created") is None


def test_a_directory_without_jsonl_is_absent(tmp_path: Path) -> None:
    """omp also writes tool logs beside the session; only JSONL is a session."""
    directory = _sessions_dir(tmp_path)
    (directory / "notes.txt").write_text("not a session\n", encoding="utf-8")
    (directory / "1.bash.log").write_text("tool log\n", encoding="utf-8")

    assert session.sum_session_usage(directory) is None


def test_every_session_file_in_the_directory_is_summed(tmp_path: Path) -> None:
    """One trial can leave more than one session file; the totals are the
    trial's, not the first file's."""
    directory = _sessions_dir(tmp_path)
    shutil.copy(FIXTURE, directory / "a.jsonl")
    (directory / "b.jsonl").write_text(
        '{"message":{"usage":{"input":5,"output":1,"cacheRead":0,"cacheWrite":0,'
        '"cost":{"total":0.001}}}}\n',
        encoding="utf-8",
    )

    usage = session.sum_session_usage(directory)

    assert usage is not None
    assert usage.files_read == 2
    assert usage.input_tokens == FIXTURE_INPUT + 5
    assert usage.output_tokens == FIXTURE_OUTPUT + 1
    assert usage.steps == FIXTURE_STEPS + 1
    assert usage.cost_usd == pytest.approx(FIXTURE_COST + 0.001)


def test_a_corrupt_line_and_a_malformed_value_are_counted_not_raised(
    tmp_path: Path,
) -> None:
    """Totals stay readable, and the counts are how a caller notices they may be
    low — a crash post-run would lose the whole trial's metrics."""
    directory = _sessions_dir(tmp_path)
    (directory / "session.jsonl").write_text(
        '{"message":{"usage":{"input":"abc","output":5,"cacheRead":0,"cacheWrite":0,'
        '"cost":{"total":"oops"}}}}\n'
        "not json at all\n",
        encoding="utf-8",
    )

    usage = session.sum_session_usage(directory)

    assert usage is not None
    assert usage.output_tokens == 5
    assert usage.input_tokens == 0
    assert usage.cost_usd == 0.0
    assert usage.steps == 1
    assert usage.skipped_lines == 1
    assert usage.skipped_values == 2


def test_iter_session_events_yields_the_objects_and_skips_junk(tmp_path: Path) -> None:
    """The streaming reader the trajectory converter will use: only JSON objects,
    in file order, with junk dropped."""
    directory = _sessions_dir(tmp_path)
    (directory / "session.jsonl").write_text(
        '{"type":"message"}\n'
        "[1, 2, 3]\n"
        "not json\n"
        '{"type":"tool"}\n',
        encoding="utf-8",
    )

    events = list(session.iter_session_events(directory))

    assert events == [{"type": "message"}, {"type": "tool"}]


def test_the_fixture_flows_through_the_streaming_reader(tmp_path: Path) -> None:
    """The reader and the summer see the same directory the same way."""
    directory = _sessions_dir(tmp_path)
    shutil.copy(FIXTURE, directory / "session.jsonl")

    events = list(session.iter_session_events(directory))

    assert [event.get("type") for event in events] == [
        "session",
        "message",
        "message",
        "tool",
        "message",
    ]
