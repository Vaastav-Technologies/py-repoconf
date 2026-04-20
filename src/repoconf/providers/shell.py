"""ShellGitProvider implementation using gitbolt."""

from pathlib import Path

import gitbolt
from gitbolt.subprocess.base import GitCommand
from gitbolt.subprocess.exceptions import GitCmdException as GitboltCmdException

from repoconf.providers.protocol import GitCmdException, GitRefProvider


class ShellGitProvider(GitRefProvider):
    """
    Ref-aware Git provider implementation that executes Git commands via gitbolt.
    """

    def __init__(self, git_root_dir: Path | None = None) -> None:
        self._git_root_dir = Path(git_root_dir or Path.cwd()).resolve()
        self.git: GitCommand = gitbolt.get_git_command(self.git_root_dir)
        self._git_dir = self._resolve_git_dir()

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

    def run_unchecked(
        self,
        args: list[str],
        env: dict[str, str] | None = None,
        input: str | None = None,
    ) -> str:
        """
        Executes a Git command through gitbolt's unchecked subcommand runner.

        Args:
            args: The git command arguments.
            env: Optional environment variables to merge.
            input: Optional standard input to pass.

        Returns:
            str: The standard output of the command.

        Raises:
            GitCmdException: If the command returns a non-zero exit code.

        >>> provider = ShellGitProvider()
        >>> version = provider.run_unchecked(["version"])
        >>> "git version" in version
        True
        """
        try:
            result = self.git.subcmd_unchecked.run(
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

        return result.stdout

    def read_blob(self, branch: str, path: str) -> str | None:
        """
        Reads the content of a blob at a specific path on a branch.

        Args:
            branch: The branch name.
            path: The file path within the branch.

        Returns:
            str: The content of the file, or None if the path/branch does not exist.

        Raises:
            GitCmdException: If an unexpected error occurs during reading.
        """
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
        """
        Updates a branch pointer (reference) to a new commit SHA.

        Args:
            ref: The full reference name.
            new_sha: The commit SHA.

        Raises:
            GitCmdException: If the update fails.
        """
        self.run_unchecked(["update-ref", ref, new_sha])
