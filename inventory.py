from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from api import DEFAULT_COLUMNS

APP_DIR = Path.home() / ".moms_books"
APP_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_DB_PATH = APP_DIR / "library.db"


@dataclass
class PlacementInfo:
    book_id: int
    shelf_id: int
    shelf_name: str
    shelf_row_id: int
    row_name: str
    slot_index: int


class InventoryStore:
    """SQLite-backed store for the local library inventory."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.execute("PRAGMA foreign_keys = ON;")
        self._ensure_schema()

    # --------------------------------------------------------------------- #
    # Schema
    # --------------------------------------------------------------------- #
    def _ensure_schema(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS books (
                    id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL,
                    subtitle TEXT,
                    authors TEXT,
                    first_publish_year INTEGER,
                    edition_count INTEGER,
                    openlibrary_key TEXT,
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
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS shelves (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT
                );
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS shelf_rows (
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
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS placements (
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
            self._ensure_books_supports_copies()
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_books_title
                ON books(title COLLATE NOCASE);
                """
            )
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_books_authors
                ON books(authors COLLATE NOCASE);
                """
            )

    def _ensure_books_supports_copies(self) -> None:
        """Ensure the books table permits duplicate metadata for multiple copies."""
        with self._lock:
            # Clean up any previous failed migrations.
            self._conn.execute("DROP TABLE IF EXISTS books_backup;")
            indexes = self._conn.execute("PRAGMA index_list('books');").fetchall()
            needs_migration = False
            for index in indexes:
                unique = index["unique"] if isinstance(index, sqlite3.Row) else index[2]
                origin = index["origin"] if isinstance(index, sqlite3.Row) else index[3]
                # Origin "u" indicates an index created from a UNIQUE constraint.
                if unique == 1 and origin == "u":
                    needs_migration = True
                    break

            if not needs_migration:
                fk_rows = self._conn.execute("PRAGMA foreign_key_list('placements');").fetchall()
                fk_tables = {
                    row["table"] if isinstance(row, sqlite3.Row) else row[2] for row in fk_rows
                }
                if "books_backup" not in fk_tables:
                    return

            original_fk_state = self._conn.execute("PRAGMA foreign_keys;").fetchone()[0]

            with self._conn:
                try:
                    if original_fk_state:
                        self._conn.execute("PRAGMA foreign_keys = OFF;")

                    self._conn.execute("ALTER TABLE books RENAME TO books_backup;")
                    self._conn.execute(
                        """
                        CREATE TABLE books (
                            id INTEGER PRIMARY KEY,
                            title TEXT NOT NULL,
                            subtitle TEXT,
                            authors TEXT,
                            first_publish_year INTEGER,
                            edition_count INTEGER,
                            openlibrary_key TEXT,
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
                    columns = [
                        "id",
                        "title",
                        "subtitle",
                        "authors",
                        "first_publish_year",
                        "edition_count",
                        "openlibrary_key",
                        "cover_url",
                        "cover_path",
                        "isbn",
                        "subjects",
                        "publisher",
                        "number_of_pages_median",
                        "created_at",
                    ]
                    column_list = ", ".join(columns)
                    self._conn.execute(
                        f"""
                        INSERT INTO books ({column_list})
                        SELECT {column_list}
                        FROM books_backup;
                        """
                    )
                    self._conn.execute("DROP TABLE books_backup;")
                finally:
                    # Always ensure the temporary table is removed.
                    self._conn.execute("DROP TABLE IF EXISTS books_backup;")
                    if original_fk_state:
                        self._conn.execute("PRAGMA foreign_keys = ON;")
                    self._conn.execute("PRAGMA foreign_key_check;")

            fk_rows = self._conn.execute("PRAGMA foreign_key_list('placements');").fetchall()
            fk_tables = {
                row["table"] if isinstance(row, sqlite3.Row) else row[2] for row in fk_rows
            }
            if "books_backup" in fk_tables:
                with self._conn:
                    self._conn.execute(
                        """
                        CREATE TABLE placements_new (
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
                    self._conn.execute(
                        """
                        INSERT INTO placements_new (id, book_id, shelf_row_id, slot_index)
                        SELECT id, book_id, shelf_row_id, slot_index FROM placements;
                        """
                    )
                    self._conn.execute("DROP TABLE placements;")
                    self._conn.execute("ALTER TABLE placements_new RENAME TO placements;")

    # --------------------------------------------------------------------- #
    # Utility helpers
    # --------------------------------------------------------------------- #
    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # --------------------------------------------------------------------- #
    # Book management
    # --------------------------------------------------------------------- #
    def add_or_update_book(
        self,
        record: Dict[str, Any],
        *,
        cover_path: Optional[Path] = None,
        allow_multiple: bool = False,
    ) -> Tuple[int, bool]:
        """Insert a new book or update an existing one. Returns (book_id, created)."""

        def _insert() -> Tuple[int, bool]:
            columns = DEFAULT_COLUMNS + ["cover_path"]
            values = [record.get(column) for column in DEFAULT_COLUMNS]
            values.append(str(cover_path) if cover_path else None)
            placeholders = ", ".join("?" for _ in columns)
            self._conn.execute(
                f"""
                INSERT INTO books ({", ".join(columns)})
                VALUES ({placeholders})
                """,
                values,
            )
            book_id = self._conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            return int(book_id), True

        with self._lock, self._conn:
            if allow_multiple:
                return _insert()

            existing = None
            if record.get("openlibrary_key"):
                existing = self._conn.execute(
                    "SELECT * FROM books WHERE openlibrary_key = ?",
                    (record["openlibrary_key"],),
                ).fetchone()
            if existing is None and record.get("isbn"):
                existing = self._conn.execute(
                    "SELECT * FROM books WHERE isbn = ?",
                    (record["isbn"],),
                ).fetchone()

            if existing:
                book_id = existing["id"]
                payload = [
                    record.get("title") or existing["title"],
                    record.get("subtitle"),
                    record.get("authors"),
                    record.get("first_publish_year"),
                    record.get("edition_count"),
                    record.get("cover_url"),
                    str(cover_path) if cover_path else existing["cover_path"],
                    record.get("isbn"),
                    record.get("subjects"),
                    record.get("publisher"),
                    record.get("number_of_pages_median"),
                    book_id,
                ]
                self._conn.execute(
                    """
                    UPDATE books
                    SET title = ?, subtitle = ?, authors = ?, first_publish_year = ?,
                        edition_count = ?, cover_url = ?, cover_path = ?, isbn = ?,
                        subjects = ?, publisher = ?, number_of_pages_median = ?
                    WHERE id = ?
                    """,
                    payload,
                )
                return int(book_id), False

            return _insert()

    def update_cover_path(self, book_id: int, path: Optional[Path]) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE books SET cover_path = ? WHERE id = ?",
                (str(path) if path else None, book_id),
            )

    def list_books(self, search: str = "") -> List[Dict[str, Any]]:
        sql = """
            SELECT
                b.*,
                p.shelf_row_id,
                p.slot_index,
                sr.name AS row_name,
                sr.position AS row_position,
                sr.capacity AS row_capacity,
                s.id AS shelf_id,
                s.name AS shelf_name
            FROM books b
            LEFT JOIN placements p ON p.book_id = b.id
            LEFT JOIN shelf_rows sr ON sr.id = p.shelf_row_id
            LEFT JOIN shelves s ON s.id = sr.shelf_id
        """
        params: Tuple[Any, ...] = ()
        if search:
            search_like = f"%{search.lower()}%"
            sql += """
                WHERE lower(b.title) LIKE ?
                   OR lower(b.authors) LIKE ?
                   OR lower(b.publisher) LIKE ?
                   OR lower(COALESCE(b.isbn, '')) LIKE ?
            """
            params = (search_like, search_like, search_like, search_like)
        sql += " ORDER BY lower(b.title);"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_book(self, book_id: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT
                    b.*,
                    p.shelf_row_id,
                    p.slot_index,
                    sr.name AS row_name,
                    sr.position AS row_position,
                    sr.capacity AS row_capacity,
                    s.id AS shelf_id,
                    s.name AS shelf_name
                FROM books b
                LEFT JOIN placements p ON p.book_id = b.id
                LEFT JOIN shelf_rows sr ON sr.id = p.shelf_row_id
                LEFT JOIN shelves s ON s.id = sr.shelf_id
                WHERE b.id = ?
                """,
                (book_id,),
            ).fetchone()
        return dict(row) if row else None

    def delete_book(self, book_id: int) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM books WHERE id = ?", (book_id,))

    def search_books(self, term: str) -> List[Dict[str, Any]]:
        return self.list_books(term)

    def get_unplaced_books(self) -> List[Dict[str, Any]]:
        sql = """
            SELECT b.*
            FROM books b
            LEFT JOIN placements p ON p.book_id = b.id
            WHERE p.id IS NULL
            ORDER BY lower(b.title);
        """
        with self._lock:
            rows = self._conn.execute(sql).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------ #
    # Shelf management
    # ------------------------------------------------------------------ #
    def list_shelves(self) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT
                    s.*,
                    COUNT(sr.id) AS row_count,
                    COALESCE(SUM(sr.capacity), 0) AS capacity
                FROM shelves s
                LEFT JOIN shelf_rows sr ON sr.shelf_id = s.id
                GROUP BY s.id
                ORDER BY lower(s.name);
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def create_shelf(self, name: str, description: str = "") -> int:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO shelves (name, description) VALUES (?, ?);",
                (name, description or None),
            )
            shelf_id = self._conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        return int(shelf_id)

    def update_shelf(self, shelf_id: int, *, name: str, description: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE shelves SET name = ?, description = ? WHERE id = ?;",
                (name, description or None, shelf_id),
            )

    def delete_shelf(self, shelf_id: int) -> None:
        with self._lock:
            has_rows = (
                self._conn.execute(
                    "SELECT 1 FROM shelf_rows WHERE shelf_id = ? LIMIT 1;",
                    (shelf_id,),
                ).fetchone()
                is not None
            )
            if has_rows:
                raise ValueError("Cannot delete a shelf that still has rows.")
            with self._conn:
                self._conn.execute("DELETE FROM shelves WHERE id = ?;", (shelf_id,))

    def list_rows(self, shelf_id: int) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT
                    sr.*,
                    COUNT(p.id) AS used,
                    COALESCE(MAX(p.slot_index), 0) AS max_slot
                FROM shelf_rows sr
                LEFT JOIN placements p ON p.shelf_row_id = sr.id
                WHERE sr.shelf_id = ?
                GROUP BY sr.id
                ORDER BY sr.position;
                """,
                (shelf_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_row(self, row_id: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT
                    sr.*,
                    COUNT(p.id) AS used,
                    s.name AS shelf_name
                FROM shelf_rows sr
                LEFT JOIN shelves s ON s.id = sr.shelf_id
                LEFT JOIN placements p ON p.shelf_row_id = sr.id
                WHERE sr.id = ?
                GROUP BY sr.id;
                """,
                (row_id,),
            ).fetchone()
        return dict(row) if row else None

    def create_row(
        self,
        shelf_id: int,
        *,
        name: Optional[str] = None,
        capacity: Optional[int] = None,
    ) -> int:
        with self._lock, self._conn:
            next_position = (
                self._conn.execute(
                    "SELECT COALESCE(MAX(position), 0) + 1 FROM shelf_rows WHERE shelf_id = ?;",
                    (shelf_id,),
                ).fetchone()[0]
            )
            self._conn.execute(
                """
                INSERT INTO shelf_rows (shelf_id, name, position, capacity)
                VALUES (?, ?, ?, ?);
                """,
                (shelf_id, name or None, next_position, capacity or 0),
            )
            row_id = self._conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        return int(row_id)

    def update_row(
        self,
        row_id: int,
        *,
        name: Optional[str] = None,
        capacity: Optional[int] = None,
    ) -> None:
        with self._lock:
            with self._conn:
                assignments = []
                values: List[Any] = []
                if name is not None:
                    assignments.append("name = ?")
                    values.append(name or None)
                if capacity is not None:
                    assignments.append("capacity = ?")
                    values.append(capacity)
                if assignments:
                    values.append(row_id)
                    self._conn.execute(
                        f"UPDATE shelf_rows SET {', '.join(assignments)} WHERE id = ?;",
                        values,
                    )

    def delete_row(self, row_id: int) -> None:
        with self._lock:
            has_placements = (
                self._conn.execute(
                    "SELECT 1 FROM placements WHERE shelf_row_id = ? LIMIT 1;",
                    (row_id,),
                ).fetchone()
                is not None
            )
            if has_placements:
                raise ValueError("Cannot delete a row that still contains books.")
            with self._conn:
                self._conn.execute("DELETE FROM shelf_rows WHERE id = ?;", (row_id,))

    # ------------------------------------------------------------------ #
    # Placements
    # ------------------------------------------------------------------ #
    def set_placement(self, book_id: int, shelf_row_id: int, slot_index: int) -> None:
        if slot_index < 1:
            raise ValueError("slot_index must be 1 or greater.")

        with self._lock:
            row = self._conn.execute(
                "SELECT id FROM shelf_rows WHERE id = ?;",
                (shelf_row_id,),
            ).fetchone()
            if row is None:
                raise ValueError("Row not found.")

            slot_taken = self._conn.execute(
                """
                SELECT 1 FROM placements
                WHERE shelf_row_id = ? AND slot_index = ? AND book_id != ?;
                """,
                (shelf_row_id, slot_index, book_id),
            ).fetchone()
            if slot_taken:
                raise ValueError("Another book already occupies this slot.")

            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO placements (book_id, shelf_row_id, slot_index)
                    VALUES (?, ?, ?)
                    ON CONFLICT(book_id) DO UPDATE SET
                        shelf_row_id = excluded.shelf_row_id,
                        slot_index = excluded.slot_index;
                    """,
                    (book_id, shelf_row_id, slot_index),
                )
                self._conn.execute(
                    """
                    UPDATE shelf_rows
                    SET capacity = MAX(capacity, ?)
                    WHERE id = ?;
                    """,
                    (slot_index, shelf_row_id),
                )

    def remove_placement(self, book_id: int) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM placements WHERE book_id = ?;", (book_id,))

    def get_placement(self, book_id: int) -> Optional[PlacementInfo]:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT
                    p.book_id,
                    sr.shelf_id,
                    s.name AS shelf_name,
                    p.shelf_row_id,
                    COALESCE(sr.name, 'Row ' || sr.position) AS row_name,
                    p.slot_index
                FROM placements p
                JOIN shelf_rows sr ON sr.id = p.shelf_row_id
                JOIN shelves s ON s.id = sr.shelf_id
                WHERE p.book_id = ?;
                """,
                (book_id,),
            ).fetchone()
        if row is None:
            return None
        return PlacementInfo(
            book_id=row["book_id"],
            shelf_id=row["shelf_id"],
            shelf_name=row["shelf_name"],
            shelf_row_id=row["shelf_row_id"],
            row_name=row["row_name"],
            slot_index=row["slot_index"],
        )

    def list_rows_with_shelves(self) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT
                    sr.*,
                    s.name AS shelf_name,
                    s.id AS shelf_id,
                    COUNT(p.id) AS used,
                    COALESCE(MAX(p.slot_index), 0) AS max_slot
                FROM shelf_rows sr
                JOIN shelves s ON s.id = sr.shelf_id
                LEFT JOIN placements p ON p.shelf_row_id = sr.id
                GROUP BY sr.id
                ORDER BY lower(s.name), sr.position;
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_shelf_structure(self) -> List[Dict[str, Any]]:
        """Return nested shelf -> rows -> placements for visualisation."""
        shelves = []
        with self._lock:
            shelf_rows = self._conn.execute(
                "SELECT * FROM shelves ORDER BY lower(name);"
            ).fetchall()
            for shelf in shelf_rows:
                rows = self._conn.execute(
                    """
                    SELECT *
                    FROM shelf_rows
                    WHERE shelf_id = ?
                    ORDER BY position;
                    """,
                    (shelf["id"],),
                ).fetchall()
                row_entries = []
                for row in rows:
                    placements = self._conn.execute(
                        """
                        SELECT
                            p.slot_index,
                            b.id AS book_id,
                            b.title,
                            b.authors,
                            b.cover_path
                        FROM placements p
                        JOIN books b ON b.id = p.book_id
                        WHERE p.shelf_row_id = ?
                        ORDER BY p.slot_index;
                        """,
                        (row["id"],),
                    ).fetchall()
                    row_entries.append(
                        {
                            "row": dict(row),
                            "placements": [dict(p) for p in placements],
                        }
                    )
                shelves.append({"shelf": dict(shelf), "rows": row_entries})
        return shelves

    def reorder_row(self, row_id: int, book_ids: List[int]) -> None:
        with self._lock, self._conn:
            placeholders = ",".join("?" for _ in book_ids)
            if book_ids:
                self._conn.execute(
                    f"""
                    DELETE FROM placements
                    WHERE shelf_row_id = ?
                      AND book_id NOT IN ({placeholders})
                    """,
                    (row_id, *book_ids),
                )
            else:
                self._conn.execute(
                    "DELETE FROM placements WHERE shelf_row_id = ?;",
                    (row_id,),
                )

            for index, book_id in enumerate(book_ids, start=1):
                self._conn.execute(
                    """
                    INSERT INTO placements (book_id, shelf_row_id, slot_index)
                    VALUES (?, ?, ?)
                    ON CONFLICT(book_id) DO UPDATE SET
                        shelf_row_id = excluded.shelf_row_id,
                        slot_index = excluded.slot_index;
                    """,
                    (book_id, row_id, index),
                )

            self._conn.execute(
                "UPDATE shelf_rows SET capacity = ? WHERE id = ?;",
                (len(book_ids), row_id),
            )


# ------------------------------------------------------------------------------
# Convenience factory
# ------------------------------------------------------------------------------
def get_store(db_path: Optional[Path] = None) -> InventoryStore:
    return InventoryStore(db_path=db_path)

