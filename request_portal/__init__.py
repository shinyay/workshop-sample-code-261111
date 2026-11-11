import secrets
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from hmac import compare_digest
from pathlib import Path
from typing import Never

from flask import (
    Flask,
    Response,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask.json.provider import DefaultJSONProvider
from werkzeug.exceptions import HTTPException, SecurityError
from werkzeug.wrappers import Response as BaseResponse

from . import storage
from .domain import (
    DEPARTMENTS,
    INPUT_FIELDS,
    KINDS,
    STATUSES,
    InputError,
    PortalRequest,
    validate_new_request,
)

WORKSHOP_STAGE = "starter"
_ERROR_MESSAGES = {
    400: "指定された内容を確認してください。",
    403: "操作を確認できませんでした。ページを再読み込みして、もう一度操作してください。",
    404: "指定された申請またはページが見つかりません。",
    405: "このページでは、その操作を受け付けていません。",
    409: "申請の状態が変わりました。詳細を確認してください。",
    413: "入力内容が大きすぎます。文字数を減らしてください。",
    500: "処理に失敗しました。操作は完了していません。サーバーのログを確認してください。",
}


def _fail(code: int, message: str) -> Never:
    g.public_error = message
    abort(code)


def _nonce() -> str:
    nonce = g.get("csp_nonce")
    if not isinstance(nonce, str):
        nonce = secrets.token_urlsafe(24)
        g.csp_nonce = nonce
    return nonce


def _csrf_token() -> str:
    token = session.get("csrf_token")
    if not isinstance(token, str):
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def _check_form(fields: set[str]) -> None:
    expected = session.get("csrf_token")
    supplied = request.form.get("csrf_token", "")
    if (
        not isinstance(expected, str)
        or not supplied
        or not compare_digest(expected.encode("utf-8"), supplied.encode("utf-8"))
    ):
        _fail(403, _ERROR_MESSAGES[403])
    for field in request.form:
        if field not in fields | {"csrf_token"} or len(request.form.getlist(field)) != 1:
            _fail(400, "入力項目が重複しているか、未対応の項目が含まれています。")


def _validate_query_keys(allowed: set[str]) -> None:
    for key in request.args:
        if key not in allowed | {"scoutTheme"}:
            _fail(400, "初期アプリは検索条件に対応していません。演習で追加する機能です。")
        if len(request.args.getlist(key)) != 1:
            _fail(400, "同じ検索条件を複数指定することはできません。")
    if request.args.get("scoutTheme", "") not in {"", "light", "dark"}:
        _fail(400, "テーマはlightまたはdarkを指定してください。")


def create_app(config: Mapping[str, object] | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=secrets.token_hex(32),
        DATABASE=storage.DEFAULT_DATABASE,
        SEED_DEMO_DATA=True,
        TRUSTED_HOSTS=["127.0.0.1", "localhost"],
        MAX_CONTENT_LENGTH=16_384,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
    )
    if config is not None:
        app.config.update(config)
    database_path = app.config["DATABASE"]
    if not isinstance(database_path, Path):
        raise TypeError("DATABASEにはPathを指定してください。")
    seed = app.config["SEED_DEMO_DATA"]
    if not isinstance(seed, bool):
        raise TypeError("SEED_DEMO_DATAにはboolを指定してください。")
    storage.initialize(database_path, seed=seed)
    json_provider = DefaultJSONProvider(app)
    json_provider.ensure_ascii = False
    app.json = json_provider
    app.jinja_env.globals.update(csrf_token=_csrf_token, csp_nonce=_nonce)

    @app.context_processor
    def common_context() -> dict[str, object]:
        return {
            "departments": DEPARTMENTS,
            "statuses": STATUSES,
            "kinds": KINDS,
            "workshop_stage": WORKSHOP_STAGE,
        }

    @app.template_filter("japan_time")
    def japan_time(value: str) -> str:
        local = datetime.fromisoformat(value).astimezone(timezone(timedelta(hours=9)))
        return local.strftime("%Y/%m/%d %H:%M")

    @app.after_request
    def security_headers(response: Response) -> Response:
        nonce = _nonce()
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}'; style-src 'self' 'nonce-{nonce}'; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if not request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(HTTPException)
    def http_error(error: HTTPException) -> tuple[str | Response, int]:
        code = error.code or 500
        message = g.get("public_error") or _ERROR_MESSAGES.get(code, "操作を完了できませんでした。")
        if isinstance(error, SecurityError):
            message = "許可されていないHostです。許可された開発環境のURLで開いてください。"
        if request.path.startswith("/api/"):
            return jsonify(error={"code": code, "message": message}), code
        if isinstance(error, SecurityError):
            return Response(message, mimetype="text/plain"), code
        return render_template("error.html", code=code, message=message), code

    def read_requests() -> list[PortalRequest]:
        _validate_query_keys(set())
        return storage.list_requests(database_path)

    def find_request(request_id: int) -> PortalRequest:
        record = storage.get_request(database_path, request_id)
        if record is None:
            _fail(404, _ERROR_MESSAGES[404])
        return record

    @app.get("/")
    def home() -> BaseResponse:
        return redirect(url_for("request_list"))

    @app.get("/requests")
    def request_list() -> str:
        records = read_requests()
        counts = storage.status_counts(database_path)
        return render_template(
            "list.html",
            records=records,
            counts=counts,
            total=sum(counts.values()),
            query=request.args,
        )

    @app.get("/requests/<int:request_id>")
    def request_detail(request_id: int) -> str:
        return render_template("detail.html", record=find_request(request_id))

    @app.route("/requests/new", methods=["GET", "POST"])
    def request_new() -> str | BaseResponse | tuple[str, int]:
        values: dict[str, str] = {}
        errors: dict[str, str] = {}
        if request.method == "POST":
            _check_form(set(INPUT_FIELDS))
            values = {field: request.form.get(field, "") for field in INPUT_FIELDS}
            try:
                validated = validate_new_request(values)
            except InputError as error:
                errors = error.errors
            else:
                record = storage.create_request(database_path, validated)
                flash("申請を登録しました。確認待ちの状態で保存されています。", "success")
                return redirect(url_for("request_detail", request_id=record.id), code=303)
        page = render_template("new.html", values=values, errors=errors)
        return (page, 422) if errors else page

    @app.post("/requests/<int:request_id>/decision")
    def request_decision(request_id: int) -> BaseResponse:
        _check_form({"status"})
        find_request(request_id)
        status = request.form.get("status", "")
        if status not in {"approved", "rejected"}:
            _fail(400, "承認または差し戻しを選択してください。")
        if not storage.decide_request(database_path, request_id, status):
            _fail(409, "この申請はすでに処理されています。一覧から詳細を確認してください。")
        flash(f"申請を「{STATUSES[status]}」に変更しました。", "success")
        return redirect(url_for("request_detail", request_id=request_id), code=303)

    @app.get("/api/requests")
    def api_request_list() -> Response:
        records = read_requests()
        return jsonify(items=[record.to_dict() for record in records], count=len(records))

    @app.get("/api/requests/<int:request_id>")
    def api_request_detail(request_id: int) -> Response:
        return jsonify(find_request(request_id).to_dict())

    @app.get("/healthz")
    def health() -> Response:
        storage.status_counts(database_path)
        return jsonify(application="request-portal", stage=WORKSHOP_STAGE, status="ok")

    return app
