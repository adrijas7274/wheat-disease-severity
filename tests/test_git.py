from src.utils.git import get_git_commit_hash


def test_get_git_commit_hash_returns_nonempty_string() -> None:
    result = get_git_commit_hash()

    assert isinstance(result, str)
    assert len(result) > 0
