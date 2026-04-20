"""Tests for package constants."""

from repoconf.constants import (
    BACKEND_DIR_NAME,
    CONFIG_BRANCH,
    CONFIG_REF,
    INCLUDE_PATH,
    MANAGED_FILE_NAME,
    REPOCONF_LOCAL_EMAIL,
    REPOCONF_NAME,
)


def test_constants_are_derived_from_repoconf_name() -> None:
    assert REPOCONF_LOCAL_EMAIL == f"{REPOCONF_NAME}@local"
    assert MANAGED_FILE_NAME == f"{REPOCONF_NAME}.config"
    assert INCLUDE_PATH == MANAGED_FILE_NAME
    assert CONFIG_BRANCH == f"__{REPOCONF_NAME}/default/main"
    assert CONFIG_REF == f"refs/heads/{CONFIG_BRANCH}"
    assert BACKEND_DIR_NAME == f"{REPOCONF_NAME}_backend"
