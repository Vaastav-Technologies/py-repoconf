"""Provider tests focused on injected git command usage."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from repoconf.providers.worktree import WorktreeGitProvider


class FakeUncheckedRunner:
    """Minimal unchecked runner used by fake git commands."""

    def __init__(self, stdout: str = ".git\n") -> None:
        self.stdout = stdout
        self.calls: list[tuple[list[str], dict[str, str] | None, str | None]] = []

    def run(
        self,
        args: list[str],
        _input: str | None = None,
        text: bool = True,
        capture_output: bool = True,
        check: bool = True,
        env: dict[str, str] | None = None,
    ) -> SimpleNamespace:
        del text, capture_output, check
        self.calls.append((args, env, _input))
        return SimpleNamespace(stdout=self.stdout)


class FakeLsTreeSubcommand:
    """Minimal ls-tree subcommand stub."""

    def ls_tree(self, branch: str, path: list[str]) -> str:
        del branch, path
        return ""


class FakeGitCommand:
    """Git command stub exposing the attributes the provider uses."""

    def __init__(self, git_root_dir: Path, stdout: str = ".git\n") -> None:
        self.git_root_dir = git_root_dir
        self.subcmd_unchecked = FakeUncheckedRunner(stdout=stdout)
        self.ls_tree_subcmd = FakeLsTreeSubcommand()


def test_worktree_provider_uses_client_git_command(tmp_path: Path) -> None:
    fake_git = FakeGitCommand(tmp_path)

    provider = WorktreeGitProvider(git=fake_git)

    assert provider.git is fake_git
    assert provider.git_root_dir == tmp_path.resolve()
    assert provider.git_dir == (tmp_path / ".git").resolve()
    assert fake_git.subcmd_unchecked.calls == [(["rev-parse", "--git-dir"], None, None)]


def test_worktree_provider_rejects_mismatched_client_git_root(tmp_path: Path) -> None:
    fake_git = FakeGitCommand(tmp_path / "repo")

    with pytest.raises(
        ValueError,
        match="git_root_dir must match the provided git command root",
    ):
        WorktreeGitProvider(git=fake_git, git_root_dir=tmp_path / "other")
