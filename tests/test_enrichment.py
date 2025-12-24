from __future__ import annotations

import unittest

from enrichment import NormalizedBook, cluster_records, merge_books


class EnrichmentMergeTests(unittest.TestCase):
    def test_merge_prefers_available_cover_and_combines_fields(self) -> None:
        base = NormalizedBook(
            source="openlibrary",
            title="Test Book",
            authors=["Author A"],
            publisher="Sample Publisher",
            year=1999,
            isbn_set={"1234567890"},
            cover_url=None,
            description=None,
            subjects=["fiction"],
            openlibrary_key="/works/OL123",
            raw={"source": "base"},
        )
        loc = NormalizedBook(
            source="loc",
            title="Test Book",
            authors=["Author A"],
            publisher="Sample Publisher",
            year=1999,
            isbn_set={"1234567890"},
            cover_url="https://loc.example/cover.jpg",
            description="LoC description",
            subjects=["library science"],
            openlibrary_key=None,
            raw={"source": "loc"},
        )
        ia = NormalizedBook(
            source="ia",
            title="Test Book",
            authors=["Author A"],
            publisher="Sample Publisher",
            year=1999,
            isbn_set=set(),
            cover_url="https://archive.example/cover.jpg",
            description=None,
            subjects=[],
            openlibrary_key=None,
            raw={"source": "ia"},
        )

        merged = merge_books([base, loc, ia])

        self.assertEqual(merged.cover_url, "https://loc.example/cover.jpg")
        self.assertEqual(merged.description, "LoC description")
        self.assertEqual(merged.openlibrary_key, "/works/OL123")
        self.assertCountEqual(merged.subjects, ["fiction", "library science"])
        self.assertIn("1234567890", merged.isbn_set)
        self.assertEqual(len(merged.raw["sources"]), 3)

    def test_merge_uses_google_cover_when_available(self) -> None:
        base = NormalizedBook(
            source="openlibrary",
            title="Another Book",
            authors=["Author B"],
            publisher=None,
            year=None,
            isbn_set=set(),
            cover_url=None,
            description=None,
            subjects=[],
            openlibrary_key=None,
            raw={},
        )
        google = NormalizedBook(
            source="google",
            title="Another Book",
            authors=["Author B"],
            publisher="Publisher",
            year=2005,
            isbn_set={"9781234567897"},
            cover_url="https://books.example/cover.jpg",
            description="Google description",
            subjects=["non-fiction"],
            openlibrary_key=None,
            raw={},
        )

        merged = merge_books([base, google])

        self.assertEqual(merged.cover_url, "https://books.example/cover.jpg")
        self.assertEqual(merged.description, "Google description")
        self.assertEqual(merged.year, 2005)
        self.assertIn("9781234567897", merged.isbn_set)
        self.assertIn("non-fiction", merged.subjects)

    def test_cluster_groups_by_isbn_then_tuple(self) -> None:
        base = NormalizedBook(
            source="openlibrary",
            title="Shared Title",
            authors=["Author A"],
            publisher="Pub",
            year=2001,
            isbn_set={"ABC"},
            cover_url=None,
            description=None,
            subjects=[],
            openlibrary_key="/works/OL1",
            raw={},
        )
        same_isbn = NormalizedBook(
            source="loc",
            title="Shared Title",
            authors=["Author A"],
            publisher="Pub",
            year=2001,
            isbn_set={"ABC"},
            cover_url=None,
            description=None,
            subjects=[],
            openlibrary_key=None,
            raw={},
        )
        tuple_match = NormalizedBook(
            source="ia",
            title="Shared Title",
            authors=["Author A"],
            publisher="Pub",
            year=2001,
            isbn_set=set(),
            cover_url=None,
            description=None,
            subjects=[],
            openlibrary_key=None,
            raw={},
        )
        other = NormalizedBook(
            source="loc",
            title="Other Title",
            authors=["Author A"],
            publisher="Different Pub",
            year=2001,
            isbn_set=set(),
            cover_url=None,
            description=None,
            subjects=[],
            openlibrary_key=None,
            raw={},
        )

        clusters = cluster_records([base, same_isbn, tuple_match, other])

        # Expect first cluster with base, same_isbn, tuple_match
        cluster_sizes = sorted(len(group) for group in clusters)
        self.assertEqual(cluster_sizes, [1, 3])
        combined_cluster = next(group for group in clusters if len(group) == 3)
        self.assertEqual({record.source for record in combined_cluster}, {"openlibrary", "loc", "ia"})


if __name__ == "__main__":
    unittest.main()


