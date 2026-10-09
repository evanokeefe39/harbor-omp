"""Shipping a plugin from a host checkout into the trial container.

A plugin source is a HOST path to a git checkout (private repos cannot be
installed by URL, and the sandbox has no host mounts). The adapter must ship
the committed HEAD — verify clean, ``git archive``, upload, extract as the agent
user — and the config-home step installs and configures it from the container
path, so no host path ever reaches the container command.
"""

from __future__ import annotations

import asyncio
import io
import json
import tarfile
from pathlib import Path

import pytest
from conftest import RecordingEnvironment, git

from harbor_omp.omp_agent import (
    CONFIG_DIR_NAME,
    PLUGIN_DIR,
    PLUGIN_SOURCE_RECORD,
    PLUGIN_TAR,
)

INDEX_TS = b"export const name = 'demo-plugin';\n"


def _plugin_options(source: Path, **extra: object) -> dict[str, object]:
    """The options of a trial that ships a plugin.

    ``run_flags`` is explicit because the default recipe includes
    ``--no-extensions``, which also gates plugin loading: ``OmpOptions``
    refuses a plugin that would install and never load.
    """
    plugin: dict[str, object] = {"name": "demo-plugin", "src": str(source)}
    plugin.update(extra)
    return {"plugin": plugin, "run_flags": []}


def test_a_clean_checkout_is_archived_uploaded_extracted_and_recorded(
    make_agent, plugin_repo
) -> None:
    """The committed tree is what ships: the tar holds the committed file, the
    extraction runs as the agent user, and the record names the commit, the
    plugin and the host path the trial ran."""
    repo, sha = plugin_repo
    agent = make_agent(**_plugin_options(repo))
    env = RecordingEnvironment()

    asyncio.run(agent.install(env))

    assert env.uploads_matching(PLUGIN_TAR.as_posix()) == [PLUGIN_TAR.as_posix()]
    with tarfile.open(fileobj=io.BytesIO(env.uploaded[PLUGIN_TAR.as_posix()])) as tar:
        member = tar.getmember("index.ts")
        assert member.isfile()
        extracted = tar.extractfile(member).read()
    # git archive honours the host's core.autocrlf, so compare normalised.
    assert extracted.replace(b"\r\n", b"\n") == INDEX_TS

    extract_commands = env.commands_matching(f"tar -xf {PLUGIN_TAR.as_posix()}")
    assert len(extract_commands) == 1
    assert f"-C {PLUGIN_DIR.as_posix()}" in extract_commands[0]
    assert f"mkdir -p {PLUGIN_DIR.as_posix()}" in extract_commands[0]
    # The extraction runs under the agent user (exec_as_agent passes user=None,
    # so the environment resolves its default agent user — never root here).
    assert all(
        entry["user"] != "root"
        for entry in env.execs
        if PLUGIN_TAR.as_posix() in str(entry["command"])
    )

    record = json.loads(env.uploaded[PLUGIN_SOURCE_RECORD.as_posix()])
    assert record == {"name": "demo-plugin", "commit": sha, "src": str(repo)}


def test_the_config_home_step_installs_enables_and_configures_the_plugin(
    make_agent, plugin_repo
) -> None:
    """The plugin is installed from the container path, enabled by name, and
    every setting is passed through as a string omp understands."""
    repo, _ = plugin_repo
    agent = make_agent(
        **_plugin_options(repo, settings={"router": True, "verbose": False, "level": "fast"})
    )

    script = agent._config_home_command()

    assert f"omp install {PLUGIN_DIR.as_posix()}" in script
    assert "omp plugin enable demo-plugin" in script
    assert "omp plugin config set demo-plugin level fast" in script
    assert "omp plugin config set demo-plugin router true" in script
    assert "omp plugin config set demo-plugin verbose false" in script
    # The install runs under the isolated home, like the agent does.
    assert f"HOME=/tmp/omp-home PI_CONFIG_DIR={CONFIG_DIR_NAME}" in script


def test_a_dirty_checkout_aborts_before_any_upload(make_agent, plugin_repo) -> None:
    """An uncommitted change to a tracked file means the pinned content would
    not be what runs, so nothing is uploaded and no model spend happens."""
    repo, _ = plugin_repo
    (repo / "index.ts").write_bytes(b"modified, uncommitted\n")
    env = RecordingEnvironment()

    with pytest.raises(ValueError, match="uncommitted"):
        asyncio.run(make_agent(**_plugin_options(repo)).install(env))

    assert env.uploads == []
    assert env.execs == []


def test_a_src_that_is_not_a_git_work_tree_aborts(make_agent, tmp_path: Path) -> None:
    """A src that is not a checkout cannot be archived: the trial refuses to
    guess, before any upload."""
    src = tmp_path / "not-a-repo"
    src.mkdir()
    (src / "index.ts").write_bytes(INDEX_TS)
    env = RecordingEnvironment()

    with pytest.raises(ValueError, match="not a git work tree"):
        asyncio.run(make_agent(**_plugin_options(src)).install(env))

    assert env.uploads == []


def test_a_plugin_without_a_name_aborts(make_agent, plugin_repo) -> None:
    """The config-home step cannot enable a plugin it cannot name."""
    repo, _ = plugin_repo
    env = RecordingEnvironment()

    with pytest.raises(ValueError, match="plugin.name"):
        asyncio.run(make_agent(**{"plugin": {"src": str(repo)}, "run_flags": []}).install(env))

    assert env.uploads == []


def test_a_plugin_without_a_source_aborts(make_agent) -> None:
    """A plugin pin without a source cannot land."""
    env = RecordingEnvironment()

    with pytest.raises(ValueError, match="plugin.src"):
        asyncio.run(make_agent(**{"plugin": {"name": "demo-plugin"}, "run_flags": []}).install(env))

    assert env.uploads == []


def test_no_plugin_means_no_plugin_calls(make_agent) -> None:
    """A trial with no plugin ships no plugin tar, writes no plugin record,
    runs no plugin command, and the config-home step installs nothing."""
    env = RecordingEnvironment()
    agent = make_agent()

    asyncio.run(agent.install(env))

    assert env.uploads_matching("plugin") == []
    assert env.commands_matching("plugin") == []
    script = agent._config_home_command()
    assert "omp install" not in script
    assert "omp plugin" not in script


def test_the_newest_commit_is_what_ships(make_agent, plugin_repo) -> None:
    """The archive follows HEAD: after a second commit, the shipped tar and the
    recorded commit are the new ones."""
    repo, first_sha = plugin_repo
    (repo / "index.ts").write_bytes(b"export const name = 'v2';\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "v2")
    second_sha = git(repo, "rev-parse", "HEAD")
    env = RecordingEnvironment()

    asyncio.run(make_agent(**_plugin_options(repo)).install(env))

    with tarfile.open(fileobj=io.BytesIO(env.uploaded[PLUGIN_TAR.as_posix()])) as tar:
        shipped = tar.extractfile("index.ts").read()
    assert shipped.replace(b"\r\n", b"\n") == b"export const name = 'v2';\n"
    record = json.loads(env.uploaded[PLUGIN_SOURCE_RECORD.as_posix()])
    assert record["commit"] == second_sha
    assert second_sha != first_sha


def test_an_untracked_file_neither_blocks_nor_ships(make_agent, plugin_repo) -> None:
    """Untracked work is not an uncommitted change to a tracked file: it must
    not block the ship, and it must not travel into the container."""
    repo, _ = plugin_repo
    (repo / "notes.local.md").write_text("scratch\n", encoding="utf-8")
    env = RecordingEnvironment()

    asyncio.run(make_agent(**_plugin_options(repo)).install(env))

    with tarfile.open(fileobj=io.BytesIO(env.uploaded[PLUGIN_TAR.as_posix()])) as tar:
        names = {member.name for member in tar.getmembers()}
    assert "notes.local.md" not in names
    assert "index.ts" in names
