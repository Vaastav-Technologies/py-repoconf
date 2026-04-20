"""Virtual store tests."""

from __future__ import annotations

from pathlib import Path

from gitbolt.subprocess.exceptions import GitCmdException as GitboltGitCmdException

from repoconf.constants import CONFIG_REF, REPOCONF_LOCAL_EMAIL, REPOCONF_NAME
from repoconf.core.store import VirtualStore
from repoconf.providers.protocol import GitCmdException


class FakeStoreProvider:
    """Minimal provider for VirtualStore tests."""

    def __init__(self, git_root_dir: Path) -> None:
        self.git_root_dir = git_root_dir
        self.commit_env: dict[str, str] | None = None

    def run_unchecked(
        self,
        args: list[str],
        env: dict[str, str] | None = None,
        input: str | None = None,
    ) -> str:
        del input

        if args == [
            "rev-parse",
            "-q",
            "--verify",
            CONFIG_REF,
        ]:
            raise GitCmdException("missing branch")
        if args[:2] == ["hash-object", "-w"]:
            return "blob-sha\n"
        if args[:1] == ["update-index"]:
            assert env is not None
            assert "GIT_INDEX_FILE" in env
            return ""
        if args == ["write-tree"]:
            return "tree-sha\n"
        if args[:1] == ["commit-tree"]:
            self.commit_env = env
            return "commit-sha\n"
        raise AssertionError(f"Unexpected git command: {args}")

    def read_blob(self, branch: str, path: str) -> str | None:
        del branch, path
        return None

    def update_ref(self, ref: str, new_sha: str) -> None:
        del ref, new_sha


def test_virtual_store_commit_file_sets_deterministic_identity(tmp_path: Path) -> None:
    provider = FakeStoreProvider(tmp_path)
    file_path = tmp_path / "repoconf.config"
    file_path.write_text("[core]\neditor = nano\n", encoding="utf-8")

    VirtualStore(provider).commit_file(
        str(file_path), "repoconf.config", "Update repoconf keys: core.editor"
    )

    assert provider.commit_env is not None
    assert provider.commit_env["GIT_AUTHOR_NAME"] == REPOCONF_NAME
    assert provider.commit_env["GIT_AUTHOR_EMAIL"] == REPOCONF_LOCAL_EMAIL
    assert provider.commit_env["GIT_COMMITTER_NAME"] == REPOCONF_NAME
    assert provider.commit_env["GIT_COMMITTER_EMAIL"] == REPOCONF_LOCAL_EMAIL


def test_git_cmd_exception_extends_gitbolt_exception() -> None:
    error = GitCmdException("git failed")

    assert isinstance(error, GitboltGitCmdException)
