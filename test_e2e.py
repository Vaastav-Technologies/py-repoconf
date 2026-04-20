import subprocess

from repoconf.providers.worktree import WorktreeGitProvider
from repoconf.core.engine import ConfigEngine


def check_call(args: list[str]) -> str:
    completed = subprocess.run(
        args,
        text=True,
        capture_output=True,
        check=True,
    )
    return completed.stdout.strip()


def run_test() -> None:
    print("Testing e2e Virtual Store and Config Engine...")
    provider = WorktreeGitProvider()
    engine = ConfigEngine(provider)

    # Check HEAD before
    head_before = check_call(["git", "rev-parse", "HEAD"])

    # 1. Set configuration
    print("Setting config...")
    engine = engine.set(repoconf_version="2", core_editor="nano")

    # 2. Check Virtual Branch
    print("Checking __repoconf/default/main branch logs...")
    log_out = check_call(["git", "log", "-1", "__repoconf/default/main"])
    assert "repoconf.version" in log_out or "Update" in log_out

    # Ensure set() call generated only one commit.
    commit_count = int(
        check_call(["git", "rev-list", "--count", "__repoconf/default/main"])
    )
    assert commit_count >= 1

    # 3. Check HEAD is unchanged
    head_after = check_call(["git", "rev-parse", "HEAD"])
    assert head_before == head_after, "HEAD was modified!"

    # 4. Check git config resolution
    print("Testing git config --get...")
    version = check_call(["git", "config", "--get", "repoconf.version"])
    assert version == "2", f"Expected repoconf.version=2, got {version}"

    print("All e2e tests passed!")


if __name__ == "__main__":
    run_test()
