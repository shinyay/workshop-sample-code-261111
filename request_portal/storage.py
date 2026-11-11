import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from .demo_data import DEMO_MARKER, DEMO_REQUESTS
from .domain import STATUSES, NewRequest, PortalRequest

DEFAULT_DATABASE = Path(__file__).resolve().parent.parent / "instance" / "portal-demo.sqlite3"
_COLUMNS = "id, title, applicant, department, kind, details, status, created_at"
_INSERT_DEMO = (
    "INSERT INTO requests "
    "(title, applicant, department, kind, details, status, created_at, demo_key) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
)
_SCHEMA = """
CREATE TABLE demo_metadata (
    marker TEXT PRIMARY KEY
);
CREATE TABLE requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 80),
    applicant TEXT NOT NULL CHECK (length(applicant) BETWEEN 1 AND 40),
    department TEXT NOT NULL CHECK (department IN ('engineering','sales','corporate','design')),
    kind TEXT NOT NULL CHECK (kind IN ('equipment','training','remote')),
    details TEXT NOT NULL CHECK (length(details) BETWEEN 10 AND 1000),
    status TEXT NOT NULL CHECK (status IN ('pending','approved','rejected')),
    created_at TEXT NOT NULL,
    demo_key TEXT UNIQUE
);
"""


@contextmanager
def connection(path: Path) -> Iterator[sqlite3.Connection]:
    database = sqlite3.connect(path, timeout=5)
    database.row_factory = sqlite3.Row
    try:
        yield database
    finally:
        database.close()


def _verify_marker(database: sqlite3.Connection) -> None:
    tables = {
        row[0]
        for row in database.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    if tables != {"demo_metadata", "requests"}:
        raise ValueError("専用のデモデータベースではありません。ファイルを変更せず終了しました。")
    markers = database.execute("SELECT marker FROM demo_metadata").fetchall()
    if len(markers) != 1 or markers[0]["marker"] != DEMO_MARKER:
        raise ValueError("デモデータの識別情報が一致しません。ファイルを変更せず終了しました。")


def initialize(path: Path, *, seed: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with connection(path) as database:
        existing = database.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchone()
        if existing is not None:
            _verify_marker(database)
            return
        database.executescript(_SCHEMA)
        with database:
            database.execute("INSERT INTO demo_metadata (marker) VALUES (?)", (DEMO_MARKER,))
            if seed:
                database.executemany(_INSERT_DEMO, DEMO_REQUESTS)


def reset_demo(path: Path) -> None:
    if not path.is_file():
        raise ValueError("デモデータがありません。先にアプリを起動してください。")
    with connection(path) as database, database:
        _verify_marker(database)
        database.execute("DELETE FROM requests")
        database.execute("DELETE FROM sqlite_sequence WHERE name = 'requests'")
        database.executemany(_INSERT_DEMO, DEMO_REQUESTS)


def _record(row: sqlite3.Row) -> PortalRequest:
    return PortalRequest(
        id=int(row["id"]),
        title=str(row["title"]),
        applicant=str(row["applicant"]),
        department=str(row["department"]),
        kind=str(row["kind"]),
        details=str(row["details"]),
        status=str(row["status"]),
        created_at=str(row["created_at"]),
    )


def list_requests(path: Path) -> list[PortalRequest]:
    with connection(path) as database:
        rows = database.execute(
            f"SELECT {_COLUMNS} FROM requests ORDER BY created_at DESC, id DESC"
        ).fetchall()
    return [_record(row) for row in rows]


def get_request(path: Path, request_id: int) -> PortalRequest | None:
    with connection(path) as database:
        row = database.execute(
            f"SELECT {_COLUMNS} FROM requests WHERE id = ?", (request_id,)
        ).fetchone()
    return _record(row) if row is not None else None


def status_counts(path: Path) -> dict[str, int]:
    counts = dict.fromkeys(STATUSES, 0)
    with connection(path) as database:
        for row in database.execute(
            "SELECT status, COUNT(*) AS count FROM requests GROUP BY status"
        ):
            counts[row["status"]] = int(row["count"])
    return counts


def create_request(path: Path, values: NewRequest) -> PortalRequest:
    with connection(path) as database, database:
        cursor = database.execute(
            "INSERT INTO requests "
            "(title, applicant, department, kind, details, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'pending', ?)",
            (
                values.title,
                values.applicant,
                values.department,
                values.kind,
                values.details,
                datetime.now(UTC).isoformat(timespec="seconds"),
            ),
        )
        request_id = cursor.lastrowid
    if request_id is None:
        raise RuntimeError("申請IDを取得できませんでした。")
    record = get_request(path, request_id)
    if record is None:
        raise RuntimeError("保存した申請を取得できませんでした。")
    return record


def decide_request(path: Path, request_id: int, status: str) -> bool:
    if status not in {"approved", "rejected"}:
        raise ValueError("承認または差し戻しを指定してください。")
    with connection(path) as database, database:
        cursor = database.execute(
            "UPDATE requests SET status = ? WHERE id = ? AND status = 'pending'",
            (status, request_id),
        )
    return cursor.rowcount == 1
