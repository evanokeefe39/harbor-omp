"""Shipping config content and seeding the isolated config home.

Config content is a HOST git checkout shipped by committed HEAD, restricted to
the caller's pathspecs, extracted into ``<config_home>/.omp`` after the home is
reset. A pin that cannot land aborts the trial before any upload and before any
model spend; a config ship that names nothing is refused rather than shipping
nothing silently.
"""

from __future__ import annotations

import asyncio
import io
import json
import tarfile
from pathlib import Path

import pytest
from conftest import RecordingEnvironment

from harbor_omp.omp_agent import (
    CONFIG_SOURCE_RECORD,
    CONFIG_TAR,
    SEED_DIR,
)

CONFIG_PATHS = ["agent/AGENTS.md", "agent/skills/duckdb/"]
EXPECTED_MEMBERS = {"agent/AGENTS.md", "agent/skills/duckdb/SKILL.md"}


def _agent_with_config(make_agent, repo: Path, **options: object):
    return make_agent(config_source=str(repo), config_paths=list(CONFIG_PATHS), **options)


def test_a_clean_checkout_ships_exactly_the_named_paths(make_agent, config_repo) -> None:
    """The committed HEAD of exactly the named paths ships — the hooks'
    ``__tests__`` directory that the caller did not name never travels."""
    repo, sha = config_repo
    env = RecordingEnvironment()

    asyncio.run(_agent_with_config(make_agent, repo).install(env))

    assert env.uploaded[CONFIG_TAR.as_posix()], "the config tar was never uploaded"
    with tarfile.open(fileobj=io.BytesIO(env.uploaded[CONFIG_TAR.as_posix()])) as tar:
        members = {member.name for member in tar.getmembers() if member.isfile()}
    assert members == EXPECTED_MEMBERS

    record = json.loads(env.uploaded[CONFIG_SOURCE_RECORD.as_posix()])
    assert record == {"commit": sha, "src": str(repo), "paths": list(CONFIG_PATHS)}


def test_the_shipped_content_lands_after_the_home_reset(make_agent, config_repo) -> None:
    """The home reset wipes the config dir; the extract must run after it, into
    the config dir, as the agent user — otherwise the shipped content is what
    was wiped."""
    repo, _ = config_repo
    env = RecordingEnvironment()

    asyncio.run(_agent_with_config(make_agent, repo).install(env))

    reset = env.index_of_first("exec", "rm -rf /tmp/omp-home")
    extract = env.index_of_first("exec", f"tar -xf {CONFIG_TAR.as_posix()}")
    assert reset < extract
    extract_command = env.commands_matching(f"tar -xf {CONFIG_TAR.as_posix()}")[0]
    assert "-C /tmp/omp-home/.omp" in extract_command
    assert all(
        entry["user"] != "root"
        for entry in env.execs
        if CONFIG_TAR.as_posix() in str(entry["command"])
    )


def test_a_missing_pinned_path_aborts_naming_it(make_agent, config_repo) -> None:
    """A named path absent from the committed HEAD cannot be shipped: the trial
    aborts naming it, before any upload."""
    repo, _ = config_repo
    env = RecordingEnvironment()
    agent = make_agent(
        config_source=str(repo),
        config_paths=[*CONFIG_PATHS, "agent/skills/missing/"],
    )

    with pytest.raises(ValueError, match="agent/skills/missing"):
        asyncio.run(agent.install(env))

    assert env.uploads == []


def test_a_dirty_pinned_file_aborts_before_any_upload(make_agent, config_repo) -> None:
    """An uncommitted change to a shipped file means the content would not be
    what was reviewed."""
    repo, _ = config_repo
    (repo / "agent" / "AGENTS.md").write_text("modified, uncommitted\n", encoding="utf-8")
    env = RecordingEnvironment()

    with pytest.raises(ValueError, match="uncommitted"):
        asyncio.run(_agent_with_config(make_agent, repo).install(env))

    assert env.uploads == []


def test_a_source_without_paths_is_refused(make_agent, config_repo) -> None:
    """A config ship that names nothing would silently ship nothing, so it is
    an error, not an empty tar."""
    repo, _ = config_repo
    env = RecordingEnvironment()

    with pytest.raises(ValueError, match="config_paths"):
        asyncio.run(make_agent(config_source=str(repo)).install(env))

    assert env.uploads == []


def test_no_source_means_no_config_calls(make_agent) -> None:
    """A trial with no config source ships no tar, writes no record, and runs
    no extract — the config dir is still reset, so it is empty by construction."""
    env = RecordingEnvironment()
    agent = make_agent()

    asyncio.run(agent.install(env))

    assert env.uploads_matching("config") == []
    assert env.commands_matching(f"tar -xf {CONFIG_TAR.as_posix()}") == []
    assert len(env.commands_matching("rm -rf /tmp/omp-home")) == 1


def test_the_seed_is_written_into_the_config_home(make_agent) -> None:
    """The seed is plain data: each entry is uploaded beside the others and
    copied into the config dir after the reset."""
    env = RecordingEnvironment()
    agent = make_agent(seed={"omp.json": '{"model": "x"}\n', "agent/config.yml": "task: {}\n"})

    asyncio.run(agent.install(env))

    assert env.uploads_matching(f"{SEED_DIR.as_posix()}/omp.json") == [
        f"{SEED_DIR.as_posix()}/omp.json"
    ]
    assert env.uploads_matching(f"{SEED_DIR.as_posix()}/agent/config.yml") == [
        f"{SEED_DIR.as_posix()}/agent/config.yml"
    ]
    assert env.uploaded[f"{SEED_DIR.as_posix()}/omp.json"] == b'{"model": "x"}\n'

    script = agent._config_home_command()
    seed = SEED_DIR.as_posix()
    config_dir = "/tmp/omp-home/.omp"
    assert f"cp -a {seed}/. {config_dir}/" in script
    assert script.index("rm -rf /tmp/omp-home") < script.index(f"cp -a {seed}/. {config_dir}/"), (
        "the seed must be copied in after the reset"
    )


@pytest.mark.parametrize(
    "bad_path",
    ["/etc/passwd", "../outside.md", "agent\\config.yml"],
)
def test_a_seed_path_that_escapes_or_uses_backslashes_is_refused(make_agent, bad_path: str) -> None:
    """An upload target a caller did not mean is a silent misconfig, so it is
    refused before anything is uploaded."""
    env = RecordingEnvironment()

    with pytest.raises(ValueError, match="seed path"):
        asyncio.run(make_agent(seed={bad_path: "x"}).install(env))

    assert env.uploads == []


def test_no_seed_means_no_seed_uploads(make_agent) -> None:
    """Without a seed nothing is uploaded, and the config dir is simply empty."""
    env = RecordingEnvironment()
    agent = make_agent()

    asyncio.run(agent.install(env))

    assert env.uploads_matching(SEED_DIR.as_posix()) == []
    assert "cp -a" not in agent._config_home_command()
