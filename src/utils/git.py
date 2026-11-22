"""Git metadata helpers so experiment outputs record the exact code version used."""

import subprocess


def get_git_commit_hash() -> str:
    """Return the current git commit hash, or "nogit" if unavailable.

    Falls back to "nogit" (rather than raising) so training/eval scripts still
    run in environments without git history yet, e.g. a fresh Colab checkout
    before the first commit.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "nogit"
