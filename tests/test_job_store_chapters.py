"""Completed chapter progress must outlive the bounded SSE replay tail."""
import json
import sqlite3
from contextlib import contextmanager

import pytest

from core import db, job_store


@pytest.fixture(params=["memory", "file"])
def store(monkeypatch, tmp_path, request):
    in_memory = request.param == "memory"
    path = ":memory:" if in_memory else str(tmp_path / "jobs.sqlite3")

    def connect():
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        return connection

    conn = connect()
    conn.executescript(db._BASE_SCHEMA)
    if not in_memory:
        conn.close()

    @contextmanager
    def connection():
        active = conn if in_memory else connect()
        try:
            with active:
                yield active
        finally:
            if not in_memory:
                active.close()

    monkeypatch.setattr(job_store, "db_conn", connection)
    yield job_store
    if in_memory:
        conn.close()


def test_completed_chapters_survive_event_pruning_and_duplicate_events(store):
    store.create("long-book", type="audiobook", meta={"title": "Book"})
    for index in range(600):
        store.append_event("long-book", json.dumps({"type": "chapter", "index": index}))
    assert len(store.events_since("long-book")) == 500
    assert store.chapters_done("long-book") == 600
    store.append_event("long-book", json.dumps({"type": "chapter", "index": 599}))
    store.append_event("long-book", json.dumps({"type": "chapter_error", "index": 600}))
    store.append_event("long-book", "not JSON")
    assert store.chapters_done("long-book") == 600
    meta = json.loads(store.get("long-book")["meta_json"])
    assert meta["title"] == "Book"
    assert len(meta["_completed_chapter_indices"]) == 600


def test_progress_is_isolated_by_job_and_ignores_invalid_indices(store):
    for job_id in ("one", "two"):
        store.create(job_id, type="story")
    store.append_event("one", json.dumps({"type": "chapter", "index": 0}))
    for index in (True, -1, "1", None):
        store.append_event("two", json.dumps({"type": "chapter", "index": index}))
    assert store.chapters_done("one") == 1
    assert store.chapters_done("two") == 0


def test_legacy_events_remain_readable_and_seed_durable_progress(store):
    store.create("legacy", type="audiobook")
    for index in range(3):
        store.append_event("legacy", json.dumps({"type": "chapter", "index": index}))
    with store.db_conn() as conn:
        conn.execute("UPDATE jobs SET meta_json='{}' WHERE id='legacy'")
    assert store.chapters_done("legacy") == 3
    store.append_event("legacy", json.dumps({"type": "chapter", "index": 3}))
    assert store.chapters_done("legacy") == 4
    assert json.loads(store.get("legacy")["meta_json"])["_completed_chapter_indices"] == [0, 1, 2, 3]
