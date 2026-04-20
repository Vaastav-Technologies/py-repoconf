"""Native integration and immutable configuration engine."""

from dataclasses import dataclass
from pathlib import Path

from repoconf.constants import (
    CONFIG_BRANCH,
    CONFIG_REF,
    INCLUDE_PATH,
    MANAGED_FILE_NAME,
)
from repoconf.core.registry import CommandBuilder, ConfigValue, SetCommandValidator
from repoconf.core.store import VirtualStore
from repoconf.providers.protocol import GitCmdException, GitRefProvider
from repoconf.providers.shell import ShellGitProvider


@dataclass
class SetSubcommand:
    """Represents a validated 'set' action."""

    key: str
    value: str


@dataclass
class GetSubcommand:
    """Represents a 'get' action."""

    key: str


class ConfigEngine:
    """
    Bridges the virtual configuration branch with the local repository
    via Git's native configuration stack and a proxy file.
    """

    # region Lifecycle
    def __init__(
        self,
        provider: GitRefProvider | None = None,
    ) -> None:
        self.provider: GitRefProvider = provider or ShellGitProvider()

    def clone(self) -> "ConfigEngine":
        """
        Implements the Clone Pattern for immutability.

        >>> engine1 = ConfigEngine()
        >>> engine2 = engine1.clone()
        >>> engine1 is not engine2
        True
        """
        return ConfigEngine(self.provider)

    # endregion

    # region Paths
    @property
    def git_dir(self) -> Path:
        """Return the absolute git directory path for the bound repository."""
        raw_git_dir = Path(
            self.provider.run_unchecked(["rev-parse", "--git-dir"]).strip()
        )
        if raw_git_dir.is_absolute():
            return raw_git_dir.resolve()
        return (self.provider.git_root_dir / raw_git_dir).resolve()

    @property
    def proxy_file(self) -> Path:
        """The absolute path to the proxy file inside the git directory."""
        return self.git_dir / MANAGED_FILE_NAME

    # endregion

    # region Internal Setup
    def _setup_native_resolution(self) -> None:
        """
        Idempotently sets up git config --local include.path.
        """
        try:
            # Check if it's already set
            current_includes = self.provider.run_unchecked(
                ["config", "--local", "--get-all", "include.path"]
            ).splitlines()
            if INCLUDE_PATH in current_includes:
                return
        except GitCmdException:
            pass  # Key doesn't exist

        self.provider.run_unchecked(
            ["config", "--local", "--add", "include.path", INCLUDE_PATH]
        )

    def _ensure_proxy_file(self) -> None:
        """Ensure the stable local proxy file exists under ``.git``."""
        if self.proxy_file.exists():
            return

        self.proxy_file.parent.mkdir(parents=True, exist_ok=True)
        self.proxy_file.write_text("", encoding="utf-8")

    def _sync_proxy_from_branch(self) -> None:
        """
        Mirror the latest managed branch contents into the stable proxy file.

        The branch remains the source of truth, while the proxy keeps Git's
        native config resolution working with ``git config --get``.
        """
        self._ensure_proxy_file()
        branch_content = self.provider.read_blob(CONFIG_BRANCH, MANAGED_FILE_NAME)
        proxy_content = "" if branch_content is None else branch_content
        current_content = self.proxy_file.read_text(encoding="utf-8")
        if current_content != proxy_content:
            self.proxy_file.write_text(proxy_content, encoding="utf-8")

    # endregion

    # region Commands
    def execute_set(self, cmd: SetSubcommand) -> "ConfigEngine":
        """
        Execute a single set command against the stable proxy.
        """
        self._prepare_proxy()

        # Local write via proxy using Git config file manipulation
        self.provider.run_unchecked(
            ["config", "--file", str(self.proxy_file), cmd.key, cmd.value]
        )

        return self.clone()

    def _prepare_proxy(self) -> None:
        """Ensure proxy content and include wiring are ready."""
        self._sync_proxy_from_branch()
        self._setup_native_resolution()

    def set(self, **kwargs: ConfigValue) -> "ConfigEngine":
        """
        High-level Builder method to set configurations.
        Includes built-in validation of key format and value types.

        Returns:
            A new ConfigEngine instance (Clone Pattern).
        """
        # Validate arguments according to schema
        validator = SetCommandValidator(**kwargs)
        validator.validate()

        engine = self.clone()
        commands: list[SetSubcommand] = []
        for prop, value in kwargs.items():
            payload = CommandBuilder.build_set_command(prop=prop, value=value)
            commands.append(SetSubcommand(**payload))

        if commands:
            engine._prepare_proxy()

        for cmd in commands:
            engine.provider.run_unchecked(
                ["config", "--file", str(engine.proxy_file), cmd.key, cmd.value]
            )

        if commands:
            keys = ", ".join(cmd.key for cmd in commands)
            VirtualStore(engine.provider, CONFIG_REF).commit_file(
                str(engine.proxy_file),
                MANAGED_FILE_NAME,
                f"Update repoconf keys: {keys}",
            )

        return engine

    def execute_get(self, cmd: GetSubcommand) -> str | None:
        """
        Executes a GetSubcommand.
        """
        self._prepare_proxy()
        try:
            return self.provider.run_unchecked(["config", "--get", cmd.key]).strip()
        except GitCmdException:
            return None

    def get(self, prop: str) -> str | None:
        """
        Helper method to get a config value using pythonic property names.
        """
        payload = CommandBuilder.build_get_command(prop=prop)
        return self.execute_get(GetSubcommand(**payload))

    # endregion
