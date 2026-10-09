"""Populating ``AgentContext`` from the session directory.

This is the only metric source for a non-streaming run, so it is asserted
against the fixture's literal numbers rather than against the reader.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from conftest import MODEL
from harbor.models.agent.context import AgentContext

from harbor_omp import OmpAgent

FIXTURE = Path(__file__).parent / "fixtures" / "omp_session.jsonl"


def _agent(logs_dir: Path, **options: object) -> OmpAgent:
    return OmpAgent(logs_dir=logs_dir, model_name=MODEL, **options)


def _with_fixture(logs_dir: Path, session_dir_name: str = "omp-sessions") -> Path:
    directory = logs_dir / session_dir_name
    directory.mkdir(parents=True)
    shutil.copy(FIXTURE, directory / "session.jsonl")
    return directory


def test_the_context_gets_the_tokens_cache_cost_and_steps(tmp_path: Path) -> None:
    """Every field Harbor reports comes from here, including cache included in
    the input total."""
    logs_dir = tmp_path / "logs"
    _with_fixture(logs_dir)
    context = AgentContext()

    _agent(logs_dir).populate_context_post_run(context)

    assert context.n_input_tokens == 150 + 3500 + 200
    assert context.n_output_tokens == 60
    assert context.n_cache_tokens == 3500
    assert context.cost_usd == 0.04
    assert context.metadata == {"omp_steps": 2}


def test_the_session_dir_name_option_is_where_it_reads(tmp_path: Path) -> None:
    """A trial that moved the session dir still gets its metrics."""
    logs_dir = tmp_path / "logs"
    _with_fixture(logs_dir, session_dir_name="my-sessions")
    context = AgentContext()

    _agent(logs_dir, session_dir_name="my-sessions").populate_context_post_run(context)

    assert context.n_input_tokens == 150 + 3500 + 200
    assert context.metadata == {"omp_steps": 2}


def test_a_run_with_no_session_leaves_the_context_empty(tmp_path: Path) -> None:
    """Absent metrics stay absent — the trial reports no tokens rather than
    zero, and the post-run step never raises over a missing directory."""
    context = AgentContext()

    _agent(tmp_path / "logs").populate_context_post_run(context)

    assert context.is_empty()


def test_a_session_that_reported_no_cost_reports_no_cost(tmp_path: Path) -> None:
    """Zero cost from omp means "not reported", so Harbor shows nothing rather
    than a confident 0.0."""
    logs_dir = tmp_path / "logs"
    directory = logs_dir / "omp-sessions"
    directory.mkdir(parents=True)
    (directory / "session.jsonl").write_text(
        '{"message":{"usage":{"input":10,"output":3,"cacheRead":0,"cacheWrite":0,'
        '"cost":{"total":0}}}}\n',
        encoding="utf-8",
    )
    context = AgentContext()

    _agent(logs_dir).populate_context_post_run(context)

    assert context.n_input_tokens == 10
    assert context.n_output_tokens == 3
    assert context.cost_usd is None
    assert context.metadata == {"omp_steps": 1}
