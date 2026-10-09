"""Building a Harbor ATIF trajectory from an omp session directory.

Harbor's observability surface — the viewer's Trajectory panel, ``atif2otel``,
the Opik/Phoenix/Braintrust/LangSmith plugins, ``harbor traces export`` — reads
one artifact: ``logs_dir/trajectory.json`` in ATIF (Agent Trajectory Interchange
Format). This module is the converter behind both paths that produce it:
``OmpAgent.convert_trajectory``, which Harbor's live stream calls with the
temporary logs dir it assembles, and ``populate_context_post_run``, which writes
the file for a run that is not streaming.

The encoding is lossless by construction, not by care:

* one step per non-blank session line, in file order. A ``message`` event is a
  conversation step (``user`` → ``user``, ``assistant`` → ``agent``); every
  other event — ``session``, ``title``, ``model_change``,
  ``thinking_level_change``, ``custom``, ``custom_message``, ``title_change``,
  ``model_usage`` — is a ``system`` step;
* every step carries its line's decoded payload verbatim under
  ``extra["omp_event"]``, so the session can be reconstructed from the
  trajectory alone;
* ``_account`` refuses to build a trajectory whose steps do not account for
  every line. A torn line is a loud ``TrajectoryAccountingError``, never a
  silently shorter artifact.

Three consequences are deliberate, and stated here so nobody has to infer them
from the output:

* A ``toolResult`` line becomes its own ``system`` step rather than the calling
  agent step's ``observation``. ATIF's ``source`` is one of
  ``system``/``user``/``agent``, and its validator requires an observation
  result's ``source_call_id`` to name a tool call of *its own* step — so folding
  the result into the calling step would leave that line with no step and break
  the accounting. The pairing survives in ``extra["omp_tool_call_id"]``, which
  names the ``tool_calls[]`` entry on the agent step that issued the call.
* ``final_metrics`` are ``harbor_omp.session``'s totals, not a second summation
  over the steps, so the trajectory and ``AgentContext`` report the same numbers.
  The auxiliary model's ``model_usage`` records are real spend that ATIF cannot
  carry as step metrics (a ``system`` step may not have ``metrics``), so they
  appear in ``final_metrics.extra["models"]`` beside the totals.
* A ``system`` step's ``message`` is a rendering of the event, never a claim
  about it: the payload is under ``extra["omp_event"]``. ``custom_message`` is
  the one case where the rendering is the event's own content, because that
  content is the text omp injected into the session.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Final

from harbor.models.agent.context import ModelUsage
from harbor.models.trajectories import (
    Agent,
    FinalMetrics,
    Metrics,
    Step,
    ToolCall,
    Trajectory,
)
from harbor.utils.trajectory_utils import format_trajectory_json
from harbor.utils.trajectory_validator import TrajectoryValidator

from harbor_omp import session

#: Harbor's ATIF artifact, inside the agent's log dir.
TRAJECTORY_FILENAME: Final[str] = "trajectory.json"

#: The subdirectory Harbor's live stream extracts the downloaded session tar
#: into (``harbor/trial/sync_trajectory.py``).
STREAMED_SESSIONS_DIRNAME: Final[str] = "sessions"

#: The ATIF version this converter writes.
SCHEMA_VERSION: Final[str] = "ATIF-v1.8"

#: Every step carries its session line's decoded payload under this key.
EVENT_KEY: Final[str] = "omp_event"

#: The trajectory's ``notes``: how to read the document it labels.
NOTES: Final[str] = (
    "Lossless omp session: one step per non-blank session line, in file order, "
    "each carrying its line's decoded payload under extra.omp_event. "
    "Non-message events (session, title, model_change, thinking_level_change, "
    "custom, custom_message, title_change, model_usage) are system steps, as is "
    "a toolResult line — it names its call in extra.omp_tool_call_id rather "
    "than being folded into the calling step's observation, which would leave "
    "the line with no step of its own. final_metrics are the session reader's "
    "totals, auxiliary model_usage records included, and agree with "
    "AgentContext; final_metrics.extra.models carries the per-model breakdown."
)

#: The fields a rendered system step names, per event type: ``(label, key)``.
#: A rendering only — the event itself is under ``extra[EVENT_KEY]``.
_NAMED_FIELDS: Final[dict[str, tuple[tuple[str, str], ...]]] = {
    "session": (("id", "id"), ("version", "version"), ("cwd", "cwd")),
    "title": (("title", "title"), ("source", "source")),
    "title_change": (("title", "title"), ("trigger", "trigger")),
    "model_change": (("model", "model"), ("fallback", "resolvedModelIsFallback")),
    "thinking_level_change": (("level", "thinkingLevel"),),
    "model_usage": (("model", "model"), ("role", "role"), ("purpose", "purpose")),
    "custom": (("type", "customType"),),
}

#: The ``custom`` event's payload fields a rendering names, inside ``data``.
_NAMED_DATA_FIELDS: Final[tuple[tuple[str, str], ...]] = (
    ("tool", "toolName"),
    ("intent", "intent"),
    ("reason", "reason"),
)


class TrajectoryAccountingError(RuntimeError):
    """A session line that no trajectory step accounts for.

    Raised instead of returning — or writing — a trajectory that silently omits
    a line: the artifact claims to be the session, so a shorter one would read
    as a complete session rather than as a truncated conversion.
    """


def session_dir_in(logs_dir: Path, session_dir_name: str) -> Path:
    """The session directory inside a logs dir, in either layout.

    Two layouts reach the converter. Harbor's live stream tars the contents of
    ``remote_session_logs_dir`` and extracts it under ``logs_dir/sessions``; the
    run itself writes its session under ``logs_dir/<session_dir_name>``. The
    streamed copy wins when both are present, because it is the layout Harbor's
    live path assembles, in a temporary directory that holds nothing else.
    """

    streamed = logs_dir / STREAMED_SESSIONS_DIRNAME
    if session.session_files(streamed):
        return streamed
    return logs_dir / session_dir_name


def model_usage(usage: session.SessionUsage) -> dict[str, ModelUsage]:
    """A session's per-model totals as Harbor reports usage per model.

    One mapping for two consumers: ``AgentContext.model_usage`` and this
    trajectory's ``final_metrics.extra["models"]``. They cannot disagree — the
    numbers are the session reader's, the shape is built once, and
    ``n_input_tokens`` keeps ``AgentContext``'s cache-inclusive convention.
    """

    return {
        model: ModelUsage(
            n_input_tokens=totals.total_input_tokens,
            n_cache_tokens=totals.cache_read_tokens,
            n_output_tokens=totals.output_tokens,
            cost_usd=session.reported_cost(totals.cost_usd),
        )
        for model, totals in sorted(usage.models.items())
    }


def convert_trajectory(
    logs_dir: Path,
    *,
    session_dir_name: str,
    agent_name: str,
    agent_version: str,
    model_name: str | None,
) -> Trajectory | None:
    """Build the ATIF trajectory of the omp session under ``logs_dir``.

    Pre: ``session_dir_name`` is the agent's session-dir option, and
    ``agent_name`` / ``agent_version`` / ``model_name`` are the agent's identity
    — ``model_name`` is only the default for a step whose event names no model.
    Post: one step per non-blank session line, in file order, each carrying its
    decoded payload under ``extra[EVENT_KEY]``, and ``final_metrics`` equal to
    ``session.sum_session_usage``'s totals, so the trajectory and the agent
    context report the same numbers. Returns ``None`` when there is no session
    to convert — no JSONL under either layout, or none with a non-blank line —
    which is *absent*, not an error.

    Raises:
        TrajectoryAccountingError: When a session file could not be read, or
            when a line became no step. A partial artifact is never returned:
            the caller gets the whole session or nothing.
    """

    session_dir = session_dir_in(logs_dir, session_dir_name)
    usage = session.sum_session_usage(session_dir)
    lines, unreadable_files = session.read_session_lines(session_dir)
    if unreadable_files:
        raise TrajectoryAccountingError(
            f"{unreadable_files} session file(s) under {session_dir} could not be "
            "read, so their lines cannot be accounted for; no trajectory is built "
            "from a session it can only partly see"
        )
    if usage is None or not lines:
        return None

    session_id, agent_model = _session_facts(lines, fallback_model=model_name)
    steps, positions = _build_steps(lines, agent_model=agent_model)
    _account(lines, positions)
    return Trajectory(
        schema_version=SCHEMA_VERSION,
        session_id=session_id,
        agent=Agent(name=agent_name, version=agent_version, model_name=agent_model),
        steps=steps,
        notes=NOTES,
        final_metrics=_final_metrics(usage, steps),
    )


def write_trajectory(path: Path, built: Trajectory) -> list[str]:
    """Validate and write a trajectory atomically; return the validation errors.

    Post: when the document validates, ``path`` holds exactly
    ``format_trajectory_json(built.to_json_dict())`` and the return value is
    empty; otherwise ``path`` is left as it was, the temporary file is removed,
    and the return value names every error.

    Harbor's own validator gates the write rather than being a check the suite
    happens to run: what the viewer, ``atif2otel`` and the plugins read is this
    file, so a document their loader would reject never lands. It is validated on
    disk, under a temporary name in the same directory, so the media-path checks
    see where the artifact would really sit.
    """

    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(format_trajectory_json(built.to_json_dict()), encoding="utf-8")
    validator = TrajectoryValidator()
    if validator.validate(temporary):
        temporary.replace(path)
        return []
    errors = validator.get_errors()
    temporary.unlink(missing_ok=True)
    return errors


def _final_metrics(usage: session.SessionUsage, steps: Sequence[Step]) -> FinalMetrics:
    """The trajectory's totals: the session reader's, in the context's convention.

    Deliberately not a second summation over the steps. The reader is the one
    authority on what the session spent — it drops a ``model_usage`` record an
    assistant message already covered, and it covers the auxiliary model, whose
    records ATIF cannot express as step metrics because a ``system`` step may not
    carry them. Summing the steps here would report less than the trial spent,
    with nothing in the artifact to show that it had.
    """

    return FinalMetrics(
        total_prompt_tokens=usage.total_input_tokens,
        total_completion_tokens=usage.output_tokens,
        total_cached_tokens=usage.cache_read_tokens,
        total_cost_usd=session.reported_cost(usage.cost_usd),
        total_steps=len(steps),
        extra={
            "omp_steps": usage.steps,
            "omp_files_read": usage.files_read,
            "cache_write_tokens": usage.cache_write_tokens,
            "models": {model: row.model_dump() for model, row in model_usage(usage).items()},
        },
    )


def _session_facts(
    lines: Sequence[session.SessionLine], *, fallback_model: str | None
) -> tuple[str | None, str | None]:
    """The session id and the root model name, from the session's own events.

    The root model is the one the assistant messages carry when the session names
    one — those are the records the totals are attributed to — falling back to
    the ``model_change`` the run started with, and then to the model the agent
    ran with. It is only a default: an agent step that names its own model keeps
    it.
    """

    session_id: str | None = None
    changed: str | None = None
    assistant: str | None = None
    for line in lines:
        event = line.event
        if event is None:
            continue
        kind = event.get("type")
        if kind == "session" and session_id is None:
            session_id = _text(event.get("id"))
        elif kind == "model_change" and changed is None:
            changed = _text(event.get("model"))
        elif kind == "message" and assistant is None:
            message = event.get("message")
            if isinstance(message, dict) and message.get("role") == "assistant":
                assistant = _text(message.get("model"))
    return session_id, assistant or changed or fallback_model


def _build_steps(
    lines: Sequence[session.SessionLine], *, agent_model: str | None
) -> tuple[list[Step], list[int]]:
    """The steps for the session's lines, and the line position each came from.

    Two pieces of session state carry forward: the model the last
    ``model_change`` named, which is the fallback for an agent step whose message
    names none, and the thinking level the last ``thinking_level_change``
    configured, which agent steps record as ``reasoning_effort``.
    """

    steps: list[Step] = []
    positions: list[int] = []
    model = agent_model
    thinking: str | None = None
    for position, line in enumerate(lines, start=1):
        event = line.event
        if event is not None:
            kind = event.get("type")
            if kind == "model_change":
                model = _text(event.get("model")) or model
            elif kind == "thinking_level_change":
                thinking = _text(event.get("thinkingLevel")) or thinking
        step = _step_for(line, position, model=model, thinking=thinking)
        if step is not None:
            steps.append(step)
            positions.append(position)
    return steps, positions


def _account(lines: Sequence[session.SessionLine], positions: Sequence[int]) -> None:
    """Refuse a trajectory whose steps do not account for every session line.

    The invariant is a bijection between non-blank lines and steps, in order, and
    it is checked rather than assumed: a line that became nothing would otherwise
    be invisible, because what results is a valid ATIF document that simply holds
    a shorter session than the log it names.
    """

    accounted = set(positions)
    missing = [line for position, line in enumerate(lines, start=1) if position not in accounted]
    if not missing:
        return
    named = ", ".join(
        line.site if line.event is not None else f"{line.site} (not a JSON object)"
        for line in missing
    )
    raise TrajectoryAccountingError(
        f"{len(missing)} of {len(lines)} session line(s) became no step: {named}; "
        "refusing a trajectory that would be shorter than the session it claims"
    )


def _step_for(
    line: session.SessionLine,
    position: int,
    *,
    model: str | None,
    thinking: str | None,
) -> Step | None:
    """The one step a session line becomes, or ``None`` when it cannot become one.

    A line that is not a JSON object has no event to carry, so it becomes no
    step; the caller's accounting turns that into a refusal. Every event that
    does decode becomes exactly one step: a ``message`` event (whose payload is a
    message object) becomes a conversation step, and everything else becomes a
    ``system`` step.
    """

    event = line.event
    if event is None:
        return None
    if event.get("type") == "message":
        message = event.get("message")
        if isinstance(message, dict):
            return _message_step(position, event, message, model=model, thinking=thinking)
    return _system_step(position, event)


def _message_step(
    position: int,
    event: dict[str, Any],
    message: dict[str, Any],
    *,
    model: str | None,
    thinking: str | None,
) -> Step:
    """One ``message`` event as a conversation step.

    ``user`` and ``assistant`` land on ATIF's ``user`` and ``agent``; every other
    role — omp's ``toolResult``, or one a later version adds — becomes a
    ``system`` step, because ATIF has no fourth source and the line must still be
    exactly one step. The role itself is kept in ``extra["omp_role"]``, and a
    tool result names its call in ``extra["omp_tool_call_id"]``.
    """

    role = _text(message.get("role"))
    extra: dict[str, Any] = {
        EVENT_KEY: event,
        "omp_event_type": "message",
        "omp_role": role,
    }
    if role == "toolResult":
        extra["omp_tool_call_id"] = _text(message.get("toolCallId"))
        extra["omp_tool_name"] = _text(message.get("toolName"))
        extra["omp_is_error"] = bool(message.get("isError", False))
    if role != "assistant":
        return Step(
            step_id=position,
            timestamp=_timestamp(event),
            source=_source_for(role),
            message=_text_of(message.get("content")),
            extra=extra,
        )
    blocks = _blocks(message.get("content"))
    return Step(
        step_id=position,
        timestamp=_timestamp(event),
        source="agent",
        model_name=_text(message.get("model")) or model,
        reasoning_effort=thinking,
        message=_joined(blocks, "text"),
        reasoning_content=_joined(blocks, "thinking") or None,
        tool_calls=_tool_calls(blocks) or None,
        metrics=_metrics(message.get("usage")),
        llm_call_count=1,
        extra=extra,
    )


def _system_step(position: int, event: dict[str, Any]) -> Step:
    """One non-conversation event as a ``system`` step, its payload intact.

    ``system`` because that is what these events are: session lifecycle,
    configuration changes, a tool dispatch, an auxiliary model's usage record —
    none of them a user turn, none of them a turn of the trial's own model.
    """

    kind = _text(event.get("type"))
    extra: dict[str, Any] = {EVENT_KEY: event, "omp_event_type": kind}
    if kind in ("custom", "custom_message"):
        extra["omp_custom_type"] = _text(event.get("customType"))
    if kind == "custom":
        data = event.get("data")
        if isinstance(data, dict):
            extra["omp_tool_call_id"] = _text(data.get("toolCallId"))
            extra["omp_tool_name"] = _text(data.get("toolName"))
    elif kind == "model_usage":
        extra["omp_model"] = _text(event.get("model"))
    return Step(
        step_id=position,
        timestamp=_timestamp(event),
        source="system",
        message=_render(event),
        extra=extra,
    )


def _source_for(role: str | None) -> str:
    """The ATIF source a message role maps to."""

    if role == "user":
        return "user"
    if role == "assistant":
        return "agent"
    return "system"


def _render(event: dict[str, Any]) -> str:
    """One line describing a system event: its type, and what the event names.

    A rendering, not a claim — the event is under ``extra[EVENT_KEY]`` verbatim,
    and every rendering starts with the event's type, so a reader can tell an
    event's rendering from a message's own text. ``custom_message`` is the
    exception: its content *is* the text omp injected into the session, so that
    content is the step's message.
    """

    kind = _text(event.get("type")) or "unnamed"
    if kind == "custom_message":
        content = _text_of(event.get("content"))
        if content:
            return content
    named: list[str] = []
    for label, key in _NAMED_FIELDS.get(kind, ()):
        value = event.get(key)
        if value is not None:
            named.append(f"{label}={value!r}")
    if kind == "custom":
        data = event.get("data")
        if isinstance(data, dict):
            for label, key in _NAMED_DATA_FIELDS:
                value = _text(data.get(key))
                if value is not None:
                    named.append(f"{label}={value!r}")
    return f"{kind}: {', '.join(named)}" if named else kind


def _timestamp(event: dict[str, Any]) -> str | None:
    """The event's ISO 8601 timestamp, or None when it has none this model takes.

    ``updatedAt`` is the fallback for the events omp stamps only that way (the
    ``title`` events). An unparseable value yields None rather than an exception:
    the value itself is in the raw payload, and a bad clock reading must not cost
    the session its trajectory.
    """

    for key in ("timestamp", "updatedAt"):
        value = _text(event.get(key))
        if value is None:
            continue
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return value
    return None


def _metrics(usage: object) -> Metrics | None:
    """A ``message.usage`` record as ATIF metrics, or None when there is none.

    ``prompt_tokens`` is cache-inclusive, as ATIF defines it and as
    ``AgentContext.n_input_tokens`` reports it; ``extra`` carries the two numbers
    ATIF has no field for (cache writes, reasoning tokens).
    """

    if not isinstance(usage, dict):
        return None
    cached = _int(usage.get("cacheRead"))
    written = _int(usage.get("cacheWrite"))
    cost = usage.get("cost")
    total = cost.get("total") if isinstance(cost, dict) else None
    return Metrics(
        prompt_tokens=_int(usage.get("input")) + cached + written,
        completion_tokens=_int(usage.get("output")),
        cached_tokens=cached,
        cost_usd=session.number(total),
        extra={
            "cache_write_tokens": written,
            "reasoning_tokens": _int(usage.get("reasoningTokens")),
        },
    )


def _blocks(content: object) -> list[dict[str, Any]]:
    """The dict blocks of a message's content, in order."""

    if not isinstance(content, list):
        return []
    return [block for block in content if isinstance(block, dict)]


def _joined(blocks: Sequence[dict[str, Any]], key: str) -> str:
    """Every block of one type, joined — ``""`` when there are none.

    A block type ATIF cannot express (or a malformed one) contributes nothing
    here; it is in the step's raw payload either way.
    """

    texts = [
        block[key]
        for block in blocks
        if block.get("type") == key and isinstance(block.get(key), str)
    ]
    return "\n".join(texts)


def _text_of(content: object) -> str:
    """A message's text content: a string as-is, or its ``text`` blocks joined."""

    if isinstance(content, str):
        return content
    return _joined(_blocks(content), "text")


def _tool_calls(blocks: Sequence[dict[str, Any]]) -> list[ToolCall]:
    """The tool calls an assistant message carries, in order.

    A block without an id or a function name is not a usable call — it is left to
    the raw payload rather than published with a placeholder name.
    """

    calls: list[ToolCall] = []
    for block in blocks:
        if block.get("type") != "toolCall":
            continue
        call_id = _text(block.get("id"))
        function_name = _text(block.get("name"))
        if call_id is None or function_name is None:
            continue
        arguments = block.get("arguments")
        calls.append(
            ToolCall(
                tool_call_id=call_id,
                function_name=function_name,
                arguments=arguments if isinstance(arguments, dict) else {},
            )
        )
    return calls


def _text(value: object) -> str | None:
    """A non-blank string, or None — the same rule the reader's model names use."""

    if isinstance(value, str) and value.strip():
        return value
    return None


def _int(value: object) -> int:
    """A token count as an int; unreadable and absent both count as zero.

    Zero is the reader's convention for a field it cannot read
    (``SessionUsage.skipped_values`` is how a caller notices), so the step and
    the totals cannot disagree about what an unreadable field contributed.
    """

    parsed = session.number(value)
    return int(parsed) if parsed is not None else 0
