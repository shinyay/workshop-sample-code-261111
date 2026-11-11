import json
import tomllib
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent


def test_devcontainer_waits_for_the_portal_to_start() -> None:
    config = json.loads(
        (ROOT / ".devcontainer" / "devcontainer.json").read_text(encoding="utf-8")
    )
    assert config["postCreateCommand"] == "uv sync --locked"
    assert config["postStartCommand"] == "bash .devcontainer/start-portal.sh"
    assert config["waitFor"] == "postStartCommand"
    assert config["forwardPorts"] == [8765]


def test_distribution_uses_public_dependency_sources() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    indexes = project["tool"]["uv"]["index"]
    assert indexes == [{"name": "public-pypi", "url": "https://pypi.org/simple", "default": True}]
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    registered = [package for package in lock["package"] if "registry" in package["source"]]
    assert registered
    for package in registered:
        assert package["source"]["registry"] == "https://pypi.org/simple"
        artifacts = package.get("wheels", [])
        if "sdist" in package:
            artifacts = [*artifacts, package["sdist"]]
        assert artifacts
        for artifact in artifacts:
            url = urlparse(artifact["url"])
            assert url.scheme == "https" and url.hostname == "files.pythonhosted.org"
            assert url.username is None and url.password is None
            assert artifact["hash"].startswith("sha256:")
            assert len(bytes.fromhex(artifact["hash"].removeprefix("sha256:"))) == 32


def test_locked_python_range_matches_the_project() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    assert project["project"]["requires-python"].replace(" ", "") == lock[
        "requires-python"
    ].replace(" ", "")
