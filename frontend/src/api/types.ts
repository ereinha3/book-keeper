export interface SearchResponse {
  results: OpenLibraryDocument[];
  total: number;
  page: number;
  page_size: number;
}

export interface OpenLibraryDocument {
  key: string;
  title?: string;
  subtitle?: string;
  author_name?: string[];
  first_publish_year?: number;
  edition_count?: number;
  cover_i?: number;
  cover_edition_key?: string;
  isbn?: string[];
  subject?: string[];
  publisher?: string[];
  number_of_pages_median?: number;
  [key: string]: unknown;
}

export interface Book {
  id: number;
  title: string | null;
  subtitle?: string | null;
  authors?: string | null;
  first_publish_year?: number | null;
  edition_count?: number | null;
  openlibrary_key?: string | null;
  cover_url?: string | null;
  cover_path?: string | null;
  cover_asset?: string | null;
  isbn?: string | null;
  subjects?: string | null;
  publisher?: string | null;
  number_of_pages_median?: number | null;
  shelf_id?: number | null;
  shelf_name?: string | null;
  shelf_row_id?: number | null;
  row_name?: string | null;
  row_position?: number | null;
  row_capacity?: number | null;
  slot_index?: number | null;
  created_at?: string;
}

export interface Shelf {
  id: number;
  name: string;
  description?: string | null;
  row_count: number;
  capacity: number;
}

export interface ShelfRow {
  id: number;
  shelf_id: number;
  name?: string | null;
  position: number;
  capacity: number;
  used: number;
}

export interface ShelfPlacement {
  book_id: number;
  title: string | null;
  authors: string | null;
  cover_path?: string | null;
  cover_asset?: string | null;
  slot_index: number;
}

export interface ShelfBlock {
  shelf: ShelfBlockInfo;
  rows: {
    row: {
      id: number;
      name?: string | null;
      position: number;
      capacity: number;
    };
    placements: ShelfPlacement[];
  }[];
}

export interface ShelfBlockInfo {
  id: number;
  name: string;
  description?: string | null;
}

export interface ShelfStructureResponse extends Array<ShelfBlock> {}

export type InventorySearchCategory = "all" | "title" | "author" | "publisher" | "subjects" | "isbn";

export interface BookSummary {
  book: Book;
  description?: string | null;
  subjects: string[];
  openlibrary_url?: string | null;
}

export interface InventoryFilterOptions {
  subjects: string[];
  authors: string[];
  publishers: string[];
  shelves: string[];
}

