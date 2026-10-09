"""Populating ``AgentContext`` from the session directory.

This is the only metric source for a non-streaming run, so it is asserted
against the fixture's literal numbers rather than against the reader. The
fixture is a redacted excerpt of a real session (see ``test_session.py``), so
its two ``message.usage`` records and its one auxiliary ``model_usage`` record
are the ones omp wrote.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from conftest import MODEL
from harbor.models.agent.context import AgentContext

from harbor_omp import OmpAgent

FIXTURE = Path(__file__).parent / "fixtures" / "omp_session.jsonl"

FIXTURE_TOTAL_INPUT = 8807 + 5627 + 8960
FIXTURE_TOTAL_OUTPUT = 446 + 1220
FIXTURE_CACHE_READ = 8960
FIXTURE_TOTAL_COST = 0.0004011878 + 0.0004024399 + 0.000236334
FIXTURE_STEPS = 2


def _agent(logs_dir: Path, **options: object) -> OmpAgent:
    return OmpAgent(logs_dir=logs_dir, model_name=MODEL, **options)


def _with_fixture(logs_dir: Path, session_dir_name: str = "omp-sessions") -> Path:
    directory = logs_dir / session_dir_name
    directory.mkdir(parents=True)
    shutil.copy(FIXTURE, directory / "session.jsonl")
    return directory


def test_the_context_gets_the_tokens_cache_cost_and_steps(tmp_path: Path) -> None:
    """Every field Harbor reports comes from here, including cache included in
    the input total — and including the auxiliary model's tokens, which are
    additional to the assistant messages'."""
    logs_dir = tmp_path / "logs"
    _with_fixture(logs_dir)
    context = AgentContext()

    _agent(logs_dir).populate_context_post_run(context)

    assert context.n_input_tokens == FIXTURE_TOTAL_INPUT
    assert context.n_output_tokens == FIXTURE_TOTAL_OUTPUT
    assert context.n_cache_tokens == FIXTURE_CACHE_READ
    assert context.cost_usd == round(FIXTURE_TOTAL_COST, 6)
    assert context.metadata == {"omp_steps": FIXTURE_STEPS}


def test_the_context_carries_the_per_model_usage_breakdown(tmp_path: Path) -> None:
    """Harbor's per-model seam (``AgentContext.model_usage``) is the same
    session pass, so an auxiliary model is visible without an ATIF trajectory."""
    logs_dir = tmp_path / "logs"
    _with_fixture(logs_dir)
    context = AgentContext()

    _agent(logs_dir).populate_context_post_run(context)

    assert context.model_usage is not None
    assert sorted(context.model_usage) == [
        "deepseek/deepseek-v4-flash",
        "~typesafe/jev-latest",
    ]
    auxiliary = context.model_usage["~typesafe/jev-latest"]
    assert auxiliary.n_input_tokens == 5627
    assert auxiliary.n_output_tokens == 1220
    assert auxiliary.n_cache_tokens == 0
    assert auxiliary.cost_usd == 0.000236

    own = context.model_usage["deepseek/deepseek-v4-flash"]
    assert own.n_input_tokens == 8807 + FIXTURE_CACHE_READ
    assert own.n_output_tokens == 446
    assert own.n_cache_tokens == FIXTURE_CACHE_READ
    assert own.cost_usd == 0.000804


def test_the_session_dir_name_option_is_where_it_reads(tmp_path: Path) -> None:
    """A trial that moved the session dir still gets its metrics."""
    logs_dir = tmp_path / "logs"
    _with_fixture(logs_dir, session_dir_name="my-sessions")
    context = AgentContext()

    _agent(logs_dir, session_dir_name="my-sessions").populate_context_post_run(context)

    assert context.n_input_tokens == FIXTURE_TOTAL_INPUT
    assert context.metadata == {"omp_steps": FIXTURE_STEPS}


def test_a_run_with_no_session_leaves_the_context_empty(tmp_path: Path) -> None:
    """Absent metrics stay absent — the trial reports no tokens rather than
    zero, and the post-run step never raises over a missing directory."""
    context = AgentContext()

    _agent(tmp_path / "logs").populate_context_post_run(context)

    assert context.is_empty()


def test_an_unreadable_session_leaves_the_context_empty(tmp_path: Path) -> None:
    """A session nobody can read is absent, not a confident free run: Harbor's
    ``is_empty()`` must stay true rather than reporting zero tokens."""
    logs_dir = tmp_path / "logs"
    directory = logs_dir / "omp-sessions"
    directory.mkdir(parents=True)
    (directory / "session.jsonl").write_bytes(b'{"type":"session"}\xff\xfe\n')
    context = AgentContext()

    _agent(logs_dir).populate_context_post_run(context)

    assert context.is_empty()


def test_a_session_that_reported_no_cost_reports_no_cost(tmp_path: Path) -> None:
    """Zero cost from omp means "not reported", so Harbor shows nothing rather
    than a confident 0.0."""
    logs_dir = tmp_path / "logs"
    directory = logs_dir / "omp-sessions"
    directory.mkdir(parents=True)
    (directory / "session.jsonl").write_text(
        '{"type":"message","message":{"role":"assistant","model":"m/x","usage":'
        '{"input":10,"output":3,"cacheRead":0,"cacheWrite":0,'
        '"cost":{"total":0}}}}\n',
        encoding="utf-8",
    )
    context = AgentContext()

    _agent(logs_dir).populate_context_post_run(context)

    assert context.n_input_tokens == 10
    assert context.n_output_tokens == 3
    assert context.cost_usd is None
    assert context.metadata == {"omp_steps": 1}
    assert context.model_usage is not None
    assert context.model_usage["m/x"].cost_usd is None
