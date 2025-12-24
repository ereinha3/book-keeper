from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from inventory import InventoryStore
from server import app, get_store


def _reset_store_singleton() -> None:
    if hasattr(get_store, "_instance"):
        instance = getattr(get_store, "_instance")
        if isinstance(instance, InventoryStore):
            instance.close()
        delattr(get_store, "_instance")


@pytest.fixture
def store(tmp_path: Path) -> InventoryStore:
    _reset_store_singleton()
    test_store = InventoryStore(db_path=tmp_path / "library.db")
    app.dependency_overrides[get_store] = lambda: test_store
    yield test_store
    test_store.close()
    app.dependency_overrides.pop(get_store, None)
    _reset_store_singleton()


@pytest.fixture
def client(store: InventoryStore) -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def _add_book(
    store: InventoryStore,
    *,
    title: str,
    open_key: str,
    authors: str = "",
    subjects: str = "",
    publisher: str = "",
) -> int:
    record = {
        "title": title,
        "subtitle": "",
        "authors": authors,
        "first_publish_year": None,
        "edition_count": None,
        "openlibrary_key": open_key,
        "cover_url": None,
        "isbn": None,
        "subjects": subjects,
        "publisher": publisher,
        "number_of_pages_median": None,
    }
    book_id, _ = store.add_or_update_book(record, allow_multiple=True)
    return book_id


def test_inventory_search_filters_and_subject_modes(client: TestClient, store: InventoryStore) -> None:
    mystery_id = _add_book(
        store,
        title="Mystery of the Manor",
        open_key="/works/ol-test-1",
        authors="Author One",
        subjects="Fiction, Mystery",
        publisher="Publisher A",
    )
    _add_book(
        store,
        title="Crime Scenes",
        open_key="/works/ol-test-2",
        authors="Author Two",
        subjects="Mystery, Crime",
        publisher="Publisher B",
    )
    _add_book(
        store,
        title="World History",
        open_key="/works/ol-test-3",
        authors="Author Three",
        subjects="History",
        publisher="Publisher C",
    )

    shelf_id = store.create_shelf("Shelf A")
    row_id = store.create_row(shelf_id, name="Row 1")
    store.set_placement(mystery_id, row_id, 1)

    response = client.get("/api/books/search", params=[("subjects", "Mystery")])
    assert response.status_code == 200
    titles = {book["title"] for book in response.json()}
    assert titles == {"Mystery of the Manor", "Crime Scenes"}

    response = client.get(
        "/api/books/search",
        params=[("subjects", "Mystery"), ("subjects", "Fiction"), ("subjects_mode", "all")],
    )
    assert response.status_code == 200
    titles = [book["title"] for book in response.json()]
    assert titles == ["Mystery of the Manor"]

    response = client.get("/api/books/search", params=[("authors", "Author Two")])
    assert response.status_code == 200
    titles = [book["title"] for book in response.json()]
    assert titles == ["Crime Scenes"]

    response = client.get("/api/books/search", params=[("shelves", "Shelf A")])
    assert response.status_code == 200
    titles = [book["title"] for book in response.json()]
    assert titles == ["Mystery of the Manor"]

    response = client.get("/api/books/search", params=[("shelves", "Unplaced")])
    assert response.status_code == 200
    titles = {book["title"] for book in response.json()}
    assert titles == {"Crime Scenes", "World History"}


def test_inventory_filters_endpoint_returns_enums(client: TestClient, store: InventoryStore) -> None:
    _add_book(
        store,
        title="Mystery of the Manor",
        open_key="/works/ol-enums-1",
        authors="Author One",
        subjects="Fiction, Mystery",
        publisher="Publisher A",
    )
    _add_book(
        store,
        title="World History",
        open_key="/works/ol-enums-2",
        authors="Author Two",
        subjects="History",
        publisher="Publisher B",
    )

    response = client.get("/api/books/filters")
    assert response.status_code == 200
    payload = response.json()
    assert "Mystery" in payload["subjects"]
    assert "History" in payload["subjects"]
    assert "Author One" in payload["authors"]
    assert "Publisher B" in payload["publishers"]
    assert "Unplaced" in payload["shelves"]

