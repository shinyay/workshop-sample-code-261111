from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient

from request_portal import create_app


@pytest.fixture
def app(tmp_path: Path) -> Flask:
    return create_app({"TESTING": True, "DATABASE": tmp_path / "demo.sqlite3"})


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()
