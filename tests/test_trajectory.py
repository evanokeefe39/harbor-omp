"""The ATIF trajectory: the session in Harbor's format, without losing a line.

Four properties are asserted, and each is the reason the converter exists:

* one step per session line, in order — a session that converts is a session
  that is fully represented, so a reader can trust the artifact's shape;
* every step carries its line's decoded payload verbatim, so the trajectory
  alone reconstructs the session;
* a line that becomes no step refuses the whole conversion, so the artifact can
  never be quietly shorter than the log it names;
* ``final_metrics`` agree with ``AgentContext``, auxiliary model included, so
  the two things a consumer can read report the same spend.

The fixture is the redacted real session ``test_session.py`` documents; the
numbers below are its numbers.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from conftest import MODEL
from harbor.models.agent.context import AgentContext
from harbor.models.trajectories import Metrics, Trajectory
from harbor.utils.trajectory_validator import TrajectoryValidator, validate_trajectory

from harbor_omp import OmpAgent, session, trajectory

FIXTURE = Path(__file__).parent / "fixtures" / "omp_session.jsonl"

#: The fixture's literal shape: eleven lines, four of them messages.
FIXTURE_LINES = 11
FIXTURE_SESSION_ID = "01a1208b-c731-77b8-b304-49f0c366af59"
FIXTURE_EVENT_ORDER = [
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
FIXTURE_ROLES = ["user", "assistant", "toolResult", "assistant"]

#: The totals ``test_context.py`` pins; the trajectory must report the same.
FIXTURE_TOTAL_INPUT = 8807 + 5627 + 8960
FIXTURE_TOTAL_OUTPUT = 446 + 1220
FIXTURE_CACHE_READ = 8960
FIXTURE_TOTAL_COST = round(0.0004011878 + 0.0004024399 + 0.000236334, 6)
FIXTURE_MODEL_STEPS = 2

MAIN_MODEL = "deepseek/deepseek-v4-flash"
AUX_MODEL = "~typesafe/jev-latest"
#: The tool call the fixture's assistant turn makes, and its result answers.
TOOL_CALL_ID = "call_6346d92dd1c04a2d8fba87cc|fc_tmp_m4k9iy2crvf"

CONVERT_KWARGS: dict[str, Any] = {
    "session_dir_name": "omp-sessions",
    "agent_name": "omp",
    "agent_version": "omp/18.6.0",
    "model_name": MODEL,
}


def _logs_with_fixture(tmp_path: Path, session_dir_name: str = "omp-sessions") -> Path:
    """A logs dir holding the fixture as one session file."""

    logs_dir = tmp_path / "logs"
    directory = logs_dir / session_dir_name
    directory.mkdir(parents=True)
    shutil.copy(FIXTURE, directory / "session.jsonl")
    return logs_dir


def _convert(logs_dir: Path) -> Trajectory:
    """Convert ``logs_dir`` and insist there was something to convert."""

    built = trajectory.convert_trajectory(logs_dir, **CONVERT_KWARGS)
    assert built is not None
    return built


def _fixture_events() -> list[dict[str, Any]]:
    """The fixture's lines, decoded by the test rather than by the package."""

    return [
        json.loads(line)
        for line in FIXTURE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _event_type(step) -> str:
    return step.extra["omp_event_type"]


def test_every_session_line_becomes_exactly_one_step(tmp_path: Path) -> None:
    """The accounting rule: the artifact's step count *is* the session's line
    count, in order, with no gap in the step ids."""
    logs_dir = _logs_with_fixture(tmp_path)
    lines, unreadable = session.read_session_lines(logs_dir / "omp-sessions")

    built = _convert(logs_dir)

    assert unreadable == 0
    assert len(lines) == FIXTURE_LINES
    assert len(built.steps) == FIXTURE_LINES
    assert [step.step_id for step in built.steps] == list(range(1, FIXTURE_LINES + 1))
    assert built.final_metrics is not None
    assert built.final_metrics.total_steps == FIXTURE_LINES


def test_every_step_carries_its_session_line_verbatim(tmp_path: Path) -> None:
    """Losslessness, checked rather than asserted in prose: the trajectory's
    steps, in order, carry exactly the fixture's decoded lines — so the session
    is reconstructable from the artifact alone."""
    built = _convert(_logs_with_fixture(tmp_path))

    assert [step.extra["omp_event"] for step in built.steps] == _fixture_events()


def test_the_event_types_keep_their_order_and_the_root_identity(tmp_path: Path) -> None:
    """The trajectory names the session and the agent it came from, and the
    steps follow the log rather than a grouping of it."""
    built = _convert(_logs_with_fixture(tmp_path))

    assert [str(_event_type(step)) for step in built.steps] == FIXTURE_EVENT_ORDER
    assert built.session_id == FIXTURE_SESSION_ID
    assert built.agent.name == "omp"
    assert built.agent.version == "omp/18.6.0"
    assert built.agent.model_name == MAIN_MODEL


def test_the_message_roles_become_the_atif_sources(tmp_path: Path) -> None:
    """``user`` and ``assistant`` land on ATIF's ``user`` and ``agent``; a
    ``toolResult`` — a message line ATIF has no source for — is a ``system``
    step that names the call it answers, so the pairing survives without
    folding the line into the calling step's observation."""
    built = _convert(_logs_with_fixture(tmp_path))

    messages = [step for step in built.steps if _event_type(step) == "message"]

    assert [(step.extra["omp_role"], step.source) for step in messages] == [
        ("user", "user"),
        ("assistant", "agent"),
        ("toolResult", "system"),
        ("assistant", "agent"),
    ]
    assert [step.extra["omp_role"] for step in messages] == FIXTURE_ROLES

    user = messages[0]
    assert user.message == "do the task"

    assistant = messages[1]
    assert assistant.model_name == MAIN_MODEL
    assert assistant.reasoning_content == "Checking the database backend."
    # The session's thinking level, which the fixture's
    # thinking_level_change line configured, reaches the model turn.
    assert assistant.reasoning_effort == "high"
    assert assistant.llm_call_count == 1
    assert assistant.tool_calls is not None
    assert [call.tool_call_id for call in assistant.tool_calls] == [TOOL_CALL_ID]
    assert assistant.tool_calls[0].function_name == "bash"
    assert assistant.tool_calls[0].arguments == {
        "command": 'echo "DB_TYPE=$DB_TYPE"',
        "i": "Check active database backend",
    }
    assert assistant.metrics is not None
    # 8738 input + 0 cache read + 0 cache write: ATIF's prompt_tokens is
    # cache-inclusive, as AgentContext.n_input_tokens is.
    assert assistant.metrics.prompt_tokens == 8738
    assert assistant.metrics.completion_tokens == 224
    assert assistant.metrics.cached_tokens == 0
    assert assistant.metrics.cost_usd == pytest.approx(0.0004011878)

    result = messages[2]
    assert result.message == "DB_TYPE=duckdb"
    assert result.extra["omp_tool_call_id"] == TOOL_CALL_ID
    assert result.extra["omp_tool_name"] == "bash"
    assert result.extra["omp_is_error"] is False


def test_the_control_events_are_system_steps(tmp_path: Path) -> None:
    """Session lifecycle, configuration, a tool dispatch and an auxiliary
    model's usage record: none is a user turn or a turn of the trial's own
    model, so none may carry the fields ATIF reserves for agent steps."""
    built = _convert(_logs_with_fixture(tmp_path))

    control = [step for step in built.steps if _event_type(step) != "message"]

    assert [step.source for step in control] == ["system"] * len(control)
    for step in control:
        assert step.metrics is None
        assert step.tool_calls is None
        assert step.model_name is None
        assert step.reasoning_content is None

    by_type = {str(_event_type(step)): step for step in control}
    assert by_type["model_change"].message == (
        "model_change: model='openrouter/deepseek/deepseek-v4-flash', fallback=False"
    )
    assert by_type["thinking_level_change"].message.startswith("thinking_level_change:")
    # The usage record an auxiliary model wrote is a step of its own, kept
    # apart from the trial model's turns but visible in the trajectory.
    aux = by_type["model_usage"]
    assert aux.extra["omp_model"] == AUX_MODEL
    assert "~typesafe/jev-latest" in aux.message
    assert by_type["custom"].extra["omp_custom_type"] == "session_exit"
    assert by_type["title_change"].message.startswith("title_change:")


def test_the_fixture_converts_into_a_trajectory_harbors_validator_accepts(
    tmp_path: Path,
) -> None:
    """The artifact's gate: what a consumer's loader checks is Harbor's own
    validator, so the converter's output is put through it — both as the object
    and as the serialised document that lands on disk."""
    built = _convert(_logs_with_fixture(tmp_path))

    validator = TrajectoryValidator()
    assert validator.validate(built.to_json_dict()), validator.get_errors()
    assert validator.get_errors() == []

    serialised = trajectory.format_trajectory_json(built.to_json_dict())
    assert validate_trajectory(serialised) is True
    assert built.schema_version == "ATIF-v1.8"


def test_the_agent_writes_a_validated_trajectory_after_a_run(tmp_path: Path) -> None:
    """The post-run half: a non-streaming run leaves ``logs_dir/trajectory.json``
    behind, at the path Harbor's consumers read, validated as a file — and no
    temporary file."""
    logs_dir = _logs_with_fixture(tmp_path)

    OmpAgent(logs_dir=logs_dir, model_name=MODEL).populate_context_post_run(AgentContext())

    path = logs_dir / trajectory.TRAJECTORY_FILENAME
    assert path.is_file()
    validator = TrajectoryValidator()
    assert validator.validate(path), validator.get_errors()
    assert not (logs_dir / "trajectory.json.tmp").exists()
    document = json.loads(path.read_text(encoding="utf-8"))
    assert len(document["steps"]) == FIXTURE_LINES
    assert document["session_id"] == FIXTURE_SESSION_ID


def test_the_trajectory_totals_agree_with_the_agent_context(tmp_path: Path) -> None:
    """One session, one set of numbers: ``AgentContext`` and the trajectory's
    ``final_metrics`` are both the session reader's, so a consumer that reads
    either sees the same spend — the auxiliary model's included, which ATIF
    cannot carry as step metrics."""
    logs_dir = _logs_with_fixture(tmp_path)
    context = AgentContext()

    OmpAgent(logs_dir=logs_dir, model_name=MODEL).populate_context_post_run(context)

    document = json.loads((logs_dir / trajectory.TRAJECTORY_FILENAME).read_text(encoding="utf-8"))
    metrics = document["final_metrics"]

    assert metrics["total_prompt_tokens"] == context.n_input_tokens
    assert metrics["total_prompt_tokens"] == FIXTURE_TOTAL_INPUT
    assert metrics["total_completion_tokens"] == context.n_output_tokens
    assert metrics["total_completion_tokens"] == FIXTURE_TOTAL_OUTPUT
    assert metrics["total_cached_tokens"] == context.n_cache_tokens
    assert metrics["total_cached_tokens"] == FIXTURE_CACHE_READ
    assert metrics["total_cost_usd"] == context.cost_usd
    assert metrics["total_cost_usd"] == FIXTURE_TOTAL_COST
    assert metrics["extra"]["omp_steps"] == context.metadata["omp_steps"]
    assert metrics["extra"]["omp_steps"] == FIXTURE_MODEL_STEPS

    assert context.model_usage is not None
    assert metrics["extra"]["models"] == {
        model: usage.model_dump() for model, usage in context.model_usage.items()
    }
    assert sorted(metrics["extra"]["models"]) == [MAIN_MODEL, AUX_MODEL]
    assert metrics["extra"]["models"][AUX_MODEL]["n_output_tokens"] == 1220


def test_a_line_that_becomes_no_step_refuses_the_conversion(tmp_path: Path) -> None:
    """A torn line is a loud failure, not a shorter artifact: the trajectory
    claims to be the session, and a reader cannot tell a truncated conversion
    from a short session."""
    logs_dir = tmp_path / "logs"
    directory = logs_dir / "omp-sessions"
    directory.mkdir(parents=True)
    (directory / "session.jsonl").write_text(
        '{"type":"session","id":"torn-session",'
        '"timestamp":"2026-10-09T12:00:00.000Z"}\n'
        '{"type":"message","message":{"role":"user",'
        '"content":[{"type":"text","text":"do it"}]}}\n'
        '{"type":"message","message":{"role":"assistant","content":[{"type":\n',
        encoding="utf-8",
    )

    with pytest.raises(trajectory.TrajectoryAccountingError) as raised:
        _convert(logs_dir)

    message = str(raised.value)
    assert "1 of 3 session line(s) became no step" in message
    assert "session.jsonl:3 (not a JSON object)" in message
    assert not (logs_dir / trajectory.TRAJECTORY_FILENAME).exists()


def test_a_session_file_that_cannot_be_read_refuses_the_conversion(
    tmp_path: Path,
) -> None:
    """A file whose lines cannot be read is worse than a torn one: its lines are
    invisible, so the conversion refuses rather than accounting for the part it
    happens to see."""
    logs_dir = _logs_with_fixture(tmp_path)
    (logs_dir / "omp-sessions" / "torn.jsonl").write_bytes(b"\xff\xfe not utf-8\n")

    with pytest.raises(trajectory.TrajectoryAccountingError, match="could not be read"):
        _convert(logs_dir)


def test_an_absent_session_is_not_an_error(tmp_path: Path) -> None:
    """A run that wrote no session has no trajectory to write, and says so
    rather than writing an empty document."""
    empty = tmp_path / "never-created"

    assert trajectory.convert_trajectory(empty, **CONVERT_KWARGS) is None

    logs_dir = tmp_path / "logs"
    (logs_dir / "omp-sessions").mkdir(parents=True)
    assert trajectory.convert_trajectory(logs_dir, **CONVERT_KWARGS) is None

    OmpAgent(logs_dir=logs_dir, model_name=MODEL).populate_context_post_run(AgentContext())
    assert not (logs_dir / trajectory.TRAJECTORY_FILENAME).exists()


def test_the_streamed_layout_is_read_and_preferred(tmp_path: Path) -> None:
    """Harbor's live stream extracts the session tar under ``logs_dir/sessions``,
    the run writes under ``logs_dir/<session_dir_name>``: the converter reads
    whichever is there, and prefers the streamed copy when both are."""
    logs_dir = tmp_path / "logs"
    streamed = logs_dir / "sessions"
    streamed.mkdir(parents=True)
    (streamed / "live.jsonl").write_text(
        '{"type":"session","id":"streamed-session","timestamp":"2026-10-09T12:00:00.000Z"}\n',
        encoding="utf-8",
    )
    run_dir = logs_dir / "omp-sessions"
    run_dir.mkdir()
    (run_dir / "run.jsonl").write_text(
        '{"type":"session","id":"run-session","timestamp":"2026-10-09T12:00:00.000Z"}\n',
        encoding="utf-8",
    )

    assert _convert(logs_dir).session_id == "streamed-session"

    shutil.rmtree(streamed)
    assert _convert(logs_dir).session_id == "run-session"


def test_the_writer_refuses_a_document_harbor_rejects(tmp_path: Path) -> None:
    """The write is gated by Harbor's validator: a document its loader would
    reject never lands, and an artifact already at the path is left alone rather
    than replaced by a broken one. Metrics on a non-agent step is the shape the
    validator forbids and a converter bug could produce."""
    built = _convert(_logs_with_fixture(tmp_path))
    path = tmp_path / trajectory.TRAJECTORY_FILENAME
    path.write_text('{"previous": true}\n', encoding="utf-8")
    user_step = next(step for step in built.steps if step.source == "user")
    user_step.metrics = Metrics(prompt_tokens=1)

    errors = trajectory.write_trajectory(path, built)

    assert errors, "the guard accepted a document Harbor's validator rejects"
    assert any("metrics" in error for error in errors)
    assert path.read_text(encoding="utf-8") == '{"previous": true}\n'
    assert not (tmp_path / "trajectory.json.tmp").exists()


def test_the_writer_writes_exactly_the_formatted_document(tmp_path: Path) -> None:
    """The happy path, asserted on bytes: what lands is what
    ``format_trajectory_json`` produces, not a re-serialisation of it."""
    built = _convert(_logs_with_fixture(tmp_path))
    path = tmp_path / trajectory.TRAJECTORY_FILENAME

    assert trajectory.write_trajectory(path, built) == []

    assert path.read_text(encoding="utf-8") == trajectory.format_trajectory_json(
        built.to_json_dict()
    )


def test_event_shapes_the_fixture_lacks_still_become_one_step_each(
    tmp_path: Path,
) -> None:
    """The rule is every event, not the fixture's events: a tool dispatch, an
    injected message and a type a later omp version invents each become exactly
    one ``system`` step carrying their payload, so a new event shape changes how
    readable the trajectory is and never how complete it is."""
    logs_dir = tmp_path / "logs"
    directory = logs_dir / "omp-sessions"
    directory.mkdir(parents=True)
    (directory / "session.jsonl").write_text(
        '{"type":"custom","customType":"tool_execution_start","data":'
        '{"toolCallId":"call_1|fc_1","toolName":"bash","intent":"check"},'
        '"id":"c1","timestamp":"2026-10-09T12:00:00.000Z"}\n'
        '{"type":"custom_message","customType":"mid-run-todo-nudge",'
        '"content":"<system-reminder>2 todo items still open.</system-reminder>",'
        '"display":false,"attribution":"agent","id":"c2",'
        '"timestamp":"2026-10-09T12:00:01.000Z"}\n'
        '{"type":"future_event","payload":{"anything":[1,2,3]},"id":"c3",'
        '"timestamp":"2026-10-09T12:00:02.000Z"}\n',
        encoding="utf-8",
    )

    built = _convert(logs_dir)

    assert len(built.steps) == 3
    assert [step.source for step in built.steps] == ["system", "system", "system"]

    dispatch, injected, unknown = built.steps
    assert dispatch.message == "custom: type='tool_execution_start', tool='bash', intent='check'"
    assert dispatch.extra["omp_tool_call_id"] == "call_1|fc_1"
    assert dispatch.extra["omp_tool_name"] == "bash"

    assert injected.message == "<system-reminder>2 todo items still open.</system-reminder>"
    assert injected.extra["omp_custom_type"] == "mid-run-todo-nudge"

    # A type this converter has never seen: one step, its payload intact.
    assert unknown.message == "future_event"
    assert unknown.extra["omp_event"] == {
        "type": "future_event",
        "payload": {"anything": [1, 2, 3]},
        "id": "c3",
        "timestamp": "2026-10-09T12:00:02.000Z",
    }

    validator = TrajectoryValidator()
    assert validator.validate(built.to_json_dict()), validator.get_errors()
