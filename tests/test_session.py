"""The session reader: what a session directory sums to, and what it refuses to
pretend about.

``fixtures/omp_session.jsonl`` is a redacted excerpt of a real omp session: the
event envelope and every usage record in it are the ones the CLI wrote (prose
replaced, one ``model_usage`` record and its two ``message.usage`` records kept
byte for byte), so the numbers below are the fixture's, not invented.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from harbor_omp import session

FIXTURE = Path(__file__).parent / "fixtures" / "omp_session.jsonl"

#: The fixture's literal totals: two ``message.usage`` records in one file.
FIXTURE_INPUT = 8807
FIXTURE_OUTPUT = 446
FIXTURE_CACHE_READ = 8960
FIXTURE_CACHE_WRITE = 0
FIXTURE_COST = 0.0004011878 + 0.0004024399
FIXTURE_STEPS = 2

#: The models the fixture's records name: the trial's own model on the message
#: records, and the auxiliary model omp reports separately.
MAIN_MODEL = "deepseek/deepseek-v4-flash"
AUX_MODEL = "~typesafe/jev-latest"
AUX_INPUT = 5627
AUX_OUTPUT = 1220
AUX_COST = 0.000236334


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
    assert usage.input_tokens == FIXTURE_INPUT + AUX_INPUT
    assert usage.output_tokens == FIXTURE_OUTPUT + AUX_OUTPUT
    assert usage.cache_read_tokens == FIXTURE_CACHE_READ
    assert usage.cache_write_tokens == FIXTURE_CACHE_WRITE
    assert usage.cost_usd == pytest.approx(FIXTURE_COST + AUX_COST)
    assert usage.steps == FIXTURE_STEPS
    assert usage.total_input_tokens == (
        FIXTURE_INPUT + AUX_INPUT + FIXTURE_CACHE_READ + FIXTURE_CACHE_WRITE
    )
    assert (usage.skipped_files, usage.skipped_lines, usage.skipped_values) == (0, 0, 0)


def test_the_auxiliary_models_usage_record_is_summed_not_ignored(tmp_path: Path) -> None:
    """omp reports an auxiliary model's turns in a ``model_usage`` event, beside
    the assistant messages that carry the trial's own model. Ignoring that class
    under-reports the trial: the record's tokens and cost must reach both the
    totals and the per-model breakdown."""
    directory = _sessions_dir(tmp_path)
    shutil.copy(FIXTURE, directory / "session.jsonl")

    usage = session.sum_session_usage(directory)

    assert usage is not None
    # The record is genuinely additional: dropping the branch would leave this
    # at the message-only total.
    assert usage.total_input_tokens > FIXTURE_INPUT + FIXTURE_CACHE_READ
    auxiliary = usage.models[AUX_MODEL]
    assert auxiliary.input_tokens == AUX_INPUT
    assert auxiliary.output_tokens == AUX_OUTPUT
    assert auxiliary.total_input_tokens == AUX_INPUT
    assert auxiliary.cost_usd == pytest.approx(AUX_COST)
    assert auxiliary.records == 1

    own = usage.models[MAIN_MODEL]
    assert own.input_tokens == FIXTURE_INPUT
    assert own.output_tokens == FIXTURE_OUTPUT
    assert own.cache_read_tokens == FIXTURE_CACHE_READ
    assert own.cache_write_tokens == FIXTURE_CACHE_WRITE
    assert own.total_input_tokens == (
        FIXTURE_INPUT + FIXTURE_CACHE_READ + FIXTURE_CACHE_WRITE
    )
    assert own.cost_usd == pytest.approx(FIXTURE_COST)
    assert own.records == FIXTURE_STEPS


def test_a_model_usage_record_a_message_already_carried_is_not_added_twice(
    tmp_path: Path,
) -> None:
    """The two classes can name the same (model, timestamp) — a version that
    writes both would otherwise double-count one model turn."""
    directory = _sessions_dir(tmp_path)
    (directory / "session.jsonl").write_text(
        '{"type":"message","timestamp":"2026-10-09T12:03:20.304Z","message":'
        '{"role":"assistant","model":"deepseek/deepseek-v4-flash","usage":'
        '{"input":100,"output":10,"cacheRead":0,"cacheWrite":0,'
        '"cost":{"total":0.01}}}}\n'
        '{"type":"model_usage","timestamp":"2026-10-09T12:03:20.304Z",'
        '"model":"deepseek/deepseek-v4-flash","usage":{"input":100,"output":10,'
        '"cacheRead":0,"cacheWrite":0,"cost":{"total":0.01}}}\n',
        encoding="utf-8",
    )

    usage = session.sum_session_usage(directory)

    assert usage is not None
    assert usage.input_tokens == 100
    assert usage.output_tokens == 10
    assert usage.cost_usd == pytest.approx(0.01)
    assert usage.steps == 1
    assert usage.models[MAIN_MODEL].records == 1


def test_a_usage_record_without_a_model_is_counted_rather_than_guessed(
    tmp_path: Path,
) -> None:
    """An unattributable record still reaches the totals — the trial spent those
    tokens — and the count says the per-model breakdown does not cover it."""
    directory = _sessions_dir(tmp_path)
    (directory / "session.jsonl").write_text(
        '{"type":"model_usage","usage":{"input":40,"output":4,'
        '"cacheRead":0,"cacheWrite":0,"cost":{"total":0.002}}}\n',
        encoding="utf-8",
    )

    usage = session.sum_session_usage(directory)

    assert usage is not None
    assert usage.input_tokens == 40
    assert usage.output_tokens == 4
    assert usage.unattributed_records == 1
    assert usage.models == {}


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


def test_an_unreadable_session_is_absent_not_zero(tmp_path: Path) -> None:
    """A file that cannot be decoded is not a free run: reporting zeros would
    hand Harbor a confident token total for a trial nobody can read."""
    directory = _sessions_dir(tmp_path)
    (directory / "session.jsonl").write_bytes(b'{"type":"session"}\xff\xfe\n')

    assert session.sum_session_usage(directory) is None


def test_a_partly_unreadable_directory_is_a_total_with_its_skip_count(
    tmp_path: Path,
) -> None:
    """One unreadable file beside a readable one is a real (if incomplete)
    number: the count is what tells a caller the total may be low."""
    directory = _sessions_dir(tmp_path)
    shutil.copy(FIXTURE, directory / "session.jsonl")
    (directory / "torn.jsonl").write_bytes(b"\xff\xfe not utf-8\n")

    usage = session.sum_session_usage(directory)

    assert usage is not None
    assert usage.files_read == 1
    assert usage.skipped_files == 1
    assert usage.input_tokens == FIXTURE_INPUT + AUX_INPUT


def test_every_session_file_in_the_directory_is_summed(tmp_path: Path) -> None:
    """One trial can leave more than one session file; the totals are the
    trial's, not the first file's."""
    directory = _sessions_dir(tmp_path)
    shutil.copy(FIXTURE, directory / "a.jsonl")
    (directory / "b.jsonl").write_text(
        '{"type":"model_usage","timestamp":"2026-10-09T13:00:00.000Z",'
        '"model":"openrouter/some/model","usage":{"input":5,"output":1,'
        '"cacheRead":0,"cacheWrite":7,"cost":{"total":0.001}}}\n',
        encoding="utf-8",
    )

    usage = session.sum_session_usage(directory)

    assert usage is not None
    assert usage.files_read == 2
    assert usage.input_tokens == FIXTURE_INPUT + AUX_INPUT + 5
    assert usage.output_tokens == FIXTURE_OUTPUT + AUX_OUTPUT + 1
    assert usage.cache_write_tokens == FIXTURE_CACHE_WRITE + 7
    assert usage.steps == FIXTURE_STEPS
    assert usage.cost_usd == pytest.approx(FIXTURE_COST + AUX_COST + 0.001)
    assert usage.models["openrouter/some/model"].cache_write_tokens == 7


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
    # The record names no model, so it reaches the totals but not the breakdown.
    assert usage.unattributed_records == 1


def test_iter_session_events_yields_the_objects_and_skips_junk(tmp_path: Path) -> None:
    """The streaming reader the trajectory converter will use: only JSON objects,
    in file order, with junk dropped."""
    directory = _sessions_dir(tmp_path)
    (directory / "session.jsonl").write_text(
        '{"type":"message"}\n'
        "[1, 2, 3]\n"
        "not json\n"
        '{"type":"model_usage"}\n',
        encoding="utf-8",
    )

    events = list(session.iter_session_events(directory))

    assert events == [{"type": "message"}, {"type": "model_usage"}]


def test_the_fixture_flows_through_the_streaming_reader(tmp_path: Path) -> None:
    """The reader and the summer see the same directory the same way."""
    directory = _sessions_dir(tmp_path)
    shutil.copy(FIXTURE, directory / "session.jsonl")

    events = list(session.iter_session_events(directory))

    assert [event.get("type") for event in events] == [
        "session",
        "title",
        "model_change",
        "thinking_level_change",
        "message",
        "message",
        "message",
        "message",
        "model_usage",
        "custom",
        "title_change",
    ]
