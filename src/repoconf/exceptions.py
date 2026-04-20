"""Shared repoconf exceptions."""

from subprocess import CalledProcessError

from gitbolt.subprocess.exceptions import GitCmdException as GitboltGitCmdException
from repoconf.constants import REPOCONF_NAME
from vt.utils.errors.error_specs.exceptions import VTCmdException, VTException

__all__ = ["GitCmdException", "RepoconfCmdException", "RepoconfException"]


class RepoconfException(VTException):
    """Base exception for repoconf failures."""


class RepoconfCmdException(VTCmdException, RepoconfException):
    """Base command error for repoconf command execution failures."""

    default_command: str | list[str] = REPOCONF_NAME

    def __init__(
        self,
        *args: object,
        called_process_error: CalledProcessError | None = None,
        exit_code: int | None = None,
        **kwargs: object,
    ) -> None:
        if called_process_error is None:
            called_process_error = CalledProcessError(
                returncode=exit_code or 1,
                cmd=self.default_command,
            )

        super().__init__(
            *args,
            called_process_error=called_process_error,
            exit_code=exit_code,
            **kwargs,
        )


class GitCmdException(GitboltGitCmdException, RepoconfCmdException):
    """Exception raised when a Git command fails."""

    default_command = "git"
