from __future__ import annotations

from pathlib import Path

from inventory import InventoryStore


def _make_book(index: int) -> dict[str, object]:
    return {
        "title": f"Book {index}",
        "subtitle": "",
        "authors": f"Author {index}",
        "first_publish_year": None,
        "edition_count": None,
        "openlibrary_key": f"/works/OL{index}",
        "cover_url": None,
        "isbn": None,
        "subjects": "Test",
        "publisher": "Test Pub",
        "number_of_pages_median": None,
    }


def _create_store(tmp_path: Path) -> InventoryStore:
    db_path = tmp_path / "placements.db"
    if db_path.exists():
        db_path.unlink()
    return InventoryStore(db_path=db_path)


def test_set_placement_inserts_into_middle(tmp_path: Path) -> None:
    store = _create_store(tmp_path)
    shelf_id = store.create_shelf("Shelf One")
    row_id = store.create_row(shelf_id, name="Row A")

    book_ids = []
    for idx in range(3):
        book_id, created = store.add_or_update_book(_make_book(idx), allow_multiple=True)
        assert created
        book_ids.append(book_id)

    store.set_placement(book_ids[0], row_id, 1)
    store.set_placement(book_ids[1], row_id, 2)
    store.set_placement(book_ids[2], row_id, 2)  # insert in the middle, expect existing elements to shift

    placements = store.get_shelf_structure()[0]["rows"][0]["placements"]
    assert [p["book_id"] for p in placements] == [book_ids[0], book_ids[2], book_ids[1]]
    assert [p["slot_index"] for p in placements] == [1, 2, 3]
    store.close()


def test_set_placement_moves_between_rows_and_reindexes(tmp_path: Path) -> None:
    store = _create_store(tmp_path)
    shelf_id = store.create_shelf("Shelf One")
    row_a = store.create_row(shelf_id, name="Row A")
    row_b = store.create_row(shelf_id, name="Row B")

    first_id, _ = store.add_or_update_book(_make_book(10), allow_multiple=True)
    second_id, _ = store.add_or_update_book(_make_book(11), allow_multiple=True)

    store.set_placement(first_id, row_a, 1)
    store.set_placement(second_id, row_a, 2)

    # Move the first book over to Row B at the leading slot.
    store.set_placement(first_id, row_b, 1)

    structure = store.get_shelf_structure()[0]["rows"]
    placements_a = next(row for row in structure if row["row"]["id"] == row_a)["placements"]
    placements_b = next(row for row in structure if row["row"]["id"] == row_b)["placements"]

    assert [p["book_id"] for p in placements_a] == [second_id]
    assert [p["slot_index"] for p in placements_a] == [1]
    assert [p["book_id"] for p in placements_b] == [first_id]
    assert [p["slot_index"] for p in placements_b] == [1]
    store.close()

