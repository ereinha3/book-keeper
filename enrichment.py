from __future__ import annotations

import re
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import requests

from api import COVER_URL_TEMPLATE


@dataclass
class NormalizedBook:
    source: str
    title: Optional[str]
    authors: List[str] = field(default_factory=list)
    publisher: Optional[str] = None
    year: Optional[int] = None
    isbn_set: Set[str] = field(default_factory=set)
    cover_url: Optional[str] = None
    description: Optional[str] = None
    subjects: List[str] = field(default_factory=list)
    openlibrary_key: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


def _normalize_isbn(*values: Optional[str]) -> Set[str]:
    isbn_re = re.compile(r"[0-9Xx]{10,13}")
    results: Set[str] = set()
    for value in values:
        if not value:
            continue
        if isinstance(value, str):
            matches = isbn_re.findall(value)
            for match in matches:
                results.add(match.upper())
        elif isinstance(value, Iterable):
            for item in value:
                for match in isbn_re.findall(str(item)):
                    results.add(match.upper())
    return results


def normalize_openlibrary(doc: Dict[str, Any]) -> NormalizedBook:
    authors = doc.get("author_name") or doc.get("authors") or []
    if isinstance(authors, str):
        authors = [authors]
    isbn_set = _normalize_isbn(doc.get("isbn"), doc.get("isbn_10"), doc.get("isbn_13"))
    cover = None
    cover_id = doc.get("cover_i")
    if cover_id:
        cover = COVER_URL_TEMPLATE.format(cover_id=cover_id)
    elif doc.get("cover_url"):
        cover = doc["cover_url"]
    description = doc.get("description")
    if isinstance(description, dict):
        description = description.get("value") or description.get("brief")
    subjects = doc.get("subject") or []
    if isinstance(subjects, str):
        subjects = [subjects]
    year = doc.get("first_publish_year") or doc.get("publish_year")
    if isinstance(year, list):
        year = year[0]
    try:
        year = int(year)
    except (TypeError, ValueError):
        year = None
    return NormalizedBook(
        source="openlibrary",
        title=doc.get("title"),
        authors=[str(a) for a in authors if a],
        publisher=(doc.get("publisher") or [None])[0]
        if isinstance(doc.get("publisher"), list)
        else doc.get("publisher"),
        year=year,
        isbn_set=isbn_set,
        cover_url=cover,
        description=description,
        subjects=[str(s) for s in subjects if s],
        openlibrary_key=doc.get("key") or doc.get("openlibrary_key"),
        raw=doc,
    )


def fetch_loc_books(record: NormalizedBook) -> List[NormalizedBook]:
    queries: List[str] = []
    if record.isbn_set:
        isbn = next(iter(record.isbn_set))
        queries.append(f"isbn:{isbn}")
    if record.title:
        query = f'title:"{record.title}"'
        if record.authors:
            query += f' AND author:"{record.authors[0]}"'
        queries.append(query)
    results: List[NormalizedBook] = []
    for query in queries:
        try:
            response = requests.get(
                "https://www.loc.gov/books/",
                params={"q": query, "fo": "json"},
                timeout=8,
            )
            response.raise_for_status()
        except requests.RequestException:
            continue
        data = response.json()
        for item in data.get("results", []):
            title = item.get("title")
            authors = item.get("contributor") or item.get("creator") or []
            if isinstance(authors, str):
                authors = [authors]
            subjects = item.get("subject_headings") or item.get("subjects") or []
            if isinstance(subjects, str):
                subjects = [subjects]
            description = item.get("description")
            if isinstance(description, list):
                description = " ".join(str(part) for part in description if part)
            elif isinstance(description, dict):
                description = description.get("value") or description.get("brief")
            publishers = item.get("publisher") or []
            if isinstance(publishers, str):
                publishers = [publishers]
            year = item.get("date") or item.get("published")
            try:
                year_int = int(re.findall(r"\d{4}", str(year))[0]) if year else None
            except (ValueError, IndexError):
                year_int = None
            image_urls = item.get("image_url") or []
            if isinstance(image_urls, str):
                image_urls = [image_urls]
            cover_url = next((url for url in image_urls if url), None)
            results.append(
                NormalizedBook(
                    source="loc",
                    title=item.get("title") or title,
                    authors=[str(a) for a in authors if a],
                    publisher=(publishers[0] if publishers else None),
                    year=year_int,
                    isbn_set=_normalize_isbn(item.get("isbn"), item.get("isbn_10"), item.get("isbn_13")),
                    cover_url=cover_url,
                    description=description,
                    subjects=[str(subject) for subject in subjects if subject],
                    raw=item,
                )
            )
        if results:
            break
    return results


def fetch_ia_books(record: NormalizedBook) -> List[NormalizedBook]:
    query_parts = []
    if record.title:
        query_parts.append(f'title:"{record.title}"')
    if record.authors:
        query_parts.append(f'creator:"{record.authors[0]}"')
    if not query_parts:
        return []
    query = " AND ".join(query_parts)
    try:
        response = requests.get(
            "https://archive.org/advancedsearch.php",
            params={
                "q": query,
                "fields": "identifier,title,creator,year,publisher",
                "rows": "5",
                "output": "json",
            },
            timeout=8,
        )
        response.raise_for_status()
    except requests.RequestException:
        return []
    data = response.json()
    docs = data.get("response", {}).get("docs", [])
    results: List[NormalizedBook] = []
    for doc in docs:
        identifier = doc.get("identifier")
        if not identifier:
            continue
        cover_url = f"https://archive.org/services/img/{identifier}"
        year = doc.get("year")
        try:
            year_int = int(year) if year else None
        except (ValueError, TypeError):
            year_int = None
        results.append(
            NormalizedBook(
                source="ia",
                title=doc.get("title"),
                authors=(
                    doc.get("creator").split(";") if isinstance(doc.get("creator"), str) else []
                ),
                publisher=doc.get("publisher"),
                year=year_int,
                isbn_set=set(),  # IA rarely has ISBN here
                cover_url=cover_url,
                raw=doc,
            )
        )
    return results


def fetch_google_books(record: NormalizedBook) -> List[NormalizedBook]:
    """Fetch candidate matches from the Google Books public API (no key required)."""
    queries: List[str] = []
    if record.isbn_set:
        for isbn in record.isbn_set:
            queries.append(f"isbn:{isbn}")
    if record.title and record.authors:
        queries.append(f'intitle:"{record.title}" inauthor:"{record.authors[0]}"')
    elif record.title:
        queries.append(f'intitle:"{record.title}"')
    if not queries:
        return []

    results: List[NormalizedBook] = []
    for query in queries:
        try:
            response = requests.get(
                "https://www.googleapis.com/books/v1/volumes",
                params={"q": query, "maxResults": "5"},
                timeout=8,
            )
            response.raise_for_status()
        except requests.RequestException:
            continue

        data = response.json() or {}
        items = data.get("items") or []
        for item in items:
            info = item.get("volumeInfo") or {}
            title = info.get("title")
            authors = info.get("authors") or []
            publisher = info.get("publisher")
            published = info.get("publishedDate")
            year_int: Optional[int] = None
            if isinstance(published, str):
                match = re.search(r"\d{4}", published)
                if match:
                    try:
                        year_int = int(match.group(0))
                    except ValueError:
                        year_int = None

            isbn_values: Set[str] = set()
            for identifier in info.get("industryIdentifiers") or []:
                value = identifier.get("identifier")
                if value:
                    isbn_values.update(_normalize_isbn(str(value)))

            image_links = info.get("imageLinks") or {}
            cover_url: Optional[str] = None
            for key in ("extraLarge", "large", "medium", "small", "thumbnail", "smallThumbnail"):
                candidate = image_links.get(key)
                if candidate:
                    cover_url = str(candidate).replace("http://", "https://")
                    break

            description = info.get("description")
            categories = info.get("categories") or []

            results.append(
                NormalizedBook(
                    source="google",
                    title=title,
                    authors=[str(author) for author in authors if author],
                    publisher=publisher,
                    year=year_int,
                    isbn_set=isbn_values,
                    cover_url=cover_url,
                    description=description,
                    subjects=[str(category) for category in categories if category],
                    raw=item,
                )
            )

        if results:
            break

    return results


def normalized_key(book: NormalizedBook) -> Tuple[Optional[str], Optional[str], Optional[int]]:
    title = (book.title or "").strip().lower() if book.title else None
    publisher = (book.publisher or "").strip().lower() if book.publisher else None
    year = book.year
    return title, publisher, year


def merge_books(records: List[NormalizedBook]) -> NormalizedBook:
    if not records:
        raise ValueError("merge_books requires at least one record")
    base = records[0]
    merged = NormalizedBook(
        source="merged",
        title=base.title,
        authors=list(base.authors),
        publisher=base.publisher,
        year=base.year,
        isbn_set=set(base.isbn_set),
        cover_url=base.cover_url,
        description=base.description,
        subjects=list(base.subjects),
        openlibrary_key=base.openlibrary_key,
        raw={"sources": []},
    )
    for record in records:
        merged.raw["sources"].append({"source": record.source, "raw": record.raw})
        merged.isbn_set.update(record.isbn_set)
        if not merged.title and record.title:
            merged.title = record.title
        if record.authors:
            for author in record.authors:
                if author and author not in merged.authors:
                    merged.authors.append(author)
        if not merged.publisher and record.publisher:
            merged.publisher = record.publisher
        if not merged.year and record.year:
            merged.year = record.year
        if not merged.cover_url and record.cover_url:
            merged.cover_url = record.cover_url
        if not merged.description and record.description:
            merged.description = record.description
        for subject in record.subjects:
            if subject and subject not in merged.subjects:
                merged.subjects.append(subject)
        if not merged.openlibrary_key and record.openlibrary_key:
            merged.openlibrary_key = record.openlibrary_key
    return merged


def cluster_records(records: List[NormalizedBook]) -> List[List[NormalizedBook]]:
    if not records:
        return []

    parent = list(range(len(records)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(a: int, b: int) -> None:
        root_a = find(a)
        root_b = find(b)
        if root_a == root_b:
            return
        parent[root_b] = root_a

    key_map: Dict[str, List[int]] = defaultdict(list)

    for idx, record in enumerate(records):
        if record.isbn_set:
            for isbn in record.isbn_set:
                key_map[f"isbn:{isbn}"].append(idx)
        title, publisher, year = normalized_key(record)
        if title and publisher and year:
            key_map[f"tp:{title}|{publisher}|{year}"].append(idx)
        if title and year:
            key_map[f"ty:{title}|{year}"].append(idx)
        if title:
            key_map[f"title:{title}"].append(idx)

    for indexes in key_map.values():
        if len(indexes) < 2:
            continue
        anchor = indexes[0]
        for other in indexes[1:]:
            union(anchor, other)

    groups: Dict[int, List[NormalizedBook]] = defaultdict(list)
    for idx, record in enumerate(records):
        groups[find(idx)].append(record)

    return list(groups.values())


def collect_enrichment(record: Dict[str, Any], *, base: Optional[NormalizedBook] = None) -> NormalizedBook:
    if base is None:
        base = normalize_openlibrary(record)
    loc_matches = fetch_loc_books(base)
    ia_matches = fetch_ia_books(base)
    google_matches = fetch_google_books(base)
    clusters = cluster_records([base, *loc_matches, *ia_matches, *google_matches])
    merged_clusters = [merge_books(cluster) for cluster in clusters]
    merged_clusters.sort(
        key=lambda item: (
            item.source != "openlibrary",
            -len(item.isbn_set),
            0 if item.cover_url else 1,
        )
    )
    return merged_clusters[0]


_CACHE_CAPACITY = 128
_enrichment_cache: OrderedDict[str, NormalizedBook] = OrderedDict()
_cache_lock = RLock()


def _cache_key_from_book(book: NormalizedBook) -> Optional[str]:
    if book.openlibrary_key:
        return f"ol:{book.openlibrary_key}"
    if book.isbn_set:
        return f"isbn:{sorted(book.isbn_set)[0]}"
    title, publisher, year = normalized_key(book)
    if title and publisher and year:
        return f"tp:{title}|{publisher}|{year}"
    if title and year:
        return f"ty:{title}|{year}"
    if title:
        return f"title:{title}"
    return None


def get_enriched_record(record: Dict[str, Any]) -> NormalizedBook:
    base = normalize_openlibrary(record)
    cache_key = _cache_key_from_book(base)

    if cache_key:
        with _cache_lock:
            cached = _enrichment_cache.get(cache_key)
            if cached:
                _enrichment_cache.move_to_end(cache_key)
                return cached

    enriched = collect_enrichment(record, base=base)

    if cache_key:
        with _cache_lock:
            _enrichment_cache[cache_key] = enriched
            if len(_enrichment_cache) > _CACHE_CAPACITY:
                _enrichment_cache.popitem(last=False)

    return enriched

