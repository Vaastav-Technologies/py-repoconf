"""Core validation tests."""

import pytest

from repoconf.core.registry import CommandBuilder, SetCommandValidator


def test_set_command_validator_accepts_arbitrary_key() -> None:
    SetCommandValidator(branch_main_description="shareable branch").validate()


def test_set_command_validator_rejects_unsupported_value_type() -> None:
    with pytest.raises(ValueError, match="Unsupported value type"):
        SetCommandValidator(custom_setting=["x"]).validate()  # type: ignore[arg-type]


def test_command_builder_builds_set_payload() -> None:
    payload = CommandBuilder.build_set_command(prop="user_name", value="Rahul")
    assert payload["key"] == "user.name"
    assert payload["value"] == "Rahul"


def test_command_builder_builds_get_payload() -> None:
    payload = CommandBuilder.build_get_command(prop="core_editor")
    assert payload["key"] == "core.editor"
