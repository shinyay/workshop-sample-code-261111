import sqlite3
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from request_portal import storage
from request_portal.domain import validate_new_request
from tests.test_portal import VALID


def test_seeding_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "demo.sqlite3"
    storage.initialize(path)
    first = storage.list_requests(path)
    storage.initialize(path)
    assert storage.list_requests(path) == first
    assert len(first) == 12
    assert storage.status_counts(path) == {"pending": 5, "approved": 4, "rejected": 3}


def test_reset_restores_seed_ids_and_removes_only_demo_requests(tmp_path: Path) -> None:
    path = tmp_path / "demo.sqlite3"
    storage.initialize(path)
    initial = storage.list_requests(path)
    storage.create_request(path, validate_new_request(VALID))
    assert storage.decide_request(path, 1, "approved")
    storage.reset_demo(path)
    assert storage.list_requests(path) == initial
    assert storage.status_counts(path) == {"pending": 5, "approved": 4, "rejected": 3}
    record = storage.create_request(path, validate_new_request(VALID))
    assert record.id == 13


@pytest.mark.parametrize("operation", [storage.initialize, storage.reset_demo])
def test_foreign_database_is_untouched(tmp_path: Path, operation: Callable[[Path], None]) -> None:
    path = tmp_path / "foreign.sqlite3"
    with sqlite3.connect(path) as database:
        database.execute("CREATE TABLE unrelated (value TEXT)")
        database.execute("INSERT INTO unrelated VALUES ('do not change')")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="専用のデモデータベースではありません"):
        operation(path)
    assert path.read_bytes() == before


def test_reset_missing_database_does_not_create_a_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.sqlite3"
    with pytest.raises(ValueError, match="デモデータがありません"):
        storage.reset_demo(path)
    assert not path.exists()


def test_invalid_marker_is_not_reset(tmp_path: Path) -> None:
    path = tmp_path / "demo.sqlite3"
    storage.initialize(path)
    with sqlite3.connect(path) as database:
        database.execute("UPDATE demo_metadata SET marker = 'other-application'")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="識別情報が一致しません"):
        storage.reset_demo(path)
    assert path.read_bytes() == before


def test_competing_decisions_cannot_both_succeed(tmp_path: Path) -> None:
    path = tmp_path / "demo.sqlite3"
    storage.initialize(path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda status: storage.decide_request(path, 1, status),
                (
                    "approved",
                    "rejected",
                ),
            )
        )
    assert sorted(results) == [False, True]
    record = storage.get_request(path, 1)
    assert record is not None
    assert record.status == ("approved" if results[0] else "rejected")


def test_invalid_decision_fails_explicitly(tmp_path: Path) -> None:
    path = tmp_path / "demo.sqlite3"
    storage.initialize(path)
    with pytest.raises(ValueError, match="承認または差し戻し"):
        storage.decide_request(path, 1, "pending")
    record = storage.get_request(path, 1)
    assert record is not None and record.status == "pending"
