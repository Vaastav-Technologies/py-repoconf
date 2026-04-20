"""Worktree-based Git provider implementation."""

import os
import shutil
from pathlib import Path
from typing import Protocol, cast

import gitbolt
from gitbolt.subprocess.base import GitCommand
from gitbolt.subprocess.exceptions import GitCmdException as GitboltCmdException

from repoconf.constants import BACKEND_DIR_NAME, CONFIG_BRANCH, MANAGED_FILE_NAME
from repoconf.constants import REPOCONF_LOCAL_EMAIL, REPOCONF_NAME
from repoconf.providers.protocol import GitCmdException, GitProvider


class GitCommandWithRootDir(Protocol):
    """Protocol for injected git commands bound to a repository root."""

    git_root_dir: Path


class WorktreeGitProvider(GitProvider):
    """Default provider using a hidden administrative worktree under ``.git``."""

    # region Setup
    def __init__(
        self,
        branch: str = CONFIG_BRANCH,
        backend_dir_name: str = BACKEND_DIR_NAME,
        managed_file_name: str = MANAGED_FILE_NAME,
        git_root_dir: Path | None = None,
        git: GitCommand | None = None,
    ) -> None:
        self.branch = branch
        self.backend_dir_name = backend_dir_name
        self.managed_file_name = managed_file_name
        self._git_root_dir = self._resolve_git_root_dir(
            git_root_dir=git_root_dir, git=git
        )
        self.git: GitCommand = git or gitbolt.get_git_command(self.git_root_dir)
        self._git_dir = self._resolve_git_dir()

    @staticmethod
    def _resolve_git_root_dir(
        git_root_dir: Path | None, git: GitCommand | None
    ) -> Path:
        """Resolve the repository root bound to this provider instance."""
        if git is None:
            return Path(git_root_dir or Path.cwd()).resolve()

        resolved_git_root_dir = cast(GitCommandWithRootDir, git).git_root_dir.resolve()
        if (
            git_root_dir is not None
            and resolved_git_root_dir != Path(git_root_dir).resolve()
        ):
            raise ValueError(
                "WorktreeGitProvider git_root_dir must match the provided git command root"
            )
        return resolved_git_root_dir

    @property
    def git_root_dir(self) -> Path:
        """Absolute path to the repository root."""
        return self._git_root_dir

    @property
    def git_dir(self) -> Path:
        """Absolute path to the repository git directory."""
        return self._git_dir

    def _resolve_git_dir(self) -> Path:
        raw_git_dir = Path(self.run_unchecked(["rev-parse", "--git-dir"]).strip())
        if raw_git_dir.is_absolute():
            return raw_git_dir.resolve()
        return (self.git_root_dir / raw_git_dir).resolve()

    @property
    def backend_path(self) -> Path:
        """Return the administrative worktree path."""
        return self.git_dir / self.backend_dir_name

    @property
    def proxy_path(self) -> Path:
        """Return the stable local proxy file path."""
        return self.git_dir / self.managed_file_name

    # endregion

    # region Protocol Methods
    def run_unchecked(
        self,
        args: list[str],
        env: dict[str, str] | None = None,
        input: str | None = None,
    ) -> str:
        """Run a git command via gitbolt and return stdout.

        Args:
            args: Git command arguments without the ``git`` executable.
            env: Optional environment variables merged into current process env.
            input: Optional stdin payload.

        Returns:
            Stdout text from git.

        Raises:
            GitCmdException: If git exits with non-zero status.
        """
        try:
            completed = self.git.subcmd_unchecked.run(
                args,
                _input=input,
                text=True,
                capture_output=True,
                check=True,
                env=env,
            )
        except GitboltCmdException as exc:
            raise GitCmdException(str(exc)) from exc
        except Exception as exc:
            raise GitCmdException(f"Failed to execute git command: {exc}") from exc

        return completed.stdout

    def ensure_worktree(self, branch: str, path: Path) -> None:
        """Ensure the hidden administrative worktree exists and tracks the branch.

        Args:
            branch: The config branch name.
            path: Target administrative worktree path.
        """
        worktree_path = Path(path)
        worktree_path.parent.mkdir(parents=True, exist_ok=True)

        if not (worktree_path / ".git").exists():
            if worktree_path.exists():
                shutil.rmtree(worktree_path)
            self.run_unchecked(
                [
                    "worktree",
                    "add",
                    "--force",
                    "--detach",
                    "--no-checkout",
                    str(worktree_path),
                ]
            )

        has_branch = True
        try:
            self.run_unchecked(["show-ref", "--verify", f"refs/heads/{branch}"])
        except GitCmdException:
            has_branch = False

        if has_branch:
            self.run_unchecked(["-C", str(worktree_path), "checkout", branch])
        else:
            self.run_unchecked(
                ["-C", str(worktree_path), "checkout", "--orphan", branch]
            )

        # Ensure the managed file exists in the backend worktree.
        backend_file = worktree_path / self.managed_file_name
        if not backend_file.exists():
            backend_file.write_text("", encoding="utf-8")

    def read_blob(self, branch: str, path: str) -> str | None:
        """Read the content of a blob from a branch or ref."""
        try:
            ls_tree_output = self.git.ls_tree_subcmd.ls_tree(
                branch, path=[path]
            ).strip()
            if not ls_tree_output:
                return None

            return self.run_unchecked(["cat-file", "blob", f"{branch}:{path}"])
        except GitboltCmdException as exc:
            if "Not a valid object name" in str(exc) or "bad revision" in str(exc):
                return None
            raise GitCmdException(str(exc)) from exc

    def update_ref(self, ref: str, new_sha: str) -> None:
        """Atomically update a Git ref."""
        self.run_unchecked(["update-ref", ref, new_sha])

    def commit_and_push(self, path: Path, message: str) -> None:
        """Persist managed config updates to the worktree branch.

        Args:
            path: Stable proxy file path under ``.git``.
            message: Commit message.
        """
        self.ensure_worktree(self.branch, self.backend_path)

        proxy_path = Path(path)
        backend_file = self.backend_path / self.managed_file_name
        backend_file.parent.mkdir(parents=True, exist_ok=True)

        if proxy_path.exists():
            shutil.copyfile(proxy_path, backend_file)
        else:
            backend_file.write_text("", encoding="utf-8")

        self.run_unchecked(
            ["-C", str(self.backend_path), "add", self.managed_file_name]
        )

        # Skip commit when there is no staged diff.
        diff = self.run_unchecked(
            ["-C", str(self.backend_path), "diff", "--cached", "--name-only"]
        ).strip()
        if not diff:
            return

        env = dict(os.environ)
        env.update(
            {
                "GIT_AUTHOR_NAME": REPOCONF_NAME,
                "GIT_AUTHOR_EMAIL": REPOCONF_LOCAL_EMAIL,
                "GIT_COMMITTER_NAME": REPOCONF_NAME,
                "GIT_COMMITTER_EMAIL": REPOCONF_LOCAL_EMAIL,
            }
        )
        self.run_unchecked(
            ["-C", str(self.backend_path), "commit", "-m", message], env=env
        )

        # Push is best-effort because many repos have no default push target.
        try:
            self.run_unchecked(
                ["-C", str(self.backend_path), "push", "-u", "origin", self.branch]
            )
        except GitCmdException:
            pass

    # endregion
