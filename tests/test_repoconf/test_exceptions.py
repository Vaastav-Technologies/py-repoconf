"""Tests for repoconf exception hierarchy."""

from repoconf.constants import REPOCONF_NAME
from vt.utils.errors.error_specs.exceptions import VTCmdException, VTException

from repoconf.exceptions import GitCmdException, RepoconfCmdException, RepoconfException


def test_repoconf_exception_extends_company_base() -> None:
    assert issubclass(RepoconfException, VTException)


def test_repoconf_cmd_exception_extends_company_command_base() -> None:
    assert issubclass(RepoconfCmdException, VTCmdException)


def test_repoconf_cmd_exception_uses_repoconf_name_as_default_command() -> None:
    assert RepoconfCmdException.default_command == REPOCONF_NAME


def test_git_cmd_exception_is_explicit_command_error() -> None:
    error = GitCmdException("git failed")

    assert isinstance(error, RepoconfCmdException)
    assert isinstance(error, VTCmdException)
    assert "git failed" in str(error)
