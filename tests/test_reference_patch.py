import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PATCH = ROOT / "workshop" / "filtering.patch"
PATCH_FILES = (
    Path("request_portal") / "__init__.py",
    Path("request_portal") / "storage.py",
    Path("request_portal") / "templates" / "list.html",
    Path("request_portal") / "static" / "portal.css",
    Path("tests") / "test_filtering.py",
)


def run(directory: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    command = list(arguments)
    if command[0] == "git":
        command[1:1] = ["-c", "core.autocrlf=false", "-c", "core.eol=lf"]
    environment = os.environ | {
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    environment.pop("PYTHONPATH", None)
    return subprocess.run(
        command,
        cwd=directory,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=90,
        check=False,
    )


def manifest(directory: Path) -> dict[Path, bytes]:
    return {
        path: (directory / path).read_bytes() for path in PATCH_FILES if (directory / path).exists()
    }


@pytest.fixture
def starter_copy(tmp_path: Path) -> Path:
    assert shutil.which("git"), "完成例の差分確認にはGitが必要です。"
    directory = tmp_path / "portal"
    shutil.copytree(
        ROOT,
        directory,
        ignore=shutil.ignore_patterns(
            ".git",
            ".venv",
            ".venv313",
            ".venv-browser",
            "browser-checks",
            "instance",
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            "test_reference_patch.py",
        ),
    )
    source = (directory / PATCH_FILES[0]).read_bytes()
    if b'WORKSHOP_STAGE = "reference"' in source:
        result = run(directory, "git", "apply", "--reverse", str(PATCH))
        assert result.returncode == 0, result.stderr
    assert (directory / PATCH_FILES[0]).read_bytes().count(b'WORKSHOP_STAGE = "starter"') == 1
    return directory


def test_reference_patch_passes_behavior_and_reverses_exactly(starter_copy: Path) -> None:
    names = re.findall(
        r"^diff --git a/(\S+) b/\1$", PATCH.read_text(encoding="utf-8"), re.MULTILINE
    )
    assert set(names) == {path.as_posix() for path in PATCH_FILES}
    before = manifest(starter_copy)
    checked = run(starter_copy, "git", "apply", "--check", str(PATCH))
    assert checked.returncode == 0, checked.stderr
    applied = run(starter_copy, "git", "apply", str(PATCH))
    assert applied.returncode == 0, applied.stderr
    assert (starter_copy / PATCH_FILES[0]).read_bytes().count(b'WORKSHOP_STAGE = "reference"') == 1
    assert (starter_copy / PATCH_FILES[0]).read_bytes().count(b'WORKSHOP_STAGE = "starter"') == 0
    assert (starter_copy / PATCH_FILES[-1]).is_file()
    verified = run(
        starter_copy,
        sys.executable,
        "-m",
        "pytest",
        str(Path("tests") / "test_filtering.py"),
        "-q",
        "--tb=short",
        "-p",
        "no:cacheprovider",
    )
    assert verified.returncode == 0, verified.stdout + verified.stderr
    reverse_checked = run(starter_copy, "git", "apply", "--reverse", "--check", str(PATCH))
    assert reverse_checked.returncode == 0, reverse_checked.stderr
    reversed_patch = run(starter_copy, "git", "apply", "--reverse", str(PATCH))
    assert reversed_patch.returncode == 0, reversed_patch.stderr
    assert manifest(starter_copy) == before


def test_reference_patch_rejects_participant_changes_atomically(starter_copy: Path) -> None:
    source = starter_copy / PATCH_FILES[0]
    original = source.read_bytes()
    assert original.count(b'WORKSHOP_STAGE = "starter"') == 1
    changed = original.replace(
        b'WORKSHOP_STAGE = "starter"', b'WORKSHOP_STAGE = "participant-edit"'
    )
    assert changed.count(b'WORKSHOP_STAGE = "participant-edit"') == 1
    assert b'WORKSHOP_STAGE = "starter"' not in changed
    source.write_bytes(changed)
    before = manifest(starter_copy)
    result = run(starter_copy, "git", "apply", str(PATCH))
    assert result.returncode == 1
    assert "patch does not apply" in result.stderr
    assert manifest(starter_copy) == before
