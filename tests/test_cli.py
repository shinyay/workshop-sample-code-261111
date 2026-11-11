import os
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from flask import Flask

from request_portal import __main__ as cli
from request_portal import storage


@pytest.fixture
def serve_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    monkeypatch.setattr(storage, "DEFAULT_DATABASE", tmp_path / "portal-demo.sqlite3")
    factory = MagicMock()
    monkeypatch.setattr(cli, "make_server", factory)
    return factory


@pytest.mark.parametrize("codespaces", [None, "false"])
def test_serve_keeps_local_hosts_outside_codespaces(
    monkeypatch: pytest.MonkeyPatch, serve_factory: MagicMock, codespaces: str | None
) -> None:
    if codespaces is None:
        monkeypatch.delenv("CODESPACES", raising=False)
    else:
        monkeypatch.setenv("CODESPACES", codespaces)
    monkeypatch.setenv("CODESPACE_NAME", "fictional-codespace")
    monkeypatch.setenv("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "app.github.dev")
    assert cli.main(["serve"]) == 0
    serve_factory.assert_called_once()
    assert serve_factory.call_args.args[:2] == ("127.0.0.1", 8765)
    app = serve_factory.call_args.args[2]
    assert isinstance(app, Flask)
    assert app.config["TRUSTED_HOSTS"] == ["127.0.0.1", "localhost"]
    response = app.test_client().get(
        "/requests", headers={"Host": "fictional-codespace-8765.app.github.dev"}
    )
    assert response.status_code == 400


@pytest.mark.parametrize("port", [8765, 8766])
@pytest.mark.parametrize("domain", ["app.github.dev", "app.github.example"])
def test_codespaces_serve_trusts_only_its_forwarded_host(
    monkeypatch: pytest.MonkeyPatch, serve_factory: MagicMock, port: int, domain: str
) -> None:
    monkeypatch.setenv("CODESPACES", "true")
    monkeypatch.setenv("CODESPACE_NAME", "fictional-codespace")
    monkeypatch.setenv("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", domain)
    host = f"fictional-codespace-{port}.{domain}"
    base_url = f"https://{host}"
    assert cli.main(["serve", "--port", str(port)]) == 0
    serve_factory.assert_called_once()
    assert serve_factory.call_args.args[:2] == ("127.0.0.1", port)
    assert serve_factory.call_args.kwargs == {"threaded": True}
    app = serve_factory.call_args.args[2]
    assert isinstance(app, Flask)
    assert app.config["TRUSTED_HOSTS"] == ["127.0.0.1", "localhost", host]
    client = app.test_client()
    for path in (
        "/requests",
        "/requests/1",
        "/requests/new",
        "/api/requests",
        "/api/requests/1",
        "/healthz",
    ):
        assert client.get(path, base_url=base_url).status_code == 200, path
    assert client.get("/api/requests", base_url=base_url).get_json()["count"] == 12
    page = client.get("/requests/new", base_url=base_url).get_data(as_text=True)
    token = re.search(r'name="csrf_token" value="([^"]+)"', page)
    assert token is not None
    response = client.post(
        "/requests/new",
        base_url=base_url,
        data={
            "title": "Fictional container request",
            "applicant": "Demo applicant",
            "department": "engineering",
            "kind": "equipment",
            "details": "Fictional request for Codespaces regression testing.",
            "csrf_token": token[1],
        },
    )
    assert response.status_code == 303
    assert response.headers["Location"] == "/requests/13"
    assert client.get("/api/requests", base_url=base_url).get_json()["count"] == 13
    response = client.post(
        "/requests/13/decision",
        base_url=base_url,
        data={"status": "approved", "csrf_token": token[1]},
    )
    assert response.status_code == 303
    response = client.post(
        "/requests/13/decision",
        base_url=base_url,
        data={"status": "rejected", "csrf_token": token[1]},
    )
    assert response.status_code == 409
    assert client.get("/api/requests/13", base_url=base_url).get_json()["status"] == "approved"
    for untrusted in (
        "unrelated.example",
        f"another-codespace-{port}.{domain}",
        f"fictional-codespace-{port + 1}.{domain}",
        f"subdomain.{host}",
    ):
        for path in ("/requests", "/api/requests"):
            assert client.get(path, base_url=f"https://{untrusted}").status_code == 400


@pytest.mark.parametrize(
    ("name", "domain"),
    [
        ("", "app.github.dev"),
        ("fictional-codespace", ""),
        ("invalid.name", "app.github.dev"),
        ("invalid name", "app.github.dev"),
        ("fictional-codespace", ".app.github.dev"),
        ("fictional-codespace", "*.github.dev"),
        ("fictional-codespace", "https://app.github.dev"),
        ("fictional-codespace", "app.github.dev:443"),
        ("fictional-codespace", "app.github.dev/example"),
        ("fictional-codespace", "app..github.dev"),
        ("fictional-codespace", "app.github.dev."),
        ("x" * 64, "app.github.dev"),
        ("fictional-codespace", "x" * 64 + ".github.dev"),
        ("fictional-codespace", ".".join(["x" * 63] * 4)),
    ],
)
def test_invalid_codespaces_context_is_reported_before_initialization(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    serve_factory: MagicMock,
    name: str,
    domain: str,
) -> None:
    monkeypatch.setenv("CODESPACES", "true")
    monkeypatch.setenv("CODESPACE_NAME", name)
    monkeypatch.setenv("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", domain)
    with pytest.raises(SystemExit) as error:
        cli.main(["serve"])
    assert error.value.code == 1
    assert "Codespaces" in capsys.readouterr().err
    serve_factory.assert_not_called()
    assert not storage.DEFAULT_DATABASE.exists()


def test_seed_and_confirmed_reset_use_only_the_default_demo_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "portal-demo.sqlite3"
    monkeypatch.setattr(cli, "DEFAULT_DATABASE", path)
    assert cli.main(["seed"]) == 0
    assert "12件" in capsys.readouterr().out
    assert storage.decide_request(path, 1, "approved")
    assert cli.main(["reset-demo", "--confirm", "request-portal-demo"]) == 0
    record = storage.get_request(path, 1)
    assert record is not None and record.status == "pending"


@pytest.mark.parametrize("confirmation", [[], ["--confirm", "wrong-database"]])
def test_reset_requires_specific_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    confirmation: list[str],
) -> None:
    path = tmp_path / "portal-demo.sqlite3"
    monkeypatch.setattr(cli, "DEFAULT_DATABASE", path)
    with pytest.raises(SystemExit) as error:
        cli.main(["reset-demo", *confirmation])
    assert error.value.code == 2
    assert not path.exists()


@pytest.mark.parametrize("port", ["0", "65536", "not-a-number"])
def test_invalid_port_is_rejected_before_starting(port: str) -> None:
    with pytest.raises(SystemExit) as error:
        cli.main(["serve", "--port", port])
    assert error.value.code == 2


def test_cli_outputs_utf8_even_when_redirected_with_ascii_encoding() -> None:
    environment = os.environ | {"PYTHONIOENCODING": "ascii"}
    result = subprocess.run(
        [sys.executable, "-m", "request_portal", "--help"],
        capture_output=True,
        env=environment,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8")
    assert "架空の社内申請ポータル" in result.stdout.decode("utf-8")
