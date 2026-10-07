from __future__ import annotations

import re
import tomllib
from pathlib import Path

from runtimetruth import __version__

ROOT = Path(__file__).resolve().parents[1]


def _project_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["version"]


def test_package_and_cli_versions_match() -> None:
    assert __version__ == _project_version()


def test_public_release_metadata_matches_package_version() -> None:
    version = _project_version()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert f"**Public alpha · v{version}.**" in readme
    assert f"https://github.com/sidelobe-labs/runtimetruth/releases/tag/v{version}" in readme
    assert f"## [{version}]" in changelog
    assert (ROOT / f"docs/release-v{version}.md").is_file()


def test_readme_markdown_targets_are_portable() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    targets = re.findall(r"\]\(([^)]+)\)", readme)
    allowed_prefixes = ("https://", "http://", "mailto:", "#")
    relative_targets = [target for target in targets if not target.startswith(allowed_prefixes)]

    assert relative_targets == []
