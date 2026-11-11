import re
import sqlite3
from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient
from werkzeug.datastructures import MultiDict

from request_portal import WORKSHOP_STAGE, create_app, storage

VALID = {
    "title": "架空の研修用機器の購入",
    "applicant": "試験用 さくら",
    "department": "engineering",
    "kind": "equipment",
    "details": "研修で操作を確認するため、架空の機器を1台購入したいです。",
}


def csrf(client: FlaskClient, path: str = "/requests/new") -> str:
    response = client.get(path)
    assert response.status_code == 200
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.get_data(as_text=True))
    assert match is not None
    return match.group(1)


def test_list_and_api_share_seeded_data(client: FlaskClient) -> None:
    response = client.get("/requests")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "12件を表示" in page
    assert page.count('class="request-title"') == 12
    payload = client.get("/api/requests").get_json()
    assert set(payload) == {"items", "count"}
    assert payload["count"] == len(payload["items"]) == 12
    assert [item["id"] for item in payload["items"]] == list(range(12, 0, -1))
    assert set(payload["items"][0]) == {
        "id",
        "title",
        "applicant",
        "department",
        "kind",
        "details",
        "status",
        "created_at",
    }
    assert payload["items"][0]["title"] in page


def test_health_and_workshop_stage_are_explicit(client: FlaskClient) -> None:
    assert WORKSHOP_STAGE in {"starter", "reference"}
    assert client.get("/healthz").get_json() == {
        "application": "request-portal",
        "stage": WORKSHOP_STAGE,
        "status": "ok",
    }
    page = client.get("/requests").get_data(as_text=True)
    if WORKSHOP_STAGE == "starter":
        assert "<strong>初期アプリ</strong>" in page
        assert 'id="filter-department"' not in page
        assert client.get("/api/requests?department=engineering&status=pending").status_code == 400
    else:
        assert "<strong>完成例</strong>" in page
        assert 'id="filter-department"' in page
        assert client.get("/api/requests?department=engineering&status=pending").status_code == 200


def test_home_redirects_to_list(client: FlaskClient) -> None:
    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"] == "/requests"


def test_detail_displays_department_status_and_content(client: FlaskClient) -> None:
    response = client.get("/requests/1")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "開発部" in page
    assert "確認待ち" in page
    assert "検証端末で使うキーボードを1台購入したいです。" in page
    payload = client.get("/api/requests/1").get_json()
    assert payload["id"] == 1
    assert payload["department"] == "engineering"
    assert payload["status"] == "pending"


@pytest.mark.parametrize("path", ["/requests/9999", "/api/requests/9999", "/api/requests/0"])
def test_missing_request_returns_404(client: FlaskClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 404
    if path.startswith("/api/"):
        assert response.get_json()["error"]["code"] == 404
    else:
        assert "見つかりません" in response.get_data(as_text=True)


def test_create_persists_and_updates_summary(client: FlaskClient, app: Flask) -> None:
    response = client.post("/requests/new", data=VALID | {"csrf_token": csrf(client)})
    assert response.status_code == 303
    assert response.headers["Location"] == "/requests/13"
    page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "申請を登録しました。" in page
    assert VALID["title"] in page
    record = storage.get_request(app.config["DATABASE"], 13)
    assert record is not None
    assert record.title == VALID["title"]
    assert record.status == "pending"
    assert storage.status_counts(app.config["DATABASE"]) == {
        "pending": 6,
        "approved": 4,
        "rejected": 3,
    }
    restarted = create_app({"TESTING": True, "DATABASE": app.config["DATABASE"]})
    assert restarted.test_client().get("/api/requests").get_json()["count"] == 13


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", ""),
        ("title", "   "),
        ("title", "x" * 81),
        ("applicant", ""),
        ("applicant", "x" * 41),
        ("details", "x" * 9),
        ("details", "x" * 1001),
        ("department", "unknown"),
        ("kind", "unknown"),
        ("title", "bad\x00title"),
        ("applicant", "bad\nname"),
        ("details", "bad\x01contents"),
    ],
)
def test_invalid_form_is_visible_and_does_not_write(
    client: FlaskClient,
    field: str,
    value: str,
) -> None:
    response = client.post(
        "/requests/new",
        data=VALID | {field: value, "csrf_token": csrf(client)},
    )
    assert response.status_code == 422
    page = response.get_data(as_text=True)
    assert 'role="alert"' in page
    assert f'id="{field}-error"' in page
    assert client.get("/api/requests").get_json()["count"] == 12


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", "x"),
        ("title", "x" * 80),
        ("applicant", "x"),
        ("applicant", "x" * 40),
        ("details", "x" * 10),
        ("details", "x" * 1000),
        ("details", "申請の理由です。\n補足説明を追加します。"),
    ],
)
def test_form_length_boundaries_are_accepted(
    client: FlaskClient,
    field: str,
    value: str,
) -> None:
    response = client.post(
        "/requests/new",
        data=VALID | {field: value, "csrf_token": csrf(client)},
    )
    assert response.status_code == 303
    assert client.get("/api/requests/13").get_json()[field] == value


@pytest.mark.parametrize("token", ["", "invalid-token", "架空のトークン"])
def test_invalid_csrf_is_rejected_without_writing(client: FlaskClient, token: str) -> None:
    csrf(client)
    response = client.post("/requests/new", data=VALID | {"csrf_token": token})
    assert response.status_code == 403
    assert "再読み込み" in response.get_data(as_text=True)
    assert client.get("/api/requests").get_json()["count"] == 12


def test_unknown_form_field_cannot_set_initial_status(client: FlaskClient) -> None:
    response = client.post(
        "/requests/new",
        data=VALID | {"status": "approved", "csrf_token": csrf(client)},
    )
    assert response.status_code == 400
    assert client.get("/api/requests").get_json()["count"] == 12


def test_duplicate_form_fields_are_rejected(client: FlaskClient) -> None:
    fields = MultiDict(list(VALID.items()) + [("title", "another"), ("csrf_token", csrf(client))])
    response = client.post("/requests/new", data=fields)
    assert response.status_code == 400
    assert client.get("/api/requests").get_json()["count"] == 12


def test_input_is_escaped_in_detail(client: FlaskClient) -> None:
    values = VALID | {
        "title": "<script>alert(1)</script>",
        "details": '<img src=x onerror="alert(1)">これは架空の説明です。',
    }
    response = client.post("/requests/new", data=values | {"csrf_token": csrf(client)})
    assert response.status_code == 303
    page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert values["title"] not in page
    assert values["details"] not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "&lt;img" in page


@pytest.mark.parametrize("status", ["approved", "rejected"])
def test_decision_transitions_only_once(
    client: FlaskClient,
    app: Flask,
    status: str,
) -> None:
    token = csrf(client, "/requests/1")
    response = client.post("/requests/1/decision", data={"status": status, "csrf_token": token})
    assert response.status_code == 303
    record = storage.get_request(app.config["DATABASE"], 1)
    assert record is not None and record.status == status
    page = client.get("/requests/1").get_data(as_text=True)
    assert 'value="approved"' not in page and 'value="rejected"' not in page
    repeated = client.post(
        "/requests/1/decision",
        data={"status": "rejected" if status == "approved" else "approved", "csrf_token": token},
    )
    assert repeated.status_code == 409
    assert client.get("/api/requests/1").get_json()["status"] == status


@pytest.mark.parametrize("status", ["pending", "", "unknown"])
def test_invalid_decision_does_not_change_data(client: FlaskClient, status: str) -> None:
    response = client.post(
        "/requests/1/decision",
        data={"status": status, "csrf_token": csrf(client, "/requests/1")},
    )
    assert response.status_code == 400
    assert client.get("/api/requests/1").get_json()["status"] == "pending"


def test_decision_missing_request_is_not_success(client: FlaskClient) -> None:
    response = client.post(
        "/requests/9999/decision",
        data={"status": "approved", "csrf_token": csrf(client)},
    )
    assert response.status_code == 404


def test_empty_database_has_actionable_empty_state(tmp_path: Path) -> None:
    app = create_app(
        {"TESTING": True, "DATABASE": tmp_path / "empty.sqlite3", "SEED_DEMO_DATA": False}
    )
    client = app.test_client()
    page = client.get("/requests").get_data(as_text=True)
    assert "表示する申請はありません" in page
    assert "新規申請を作成" in page
    assert client.get("/api/requests").get_json() == {"items": [], "count": 0}
    again = create_app({"TESTING": True, "DATABASE": tmp_path / "empty.sqlite3"})
    assert again.test_client().get("/api/requests").get_json()["count"] == 0


@pytest.mark.parametrize(
    "path", ["/requests?unknown=x", "/api/requests?scoutTheme=light&scoutTheme=dark"]
)
def test_unknown_or_duplicate_query_is_rejected(client: FlaskClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 400
    if path.startswith("/api/"):
        assert response.get_json()["error"]["code"] == 400
    else:
        assert 'role="alert"' in response.get_data(as_text=True)


def test_security_headers_and_theme_are_served(client: FlaskClient) -> None:
    response = client.get("/requests?scoutTheme=dark")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    nonce = re.search(r'<script nonce="([^"]+)"', page)
    assert nonce is not None
    policy = response.headers["Content-Security-Policy"]
    assert f"'nonce-{nonce.group(1)}'" in policy
    assert "frame-ancestors 'none'" in policy
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Cache-Control"] == "no-store"
    cookie = client.get("/requests/new").headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie


@pytest.mark.parametrize("path", ["/requests", "/api/requests"])
def test_untrusted_host_is_rejected(client: FlaskClient, path: str) -> None:
    response = client.get(path, base_url="http://unexpected.example")
    assert response.status_code == 400
    if path.startswith("/api/"):
        assert response.get_json()["error"]["code"] == 400
    else:
        assert response.mimetype == "text/plain"
        assert "許可されていないHost" in response.get_data(as_text=True)


def test_excessive_request_body_is_rejected(client: FlaskClient) -> None:
    response = client.post("/requests/new", data={"details": "x" * 17000})
    assert response.status_code == 413
    assert "入力内容が大きすぎます" in response.get_data(as_text=True)


def test_database_failure_is_logged_and_not_reported_as_success(
    client: FlaskClient,
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def unavailable(path: Path, **filters: str) -> list[object]:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(storage, "list_requests", unavailable)
    app.config["PROPAGATE_EXCEPTIONS"] = False
    response = client.get("/api/requests")
    assert response.status_code == 500
    assert response.get_json()["error"]["code"] == 500
    assert "完了していません" in response.get_json()["error"]["message"]
    assert "database is locked" in caplog.text
