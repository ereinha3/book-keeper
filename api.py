import json
import os
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import pandas
import requests

try:
    from olclient.openlibrary import OpenLibrary as _OpenLibrary  # type: ignore[import-not-found]
except ImportError as import_error:
    _OpenLibrary = None
    _OPEN_LIBRARY_IMPORT_ERROR = import_error
else:
    _OPEN_LIBRARY_IMPORT_ERROR = None


DEFAULT_COLUMNS = [
    "title",
    "subtitle",
    "authors",
    "publish_year",
    "edition_count",
    "openlibrary_key",
    "cover_url",
    "isbn",
    "subjects",
    "publisher",
    "number_of_pages_median",
]
COVER_URL_TEMPLATE = "https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"
PAGE_SIZE = 5

DEFAULT_API_FIELDS = [
    "title",
    "subtitle",
    "author_name",
    "publish_year",
    "edition_count",
    "cover_i",
    "isbn",
    "subject",
    "publisher",
    "number_of_pages_median",
    "key",
]

_OPEN_LIBRARY_CLIENT: Optional[Any] = None


def get_openlibrary_client():
    """Return a cached Open Library client instance."""
    if _OpenLibrary is None:
        raise ImportError(
            "The 'openlibrary-client' package is required. "
            "Install it with 'pip install openlibrary-client'."
        ) from _OPEN_LIBRARY_IMPORT_ERROR

    global _OPEN_LIBRARY_CLIENT
    if _OPEN_LIBRARY_CLIENT is None:
        _OPEN_LIBRARY_CLIENT = _OpenLibrary()
    return _OPEN_LIBRARY_CLIENT


@dataclass
class OpenLibraryQuery:
    """Encapsulates an Open Library search query."""

    title: Optional[str] = None
    author: Optional[str] = None
    year: Optional[int] = None
    general: Optional[str] = None
    limit: int = 25
    fields: List[str] = field(default_factory=lambda: list(DEFAULT_API_FIELDS))

    def to_params(self) -> Dict[str, str]:
        params: Dict[str, str] = {}
        if self.general:
            params["q"] = self.general
        if self.title:
            params["title"] = self.title
        if self.author:
            params["author"] = self.author
        if self.year:
            params["first_publish_year"] = str(self.year)
        params["limit"] = str(self.limit)
        if self.fields:
            params["fields"] = ",".join(self.fields)
        return params


def fetch_records(query: OpenLibraryQuery) -> List[Dict[str, Any]]:
    """Fetch matching records from the Open Library Search API."""
    params = query.to_params()
    try:
        client = get_openlibrary_client()
    except ImportError:
        client = None

    try:
        if client and hasattr(client, "get_ol_response"):
            path = "/search.json"
            if params:
                path = f"{path}?{urlencode(params)}"
            response = client.get_ol_response(path)  # type: ignore[operator]
        elif client and hasattr(client, "session"):
            response = client.session.get(  # type: ignore[attr-defined]
                "https://openlibrary.org/search.json",
                params=params,
                timeout=15,
            )
            response.raise_for_status()
        else:
            response = requests.get(
                "https://openlibrary.org/search.json",
                params=params,
                timeout=15,
            )
            response.raise_for_status()
        data = response.json()
    except Exception as error:  # pragma: no cover - defensive guard
        print(f"Unable to reach Open Library: {error}")
        return []

    docs = data.get("docs", []) if isinstance(data, dict) else []
    return rank_docs(query, docs or [])


def rank_docs(query: OpenLibraryQuery, docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort search results by a heuristic relevance score."""

    def compute_score(doc: Dict[str, Any]) -> float:
        score = 0.0

        title = (doc.get("title") or "").lower()
        authors = [name.lower() for name in doc.get("author_name", [])]
        subjects = ", ".join(doc.get("subject", [])).lower()

        if query.title:
            target_title = query.title.lower()
            ratio = SequenceMatcher(None, target_title, title).ratio()
            score += 5.0 * ratio
            if target_title == title:
                score += 2.0
            elif target_title in title:
                score += 1.0

        if query.author:
            target_author = query.author.lower()
            author_ratios = [
                SequenceMatcher(None, target_author, author).ratio() for author in authors
            ]
            best_author_ratio = max(author_ratios) if author_ratios else 0.0
            score += 4.0 * best_author_ratio
            if any(target_author in author for author in authors):
                score += 2.0

        if query.general:
            target_general = query.general.lower()
            haystack = " ".join(filter(None, [title, subjects, " ".join(authors)]))
            if target_general in haystack:
                score += 1.0

        if query.year and doc.get("first_publish_year"):
            try:
                year_value = int(doc["first_publish_year"])
            except (TypeError, ValueError):
                year_value = None
            if year_value is not None:
                difference = abs(query.year - year_value)
                if difference == 0:
                    score += 2.0
                else:
                    score += max(0.0, 1.0 - min(difference, 50) / 50.0)

        edition_count = doc.get("edition_count")
        if isinstance(edition_count, int):
            score += min(edition_count, 5) * 0.1

        return score

    scored_docs = [
        (index, compute_score(doc), doc) for index, doc in enumerate(docs)
    ]
    scored_docs.sort(key=lambda item: (-item[1], item[0]))
    return [doc for _, _, doc in scored_docs]


def describe_result(doc: Dict, index: int) -> str:
    """Return a printable description for an Open Library doc."""
    title = doc.get("title") or "Untitled"
    authors = ", ".join(doc.get("author_name", [])) or "Unknown author"
    publish_year = doc.get("first_publish_year")
    subjects = ", ".join(doc.get("subject", [])[:4])
    edition_count = doc.get("edition_count")
    cover_id = doc.get("cover_i")
    cover_url = COVER_URL_TEMPLATE.format(cover_id=cover_id) if cover_id else "N/A"

    lines = [
        f"{index}. {title}",
        f"   Author(s): {authors}",
    ]
    if publish_year:
        lines.append(f"   First Published: {publish_year}")
    if edition_count:
        lines.append(f"   Edition Count: {edition_count}")
    if subjects:
        lines.append(f"   Subjects: {subjects}")
    lines.append(f"   Cover URL: {cover_url}")
    return "\n".join(lines)


def ensure_columns(frame: pandas.DataFrame) -> pandas.DataFrame:
    """Ensure the DataFrame has the expected columns."""
    for column in DEFAULT_COLUMNS:
        if column not in frame.columns:
            frame[column] = pandas.NA
    return frame


def load_or_create_spreadsheet() -> Tuple[pandas.DataFrame, Path]:
    """Prompt the user to load an existing spreadsheet or create a new one."""
    while True:
        choice = input(
            "Would you like to load an existing spreadsheet or create a new one? "
            "(Enter 'load' or 'new'): "
        ).strip().lower()

        if choice not in {"load", "new"}:
            print("Please answer with 'load' or 'new'.")
            continue

        if choice == "load":
            path_input = input("Enter the absolute path to the spreadsheet file: ").strip()
            path = Path(path_input).expanduser()
            if not path.exists():
                print("That file does not exist. Please try again.")
                continue
            frame = read_spreadsheet(path)
            frame = ensure_columns(frame)
            return frame, path

        else:
            path = Path(os.getcwd()) / "books.xlsx"
            frame = pandas.DataFrame(columns=DEFAULT_COLUMNS)
            save_spreadsheet(frame, path)
            print(f"Created new spreadsheet at {path}")
            return frame, path



def read_spreadsheet(path: Path) -> pandas.DataFrame:
    """Read a spreadsheet from disk based on its extension."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pandas.read_csv(path)
    if suffix in {".xlsx", ".xls"}:
        return pandas.read_excel(path)
    raise ValueError("Supported spreadsheet formats are .csv, .xls, or .xlsx")


def save_spreadsheet(frame: pandas.DataFrame, path: Path) -> None:
    """Persist the DataFrame to disk."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        frame.to_csv(path, index=False)
    elif suffix in {".xlsx", ".xls"}:
        frame.to_excel(path, index=False)
    else:
        raise ValueError("Supported spreadsheet formats are .csv, .xls, or .xlsx")


def build_record(doc: Dict) -> Dict:
    """Create a spreadsheet-ready record from an Open Library doc."""
    cover_id = doc.get("cover_i")
    cover_url = COVER_URL_TEMPLATE.format(cover_id=cover_id) if cover_id else ""
    isbns_raw = doc.get("isbn")
    if isinstance(isbns_raw, list) and isbns_raw:
        isbn_value = str(isbns_raw[0])
    elif isbns_raw:
        isbn_value = str(isbns_raw)
    else:
        isbn_value = ""

    subjects = ", ".join(doc.get("subject", [])[:6]) if doc.get("subject") else ""
    authors = ", ".join(doc.get("author_name", [])) if doc.get("author_name") else ""

    publishers = doc.get("publisher")
    if isinstance(publishers, list) and publishers:
        publisher_value = str(publishers[0])
    elif publishers:
        publisher_value = str(publishers)
    else:
        publisher_value = ""

    pages = doc.get("number_of_pages_median")

    return {
        "title": doc.get("title", ""),
        "subtitle": doc.get("subtitle", ""),
        "authors": authors,
        "first_publish_year": doc.get("first_publish_year"),
        "edition_count": doc.get("edition_count"),
        "openlibrary_key": doc.get("key"),
        "cover_url": cover_url,
        "isbn": isbn_value,
        "subjects": subjects,
        "publisher": publisher_value,
        "number_of_pages_median": pages,
    }

