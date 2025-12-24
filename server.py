from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from api import COVER_URL_TEMPLATE, OpenLibraryQuery, build_record, fetch_records
from inventory import InventoryStore
from media import COVERS_DIR, fetch_and_cache_cover
from enrichment import get_enriched_record


# -----------------------------------------------------------------------------
# Application setup
# -----------------------------------------------------------------------------

app = FastAPI(title="Mom's Books API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_store() -> InventoryStore:
    if not hasattr(get_store, "_instance"):
        get_store._instance = InventoryStore()
    return get_store._instance  # type: ignore[attr-defined]


@app.on_event("shutdown")
def _shutdown() -> None:
    store = getattr(get_store, "_instance", None)
    if isinstance(store, InventoryStore):
        store.close()


# -----------------------------------------------------------------------------
# Pydantic models
# -----------------------------------------------------------------------------


class SearchResponse(BaseModel):
    results: List[Dict[str, Any]]
    total: int
    page: int
    page_size: int


class BookCreate(BaseModel):
    document: Dict[str, Any]


class ShelfPayload(BaseModel):
    name: str
    description: Optional[str] = None


class RowPayload(BaseModel):
    name: Optional[str] = None
    capacity: Optional[int] = Field(default=None, ge=1)


class PlacementPayload(BaseModel):
    shelf_row_id: int
    slot_index: int = Field(..., ge=1)


class RowOrderPayload(BaseModel):
    book_ids: List[int] = Field(default_factory=list)


class BookSummary(BaseModel):
    book: Dict[str, Any]
    description: Optional[str] = None
    subjects: List[str] = Field(default_factory=list)
    openlibrary_url: Optional[str] = None


class InventoryFilters(BaseModel):
    subjects: List[str] = Field(default_factory=list)
    authors: List[str] = Field(default_factory=list)
    publishers: List[str] = Field(default_factory=list)
    shelves: List[str] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# Helper utilities
# -----------------------------------------------------------------------------


def _serialize(obj: Any) -> Any:
    """Ensure values returned from SQLite are JSON-serializable."""
    if obj is None:
        return None
    if isinstance(obj, Path):
        return str(obj)
    return obj


def _cover_asset(value: Any) -> Optional[str]:
    if not value:
        return None
    try:
        path = Path(value)
    except TypeError:
        return None
    filename = path.name
    target = COVERS_DIR / filename
    if not target.exists():
        return None
    return f"/api/covers/{filename}"


def _normalize_record(record: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not record:
        return {}
    normalized = {key: _serialize(value) for key, value in record.items()}
    normalized["cover_asset"] = _cover_asset(normalized.get("cover_path"))
    return normalized


def _resolve_cover_url(document: Dict[str, Any]) -> Optional[str]:
    url = document.get("cover_url")
    if url:
        return url
    cover_id = document.get("cover_i")
    if cover_id:
        return COVER_URL_TEMPLATE.format(cover_id=cover_id)
    return None


def _best_identifier(record: Dict[str, Any]) -> str:
    return (
        record.get("openlibrary_key")
        or record.get("isbn")
        or record.get("title")
        or str(record.get("id", "book"))
    )


SEARCH_FIELD_GROUPS: Dict[str, List[str]] = {
    "all": [
        "title",
        "subtitle",
        "authors",
        "subjects",
        "publisher",
        "isbn",
    ],
    "title": ["title", "subtitle"],
    "author": ["authors"],
    "publisher": ["publisher"],
    "subjects": ["subjects"],
    "isbn": ["isbn"],
}


def _collect_text(book: Dict[str, Any], fields: List[str]) -> str:
    parts: List[str] = []
    for field in fields:
        value = book.get(field)
        if value:
            parts.append(str(value))
    return " ".join(parts).lower()


def _score_book(book: Dict[str, Any], words: List[str], fields: List[str]) -> int:
    if not words:
        return 0
    haystack = _collect_text(book, fields)
    if not haystack:
        return 0
    score = 0
    for word in words:
        score += haystack.count(word)
    return score


def _split_field(value: Optional[str]) -> List[str]:
    if not value:
        return []
    items = [part for part in str(value).split(",")]
    return [item.strip() for item in items if item and item.strip()]


def _split_field_lower(value: Optional[str]) -> Set[str]:
    return {item.lower() for item in _split_field(value)}


def _unique_sorted(values: Iterable[str]) -> List[str]:
    seen: Dict[str, str] = {}
    for value in values:
        if not value:
            continue
        candidate = value.strip()
        if not candidate:
            continue
        key = candidate.lower()
        if key not in seen:
            seen[key] = candidate
    return sorted(seen.values(), key=lambda item: item.lower())


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/search", response_model=SearchResponse)
def search_books(
    q: Optional[str] = Query(None),
    title: Optional[str] = None,
    author: Optional[str] = None,
    year: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
) -> SearchResponse:
    query = OpenLibraryQuery(
        general=q or None,
        title=title or None,
        author=author or None,
        year=year,
        limit=page_size,
    )
    results, total = fetch_records(query, offset=(page - 1) * page_size)
    return SearchResponse(results=results, total=total, page=page, page_size=page_size)


@app.get("/api/books")
def list_books(
    search: Optional[str] = Query(None),
    store: InventoryStore = Depends(get_store),
) -> List[Dict[str, Any]]:
    books = store.list_books(search or "")
    return [_normalize_record(book) for book in books]


@app.get("/api/books/search")
def search_books_inventory(
    q: Optional[str] = Query(None, description="General search query"),
    category: str = Query("all", pattern="^(all|title|author|publisher|subjects|isbn)$"),
    subjects: Optional[List[str]] = Query(None, description="Filter by one or more subjects"),
    subjects_mode: str = Query("any", pattern="^(any|all)$"),
    authors: Optional[List[str]] = Query(None, description="Filter by authors"),
    publishers: Optional[List[str]] = Query(None, description="Filter by publishers"),
    shelves: Optional[List[str]] = Query(None, description="Filter by shelf name or Unplaced"),
    store: InventoryStore = Depends(get_store),
) -> List[Dict[str, Any]]:
    books = store.list_books()
    if not q or not q.strip():
        filtered = books[:]
    else:
        words = [word for word in re.split(r"\s+", q.lower()) if word]
        if not words:
            filtered = books[:]
        else:
            fields = SEARCH_FIELD_GROUPS.get(category, SEARCH_FIELD_GROUPS["all"])
            ranked: List[tuple[int, Dict[str, Any]]] = []
            for book in books:
                score = _score_book(book, words, fields if category != "all" else SEARCH_FIELD_GROUPS["all"])
                if score > 0:
                    ranked.append((score, book))

            if not ranked:
                filtered = []
            else:
                ranked.sort(
                    key=lambda item: (
                        -item[0],
                        (item[1].get("title") or "").lower(),
                        item[1].get("id") or 0,
                    )
                )
                filtered = [book for _, book in ranked]

    subject_filters = [value.strip().lower() for value in (subjects or []) if value and value.strip()]
    author_filters = [value.strip().lower() for value in (authors or []) if value and value.strip()]
    publisher_filters = [value.strip().lower() for value in (publishers or []) if value and value.strip()]
    shelf_filters = [value.strip().lower() for value in (shelves or []) if value and value.strip()]

    if subject_filters:
        def subjects_match(book: Dict[str, Any]) -> bool:
            values = _split_field_lower(book.get("subjects"))
            if not values:
                return False
            if subjects_mode == "all":
                return all(subject in values for subject in subject_filters)
            return any(subject in values for subject in subject_filters)

        filtered = [book for book in filtered if subjects_match(book)]

    if author_filters:
        def authors_match(book: Dict[str, Any]) -> bool:
            authors_value = _split_field_lower(book.get("authors"))
            if not authors_value:
                return False
            return any(author in authors_value for author in author_filters)

        filtered = [book for book in filtered if authors_match(book)]

    if publisher_filters:
        def publishers_match(book: Dict[str, Any]) -> bool:
            publisher = str(book.get("publisher") or "").strip().lower()
            if not publisher:
                return False
            return publisher in publisher_filters

        filtered = [book for book in filtered if publishers_match(book)]

    if shelf_filters:
        def shelves_match(book: Dict[str, Any]) -> bool:
            name = (book.get("shelf_name") or "").strip()
            if not name:
                return "unplaced" in shelf_filters
            return name.lower() in shelf_filters

        filtered = [book for book in filtered if shelves_match(book)]

    return [_normalize_record(book) for book in filtered]


@app.get("/api/books/filters", response_model=InventoryFilters)
def get_inventory_filters(store: InventoryStore = Depends(get_store)) -> InventoryFilters:
    books = store.list_books()
    subjects: List[str] = []
    authors: List[str] = []
    publishers: List[str] = []
    shelves: List[str] = []

    for book in books:
        subjects.extend(_split_field(book.get("subjects")))
        authors.extend(_split_field(book.get("authors")))
        publisher = (book.get("publisher") or "").strip()
        if publisher:
            publishers.append(publisher)
        shelf = (book.get("shelf_name") or "").strip()
        if shelf:
            shelves.append(shelf)
        else:
            shelves.append("Unplaced")

    return InventoryFilters(
        subjects=_unique_sorted(subjects),
        authors=_unique_sorted(authors),
        publishers=_unique_sorted(publishers),
        shelves=_unique_sorted(shelves),
    )


@app.get("/api/books/{book_id}")
def get_book(book_id: int, store: InventoryStore = Depends(get_store)) -> Dict[str, Any]:
    record = store.get_book(book_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")
    return _normalize_record(record)


@app.post("/api/books", status_code=status.HTTP_201_CREATED)
def create_book(
    payload: BookCreate,
    store: InventoryStore = Depends(get_store),
) -> Dict[str, Any]:
    document = payload.document
    record = build_record(document)

    identifier = (
        record.get("openlibrary_key")
        or record.get("isbn")
        or document.get("key")
        or document.get("id")
        or record.get("title")
    )

    cover_path: Optional[Path] = None
    cover_url = _resolve_cover_url(document)
    if cover_url and identifier:
        cover_path = fetch_and_cache_cover(cover_url, identifier, max_edge=None)
        if cover_path:
            record["cover_url"] = cover_url

    enriched = get_enriched_record(record)
    if enriched.subjects and not record.get("subjects"):
        record["subjects"] = ", ".join(enriched.subjects)
    if enriched.description and not record.get("description"):
        record["description"] = enriched.description

    if not cover_path and enriched.cover_url and identifier:
        cached = fetch_and_cache_cover(enriched.cover_url, identifier, max_edge=None)
        if cached:
            cover_path = cached
            record["cover_url"] = enriched.cover_url
    if not record.get("cover_url") and enriched.cover_url:
        record["cover_url"] = enriched.cover_url

    book_id, _created = store.add_or_update_book(record, cover_path=cover_path, allow_multiple=True)
    saved = store.get_book(book_id)
    if not saved:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save book")
    return _normalize_record(saved)


@app.delete("/api/books/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_book(book_id: int, store: InventoryStore = Depends(get_store)) -> None:
    if not store.get_book(book_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")
    store.delete_book(book_id)


@app.post("/api/books/{book_id}/placement")
def assign_placement(
    book_id: int,
    payload: PlacementPayload,
    store: InventoryStore = Depends(get_store),
) -> Dict[str, Any]:
    # Ensure schemas are up to date before attempting placements in case
    # this instance is using an older database snapshot.
    try:
        store._ensure_books_supports_copies()  # type: ignore[attr-defined]
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to prepare storage schema: {exc}",
        )
    if not store.get_book(book_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")
    try:
        store.set_placement(book_id, payload.shelf_row_id, payload.slot_index)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    saved = store.get_book(book_id)
    if not saved:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to update placement")
    return _normalize_record(saved)


@app.delete("/api/books/{book_id}/placement", status_code=status.HTTP_204_NO_CONTENT)
def remove_placement(book_id: int, store: InventoryStore = Depends(get_store)) -> None:
    store.remove_placement(book_id)


@app.get("/api/shelves")
def list_shelves(store: InventoryStore = Depends(get_store)) -> List[Dict[str, Any]]:
    shelves = store.list_shelves()
    return [_normalize_record(shelf) for shelf in shelves]


@app.post("/api/shelves", status_code=status.HTTP_201_CREATED)
def create_shelf(payload: ShelfPayload, store: InventoryStore = Depends(get_store)) -> Dict[str, Any]:
    shelf_id = store.create_shelf(payload.name, payload.description or "")
    shelf = next((s for s in store.list_shelves() if s["id"] == shelf_id), None)
    if not shelf:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create shelf")
    return _normalize_record(shelf)


@app.put("/api/shelves/{shelf_id}")
def update_shelf(
    shelf_id: int,
    payload: ShelfPayload,
    store: InventoryStore = Depends(get_store),
) -> Dict[str, Any]:
    try:
        store.update_shelf(shelf_id, name=payload.name, description=payload.description or "")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    shelf = next((s for s in store.list_shelves() if s["id"] == shelf_id), None)
    if not shelf:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shelf not found")
    return _normalize_record(shelf)


@app.delete("/api/shelves/{shelf_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shelf(shelf_id: int, store: InventoryStore = Depends(get_store)) -> None:
    try:
        store.delete_shelf(shelf_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@app.get("/api/shelves/{shelf_id}/rows")
def list_rows(shelf_id: int, store: InventoryStore = Depends(get_store)) -> List[Dict[str, Any]]:
    rows = store.list_rows(shelf_id)
    return [_normalize_record(row) for row in rows]


@app.post("/api/shelves/{shelf_id}/rows", status_code=status.HTTP_201_CREATED)
def create_row(
    shelf_id: int,
    payload: RowPayload,
    store: InventoryStore = Depends(get_store),
) -> Dict[str, Any]:
    try:
        row_id = store.create_row(shelf_id, name=payload.name, capacity=payload.capacity)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    row = store.get_row(row_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create row")
    return _normalize_record(row)


@app.put("/api/rows/{row_id}")
def update_row(
    row_id: int,
    payload: RowPayload,
    store: InventoryStore = Depends(get_store),
) -> Dict[str, Any]:
    try:
        store.update_row(row_id, name=payload.name, capacity=payload.capacity)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    row = store.get_row(row_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")
    return _normalize_record(row)


@app.delete("/api/rows/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_row(row_id: int, store: InventoryStore = Depends(get_store)) -> None:
    try:
        store.delete_row(row_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@app.put(
    "/api/rows/{row_id}/order",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
def reorder_row(
    row_id: int,
    payload: RowOrderPayload,
    store: InventoryStore = Depends(get_store),
) -> Response:
    store.reorder_row(row_id, payload.book_ids)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/shelf-structure")
def shelf_structure(store: InventoryStore = Depends(get_store)) -> List[Dict[str, Any]]:
    data = store.get_shelf_structure()
    # ensure any file paths are strings
    for block in data:
        for placement in block.get("rows", []):
            for entry in placement.get("placements", []):
                entry["cover_path"] = _serialize(entry.get("cover_path"))
                entry["cover_asset"] = _cover_asset(entry.get("cover_path"))
    return data


@app.get("/api/unplaced-books")
def unplaced_books(store: InventoryStore = Depends(get_store)) -> List[Dict[str, Any]]:
    books = store.get_unplaced_books()
    return [_normalize_record(book) for book in books]


@app.get("/api/covers/{filename}")
def cover_image(filename: str) -> FileResponse:
    safe_name = Path(filename).name
    target = COVERS_DIR / safe_name
    if not target.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cover not found")
    return FileResponse(target)


@app.get("/api/books/{book_id}/summary", response_model=BookSummary)
def book_summary(book_id: int, store: InventoryStore = Depends(get_store)) -> BookSummary:
    record = store.get_book(book_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")

    normalized = _normalize_record(record)
    enriched = get_enriched_record(record)

    identifier = _best_identifier(record)
    if not normalized.get("cover_asset") and enriched.cover_url:
        cached = fetch_and_cache_cover(enriched.cover_url, identifier, max_edge=None)
        if cached:
            store.update_cover_path(book_id, cached)
            normalized["cover_path"] = str(cached)
            normalized["cover_asset"] = _cover_asset(str(cached))
            normalized["cover_url"] = enriched.cover_url

    description = (
        enriched.description
        or record.get("description")
        or normalized.get("description")
        or None
    )

    existing_subjects = []
    if record.get("subjects"):
        existing_subjects = [part.strip() for part in str(record["subjects"]).split(",") if part.strip()]

    combined_subjects: List[str] = []

    def _extend(items: Iterable[str]):
        for item in items:
            value = item.strip()
            if value and value not in combined_subjects:
                combined_subjects.append(value)

    _extend(enriched.subjects)
    _extend(existing_subjects)

    openlibrary_key = enriched.openlibrary_key or record.get("openlibrary_key")
    openlibrary_url = f"https://openlibrary.org{openlibrary_key}" if openlibrary_key else None

    return BookSummary(
        book=normalized,
        description=description,
        subjects=combined_subjects,
        openlibrary_url=openlibrary_url,
    )

