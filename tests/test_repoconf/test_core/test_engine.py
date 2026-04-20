"""Engine tests covering branch-to-proxy synchronization behavior."""

from __future__ import annotations

import configparser
from pathlib import Path
from typing import Generator

import pytest

from repoconf.constants import BACKEND_DIR_NAME, CONFIG_BRANCH, CONFIG_REF, INCLUDE_PATH
from repoconf.core.engine import ConfigEngine
from repoconf.providers.protocol import GitCmdException


class GitConfigParser(configparser.ConfigParser):
    """ConfigParser variant that preserves Git option casing."""

    def optionxform(self, optionstr: str) -> str:
        return optionstr


def write_git_config_value(path: Path, key: str, value: str) -> None:
    """Write a Git-style ``section.key`` value to a config file."""
    parser = GitConfigParser()
    if path.exists():
        parser.read(path, encoding="utf-8")

    section, option = key.split(".", 1)
    if not parser.has_section(section):
        parser.add_section(section)
    parser.set(section, option, value)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        parser.write(handle)


def read_git_config_value(path: Path, key: str) -> str:
    """Read a Git-style ``section.key`` value from a config file."""
    parser = GitConfigParser()
    parser.read(path, encoding="utf-8")

    section, option = key.split(".", 1)
    return parser.get(section, option)


class FakeGitProvider:
    """Minimal provider that emulates the engine-facing Git behavior."""

    def __init__(
        self,
        repo_root: Path,
        branch: str = CONFIG_BRANCH,
        managed_file_name: str = "repoconf.config",
    ) -> None:
        self.git_root_dir = repo_root
        self.git_dir = repo_root / ".git"
        self.branch = branch
        self.managed_file_name = managed_file_name
        self.include_paths: list[str] = []
        self.branch_blobs: dict[tuple[str, str], str] = {}
        self.commit_messages: list[str] = []
        self.ensure_worktree_calls = 0
        self.last_hashed_file: Path | None = None
        self.last_commit_env: dict[str, str] | None = None

    @property
    def proxy_path(self) -> Path:
        return self.git_dir / self.managed_file_name

    @property
    def backend_path(self) -> Path:
        return self.git_dir / BACKEND_DIR_NAME

    def seed_branch_value(self, key: str, value: str) -> None:
        """Seed a value directly in the managed branch snapshot."""
        seed_path = self.git_dir / "branch_seed.config"
        seed_path.unlink(missing_ok=True)
        existing_content = self.branch_blobs.get((self.branch, self.managed_file_name))
        if existing_content is not None:
            seed_path.write_text(existing_content, encoding="utf-8")
        write_git_config_value(seed_path, key, value)
        self.branch_blobs[(self.branch, self.managed_file_name)] = seed_path.read_text(
            encoding="utf-8"
        )
        seed_path.unlink(missing_ok=True)

    def run_unchecked(
        self,
        args: list[str],
        env: dict[str, str] | None = None,
        input: str | None = None,
    ) -> str:
        del input

        if args == ["rev-parse", "--git-dir"]:
            return f"{self.git_dir}\n"

        if args[:4] == ["config", "--local", "--get-all", "include.path"]:
            if not self.include_paths:
                raise GitCmdException("include.path is not set")
            return "\n".join(self.include_paths) + "\n"

        if args[:4] == ["config", "--local", "--add", "include.path"]:
            self.include_paths.append(args[4])
            return ""

        if len(args) == 5 and args[:2] == ["config", "--file"]:
            write_git_config_value(Path(args[2]), args[3], args[4])
            return ""

        if args[:2] == ["config", "--get"]:
            if not self.include_paths:
                raise GitCmdException(f"Key {args[2]} not found")
            include_path = Path(self.include_paths[-1])
            if not include_path.is_absolute():
                include_path = (self.git_dir / include_path).resolve()
            try:
                return read_git_config_value(include_path, args[2]) + "\n"
            except (configparser.Error, ValueError):
                raise GitCmdException(f"Key {args[2]} not found") from None

        if args[:2] == ["hash-object", "-w"]:
            self.last_hashed_file = Path(args[2])
            return "blob-sha\n"

        if args == ["rev-parse", "-q", "--verify", CONFIG_REF]:
            if (self.branch, self.managed_file_name) not in self.branch_blobs:
                raise GitCmdException(f"Ref {CONFIG_REF} not found")
            return "parent-sha\n"

        if args[:1] == ["read-tree"]:
            return ""

        if args[:1] == ["update-index"]:
            return ""

        if args == ["write-tree"]:
            return "tree-sha\n"

        if args[:1] == ["commit-tree"]:
            self.last_commit_env = env
            self.commit_messages.append(args[args.index("-m") + 1])
            return "commit-sha\n"

        raise AssertionError(f"Unexpected git command: {args}")

    def ensure_worktree(self, branch: str, path: Path) -> None:
        del branch, path
        self.ensure_worktree_calls += 1

    def read_blob(self, branch: str, path: str) -> str | None:
        return self.branch_blobs.get((branch, path))

    def update_ref(self, ref: str, new_sha: str) -> None:
        del new_sha
        if self.last_hashed_file is None:
            raise AssertionError("hash-object must run before update_ref")
        branch = ref.removeprefix("refs/heads/")
        self.branch_blobs[(branch, self.managed_file_name)] = (
            self.last_hashed_file.read_text(encoding="utf-8")
        )

    def commit_and_push(self, path: Path, message: str) -> None:
        del path, message
        raise AssertionError("ConfigEngine should persist via VirtualStore")


@pytest.fixture
def fake_provider_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """Provide an isolated fake repository with a dedicated git directory."""
    repo_root = tmp_path / "repo"
    git_dir = repo_root / ".git"
    git_dir.mkdir(parents=True)
    yield repo_root


def test_engine_get_syncs_proxy_from_branch(fake_provider_dir: Path) -> None:
    provider = FakeGitProvider(fake_provider_dir)
    provider.seed_branch_value("repoconf.version", "2")
    engine = ConfigEngine(provider)

    engine.proxy_file.write_text("", encoding="utf-8")

    assert engine.get("repoconf_version") == "2"
    assert read_git_config_value(engine.proxy_file, "repoconf.version") == "2"
    assert provider.include_paths == [INCLUDE_PATH]
    assert (provider.git_dir / INCLUDE_PATH).resolve() == engine.proxy_file
    assert provider.ensure_worktree_calls == 0


def test_engine_set_preserves_branch_state_when_proxy_is_stale(
    fake_provider_dir: Path,
) -> None:
    provider = FakeGitProvider(fake_provider_dir)
    provider.seed_branch_value("repoconf.version", "1")
    engine = ConfigEngine(provider)

    engine.proxy_file.write_text("", encoding="utf-8")

    engine.set(core_editor="nano")

    branch_path = fake_provider_dir / "branch_result.config"
    branch_path.write_text(
        provider.branch_blobs[(provider.branch, provider.managed_file_name)],
        encoding="utf-8",
    )

    assert read_git_config_value(branch_path, "repoconf.version") == "1"
    assert read_git_config_value(branch_path, "core.editor") == "nano"
    assert provider.commit_messages == ["Update repoconf keys: core.editor"]
    assert provider.ensure_worktree_calls == 0


def test_engine_set_preserves_all_keys_in_multi_write_batch(
    fake_provider_dir: Path,
) -> None:
    provider = FakeGitProvider(fake_provider_dir)
    provider.seed_branch_value("repoconf.version", "1")
    engine = ConfigEngine(provider)

    engine.set(repoconf_version="2", core_editor="nano")

    branch_path = fake_provider_dir / "branch_result.config"
    branch_path.write_text(
        provider.branch_blobs[(provider.branch, provider.managed_file_name)],
        encoding="utf-8",
    )

    assert read_git_config_value(branch_path, "repoconf.version") == "2"
    assert read_git_config_value(branch_path, "core.editor") == "nano"
    assert provider.commit_messages == [
        "Update repoconf keys: repoconf.version, core.editor"
    ]
    assert provider.ensure_worktree_calls == 0
