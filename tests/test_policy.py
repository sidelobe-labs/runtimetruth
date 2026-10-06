import pytest

from runtimetruth.policy import PolicyError, load_policy


def test_load_policy_reads_schema_v1_selectors(tmp_path) -> None:
    path = tmp_path / "policy.toml"
    path.write_text(
        """version = 1

protect = [
  "codex.thread.model",
  "codex.instructions",
  "codex.thread.model",
]
""",
        encoding="utf-8",
    )

    policy = load_policy(str(path))

    assert policy.version == 1
    assert policy.protect == (
        "codex.thread.model",
        "codex.instructions",
    )


def test_load_policy_trims_selector_whitespace(tmp_path) -> None:
    path = tmp_path / "policy.toml"
    path.write_text(
        'version = 1\nprotect = ["  codex.thread.model  "]\n',
        encoding="utf-8",
    )

    assert load_policy(str(path)).protect == ("codex.thread.model",)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ('version = 2\nprotect = ["codex.thread.model"]\n', "version must be integer 1"),
        (
            'version = 1\nprotect = ["codex.thread.model"]\nmode = "strict"\n',
            "unsupported policy key",
        ),
        ("version = 1\nprotect = []\n", "non-empty array"),
        ('version = 1\nprotect = ["codex.thread.model", 1]\n', "must be a string selector"),
        ('version = 1\nprotect = ["   "]\n', "must not be empty"),
    ],
)
def test_load_policy_rejects_invalid_schema(tmp_path, content, message) -> None:
    path = tmp_path / "policy.toml"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(PolicyError, match=message):
        load_policy(str(path))


def test_load_policy_rejects_invalid_toml(tmp_path) -> None:
    path = tmp_path / "policy.toml"
    path.write_text('version = 1\nprotect = ["codex.thread.model"\n', encoding="utf-8")

    with pytest.raises(PolicyError, match="invalid policy"):
        load_policy(str(path))


def test_load_policy_rejects_missing_file(tmp_path) -> None:
    with pytest.raises(PolicyError, match="could not read policy"):
        load_policy(str(tmp_path / "missing.toml"))
