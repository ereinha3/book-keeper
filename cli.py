import pandas
import json
from typing import Any, Dict, List, Optional

from api import (
    load_or_create_spreadsheet, 
    fetch_records, 
    build_record, 
    OpenLibraryQuery, 
    save_spreadsheet,
    DEFAULT_COLUMNS, 
    describe_result,
    PAGE_SIZE,
)


def print_doc_fields(doc: Dict[str, Any]) -> None:
    """Pretty-print all fields returned by the API for a document."""
    print(json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=True))


def print_record_preview(record: Dict[str, Any]) -> None:
    """Print the key/value pairs that will be written to the spreadsheet."""
    for key in DEFAULT_COLUMNS:
        value = record.get(key, "")
        print(f"   {key}: {value}")


def choose_result(docs: List[Dict]) -> Optional[Dict]:
    """Allow the user to browse results and select one."""
    if not docs:
        print("No books matched your search.")
        return None

    offset = 0
    while offset < len(docs):
        page = docs[offset : offset + PAGE_SIZE]
        for idx, doc in enumerate(page, start=offset + 1):
            print(describe_result(doc, idx))
        print()
        prompt = (
            "Enter the number of a book to add it, 'd <number>' for full details, "
            "'n' to view more, 's' to skip this query: "
        )
        response = input(prompt).strip()
        normalized = response.lower()

        if normalized.startswith("d"):
            detail_index: Optional[int] = None
            remainder = response[1:].strip()
            if remainder.isdigit():
                detail_index = int(remainder)
            else:
                tokens = response.split()
                if len(tokens) == 2 and tokens[1].isdigit():
                    detail_index = int(tokens[1])
            if detail_index is None:
                print("Use the format 'd <number>' to view all fields for a result.")
                continue
            if 1 <= detail_index <= len(docs):
                print("\nFull API response:\n")
                print_doc_fields(docs[detail_index - 1])
                print()
            else:
                print("That selection is out of range. Please try again.")
            continue

        if normalized in {"s", "skip"}:
            return None
        if normalized in {"n", "next"}:
            offset += PAGE_SIZE
            continue
        try:
            selection = int(response)
        except ValueError:
            print("Please enter a valid option.")
            continue
        if 1 <= selection <= len(docs):
            return docs[selection - 1]
        print("That selection is out of range. Please try again.")

    print("No more results to show.")
    return None




def interactive_session() -> None:
    """Run the interactive Open Library search session."""
    frame, path = load_or_create_spreadsheet()

    print("\nEnter search details to find books on Open Library.")
    print("Type 'quit' at any prompt to exit.")

    while True:
        general = input("\nKeywords (leave blank to skip): ").strip()
        if general.lower() == "quit":
            break

        title = input("Title keywords (leave blank to skip): ").strip()
        if title.lower() == "quit":
            break

        author = input("Author keywords (leave blank to skip): ").strip()
        if author.lower() == "quit":
            break

        year_value = input("First publish year (leave blank to skip): ").strip()
        if year_value.lower() == "quit":
            break
        if year_value and not year_value.isdigit():
            print("Please enter the year as digits only.")
            continue
        year = int(year_value) if year_value else None

        if not any([general, title, author, year]):
            print("No query parameters provided. Please try again.")
            continue

        query = OpenLibraryQuery(
            general=general or None,
            title=title or None,
            author=author or None,
            year=year,
        )
        docs = fetch_records(query)
        chosen = choose_result(docs)
        if not chosen:
            continue

        record = build_record(chosen)
        print("\nSelected book details:")
        print_record_preview(record)

        confirm = input("Add this to the spreadsheet? (y/n): ").strip().lower()
        if confirm not in {"y", "yes"}:
            print("Skipped adding this book.")
            continue

        frame = pandas.concat([frame, pandas.DataFrame([record])], ignore_index=True)
        save_spreadsheet(frame, path)
        print(f"Added '{record['title']}' to {path}")

        continue_response = input("Search for another book? (y/n): ").strip().lower()
        if continue_response not in {"y", "yes"}:
            break

    print("\nSession complete. Spreadsheet saved.")


if __name__ == "__main__":
    interactive_session()