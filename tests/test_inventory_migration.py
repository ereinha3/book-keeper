from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from inventory import InventoryStore


def _create_legacy_schema(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE books (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                subtitle TEXT,
                authors TEXT,
                first_publish_year INTEGER,
                edition_count INTEGER,
                openlibrary_key TEXT UNIQUE,
                cover_url TEXT,
                cover_path TEXT,
                isbn TEXT,
                subjects TEXT,
                publisher TEXT,
                number_of_pages_median INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE shelves (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                description TEXT
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE shelf_rows (
                id INTEGER PRIMARY KEY,
                shelf_id INTEGER NOT NULL,
                name TEXT,
                position INTEGER NOT NULL,
                capacity INTEGER NOT NULL,
                FOREIGN KEY(shelf_id) REFERENCES shelves(id) ON DELETE CASCADE,
                UNIQUE(shelf_id, position)
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE placements (
                id INTEGER PRIMARY KEY,
                book_id INTEGER NOT NULL UNIQUE,
                shelf_row_id INTEGER NOT NULL,
                slot_index INTEGER NOT NULL,
                FOREIGN KEY(book_id) REFERENCES books(id) ON DELETE CASCADE,
                FOREIGN KEY(shelf_row_id) REFERENCES shelf_rows(id) ON DELETE CASCADE,
                UNIQUE(shelf_row_id, slot_index)
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def legacy_store(tmp_path: Path) -> InventoryStore:
    db_path = tmp_path / "legacy.db"
    _create_legacy_schema(db_path)
    store = InventoryStore(db_path=db_path)
    yield store
    store.close()


def test_migration_allows_multiple_copies_and_placements(legacy_store: InventoryStore) -> None:
    base_record = {
        "title": "Sample Book",
        "subtitle": "",
        "authors": "Author One",
        "first_publish_year": None,
        "edition_count": None,
        "openlibrary_key": "/works/OL1",
        "cover_url": None,
        "isbn": None,
        "subjects": "Test",
        "publisher": "Test Pub",
        "number_of_pages_median": None,
    }

    record_one = dict(base_record)
    record_two = dict(base_record)
    record_two["title"] = "Sample Book Copy"

    book_id_one, created_one = legacy_store.add_or_update_book(record_one, allow_multiple=True)
    assert created_one
    book_id_two, created_two = legacy_store.add_or_update_book(record_two, allow_multiple=True)
    assert created_two
    assert book_id_one != book_id_two

    books = legacy_store.list_books()
    assert len(books) == 2
    assert {book["id"] for book in books} == {book_id_one, book_id_two}

    shelf_id = legacy_store.create_shelf("Shelf A")
    row_id = legacy_store.create_row(shelf_id, name="Row 1")

    legacy_store.set_placement(book_id_one, row_id, 1)
    legacy_store.set_placement(book_id_two, row_id, 2)

    placements = legacy_store.get_shelf_structure()[0]["rows"][0]["placements"]
    assert len(placements) == 2

