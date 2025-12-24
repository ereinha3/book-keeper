import { useEffect, useMemo, useState } from "react";
import Autocomplete from "@mui/material/Autocomplete";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Collapse,
  Divider,
  FormControl,
  IconButton,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Snackbar,
  Stack,
  TextField,
  ToggleButton,
  Typography,
} from "@mui/material";
import DeleteOutline from "@mui/icons-material/DeleteOutline";
import InfoOutlined from "@mui/icons-material/InfoOutlined";
import PlaceOutlined from "@mui/icons-material/PlaceOutlined";
import RemoveCircleOutline from "@mui/icons-material/RemoveCircleOutline";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Book, InventoryFilterOptions, InventorySearchCategory } from "../api/types";
import { api, buildAssetUrl } from "../api/client";
import PlacementDialog from "../components/PlacementDialog";
import BookDetailDialog from "../components/BookDetailDialog";
import TuneOutlined from "@mui/icons-material/TuneOutlined";

const SEARCH_OPTIONS: { value: InventorySearchCategory; label: string }[] = [
  { value: "all", label: "All fields" },
  { value: "title", label: "Title" },
  { value: "author", label: "Author" },
  { value: "publisher", label: "Publisher" },
  { value: "subjects", label: "Subjects" },
  { value: "isbn", label: "ISBN" },
];

const EMPTY_FILTER_OPTIONS: InventoryFilterOptions = {
  subjects: [],
  authors: [],
  publishers: [],
  shelves: [],
};

function useDebouncedValue<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);

  return debounced;
}

const COLLECTION_CARD_WIDTH = 220;
const COLLECTION_COVER_HEIGHT = 300;

function CollectionCard({
  book,
  onMove,
  onRemovePlacement,
  onDelete,
  onView,
}: {
  book: Book;
  onMove: (book: Book) => void;
  onRemovePlacement?: (book: Book) => void;
  onDelete: (book: Book) => void;
  onView: (book: Book) => void;
}) {
  const coverSrc = buildAssetUrl(book.cover_asset ?? book.cover_path ?? book.cover_url ?? undefined);
  return (
    <Card
      sx={{
        width: COLLECTION_CARD_WIDTH,
        display: "flex",
        flexDirection: "column",
        borderRadius: 3,
        overflow: "hidden",
        border: "1px solid rgba(148,163,184,0.2)",
        boxShadow: "0 10px 24px rgba(15,23,42,0.25)",
      }}
    >
      <Box
        sx={{
          width: "100%",
          height: COLLECTION_COVER_HEIGHT,
          backgroundColor: "rgba(148,163,184,0.12)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          textTransform: "uppercase",
          letterSpacing: 1,
          fontSize: 12,
          color: "rgba(148,163,184,0.82)",
          overflow: "hidden",
        }}
      >
        {coverSrc ? (
          <Box
            component="img"
            src={coverSrc}
            alt={book.title ?? "Book cover"}
            sx={{
              maxWidth: "100%",
              maxHeight: "100%",
              objectFit: "contain",
            }}
          />
        ) : (
          "No cover"
        )}
      </Box>
      <CardContent sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
        <Typography variant="subtitle1" noWrap>
          {book.title ?? "Untitled"}
        </Typography>
        <Typography variant="caption" color="text.secondary" noWrap>
          {book.authors || "Unknown author"}
        </Typography>
        {book.shelf_name ? (
          <Typography variant="caption" color="text.secondary">
            {book.shelf_name}
            {book.row_name ? ` · ${book.row_name}` : ""}{" "}
            {book.slot_index ? `(slot ${book.slot_index})` : ""}
          </Typography>
        ) : (
          <Typography variant="caption" color="text.secondary">
            Not placed
          </Typography>
        )}
        <Stack direction="row" spacing={1} mt="auto">
          <Button
            variant="outlined"
            size="small"
            startIcon={<InfoOutlined fontSize="small" />}
            onClick={() => onView(book)}
          >
            Details
          </Button>
          <IconButton size="small" onClick={() => onDelete(book)}>
            <DeleteOutline fontSize="small" />
          </IconButton>
        </Stack>
        <Stack direction="row" spacing={1}>
          <Button
            fullWidth
            variant="contained"
            size="small"
            startIcon={<PlaceOutlined fontSize="small" />}
            onClick={() => onMove(book)}
          >
            {book.shelf_row_id ? "Move" : "Place"}
          </Button>
          {book.shelf_row_id && onRemovePlacement && (
            <IconButton size="small" onClick={() => onRemovePlacement(book)}>
              <RemoveCircleOutline fontSize="small" />
            </IconButton>
          )}
        </Stack>
      </CardContent>
    </Card>
  );
}

export default function InventoryView() {
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState("");
  const [category, setCategory] = useState<InventorySearchCategory>("all");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [selectedSubjects, setSelectedSubjects] = useState<string[]>([]);
  const [subjectMode, setSubjectMode] = useState<"any" | "all">("any");
  const [selectedAuthors, setSelectedAuthors] = useState<string[]>([]);
  const [selectedPublishers, setSelectedPublishers] = useState<string[]>([]);
  const [selectedShelves, setSelectedShelves] = useState<string[]>([]);
  const [placementTarget, setPlacementTarget] = useState<Book | null>(null);
  const [detailTarget, setDetailTarget] = useState<Book | null>(null);
  const [snackbar, setSnackbar] = useState<{ open: boolean; message: string; severity: "success" | "error" }>({
    open: false,
    message: "",
    severity: "success",
  });

  const debouncedTerm = useDebouncedValue(searchTerm, 350);
  const appliedFilterCount =
    (category !== "all" ? 1 : 0) +
    (selectedSubjects.length ? 1 : 0) +
    (selectedAuthors.length ? 1 : 0) +
    (selectedPublishers.length ? 1 : 0) +
    (selectedShelves.length ? 1 : 0);
  const hasAdvancedFilters = appliedFilterCount > 0;

  useEffect(() => {
    if (selectedSubjects.length === 0 && subjectMode === "all") {
      setSubjectMode("any");
    }
  }, [selectedSubjects, subjectMode]);

  const filterOptionsQuery = useQuery<InventoryFilterOptions>({
    queryKey: ["inventory-filters"],
    queryFn: async () => {
      const response = await api.get<InventoryFilterOptions>("/api/books/filters");
      return response.data;
    },
    enabled: advancedOpen || hasAdvancedFilters,
    staleTime: 5 * 60 * 1000,
  });

  const filterOptions: InventoryFilterOptions = filterOptionsQuery.data ?? EMPTY_FILTER_OPTIONS;

  const searchKey = useMemo(
    () => ({
      term: debouncedTerm.trim(),
      category,
      subjects: selectedSubjects,
      subjectMode,
      authors: selectedAuthors,
      publishers: selectedPublishers,
      shelves: selectedShelves,
    }),
    [debouncedTerm, category, selectedSubjects, subjectMode, selectedAuthors, selectedPublishers, selectedShelves],
  );

  const booksQuery = useQuery<Book[]>({
    queryKey: ["inventory-search", searchKey],
    queryFn: async () => {
      const params: Record<string, string | string[] | undefined> = {};
      if (searchKey.term) {
        params.q = searchKey.term;
      }
      if (searchKey.category && searchKey.category !== "all") {
        params.category = searchKey.category;
      }
      if (searchKey.subjects.length > 0) {
        params.subjects = searchKey.subjects;
        params.subjects_mode = searchKey.subjectMode;
      }
      if (searchKey.authors.length > 0) {
        params.authors = searchKey.authors;
      }
      if (searchKey.publishers.length > 0) {
        params.publishers = searchKey.publishers;
      }
      if (searchKey.shelves.length > 0) {
        params.shelves = searchKey.shelves;
      }
      const response = await api.get<Book[]>("/api/books/search", { params });
      return response.data;
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (bookId: number) => {
      await api.delete(`/api/books/${bookId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["inventory-search"] });
      queryClient.invalidateQueries({ queryKey: ["shelf-structure"] });
      setSnackbar({ open: true, message: "Book removed from collection.", severity: "success" });
    },
    onError: () => {
      setSnackbar({ open: true, message: "Unable to delete book.", severity: "error" });
    },
  });

  const clearPlacementMutation = useMutation({
    mutationFn: async (bookId: number) => {
      await api.delete(`/api/books/${bookId}/placement`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["inventory-search"] });
      queryClient.invalidateQueries({ queryKey: ["shelf-structure"] });
      setSnackbar({ open: true, message: "Placement cleared.", severity: "success" });
    },
    onError: () => {
      setSnackbar({ open: true, message: "Unable to clear placement.", severity: "error" });
    },
  });

  const books = booksQuery.data ?? [];
  const placedBooks = useMemo(() => books.filter((book) => book.shelf_row_id), [books]);
  const unplacedBooks = useMemo(() => books.filter((book) => !book.shelf_row_id), [books]);

  const handleDelete = (book: Book) => {
    if (window.confirm(`Delete “${book.title ?? "this book"}”?`)) {
      deleteMutation.mutate(book.id);
    }
  };

  const handleClearAdvancedFilters = () => {
    setSelectedSubjects([]);
    setSelectedAuthors([]);
    setSelectedPublishers([]);
    setSelectedShelves([]);
    setSubjectMode("any");
    setCategory("all");
  };

  const filtersButtonLabel = advancedOpen
    ? "Hide filters"
    : hasAdvancedFilters
      ? `Filters · ${appliedFilterCount}`
      : "Filters";

  return (
    <Box>
      <Stack spacing={3} mb={4}>
        <Typography variant="h6" sx={{ fontWeight: 700 }}>
          My Collection
        </Typography>
        <Paper
          elevation={0}
          sx={{
            p: { xs: 2, md: 3 },
            borderRadius: 3,
            border: "1px solid rgba(148,163,184,0.2)",
            backgroundColor: "rgba(148,163,184,0.05)",
          }}
        >
          <Stack spacing={2}>
            <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems={{ md: "center" }}>
              <TextField
                label="Search collection"
                value={searchTerm}
                onChange={(event) => setSearchTerm(event.target.value)}
                fullWidth
                size="small"
                placeholder="Search by keywords"
              />
              <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems={{ xs: "stretch", sm: "center" }}>
                <FormControl size="small" sx={{ minWidth: { xs: "100%", sm: 200 } }}>
                  <InputLabel id="inventory-search-category">Category</InputLabel>
                  <Select
                    labelId="inventory-search-category"
                    value={category}
                    label="Category"
                    onChange={(event) => setCategory(event.target.value as InventorySearchCategory)}
                  >
                    {SEARCH_OPTIONS.map((option) => (
                      <MenuItem key={option.value} value={option.value}>
                        {option.label}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
                <Button
                  variant={advancedOpen || hasAdvancedFilters ? "contained" : "outlined"}
                  color="primary"
                  startIcon={<TuneOutlined />}
                  onClick={() => setAdvancedOpen((prev) => !prev)}
                  sx={{ width: { xs: "100%", sm: "auto" } }}
                >
                  {filtersButtonLabel}
                </Button>
              </Stack>
            </Stack>
            <Collapse in={advancedOpen} timeout="auto" unmountOnExit>
              <Box>
                <Divider sx={{ my: 2, borderColor: "rgba(148,163,184,0.18)" }} />
                {filterOptionsQuery.isError ? (
                  <Alert severity="error">Unable to load filter options. Please try again.</Alert>
                ) : filterOptionsQuery.isLoading && !filterOptionsQuery.data ? (
                  <Stack alignItems="center" py={3}>
                    <CircularProgress size={24} />
                  </Stack>
                ) : (
                  <Stack spacing={2}>
                    <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                      <Autocomplete
                        multiple
                        size="small"
                        options={filterOptions.subjects}
                        value={selectedSubjects}
                        onChange={(_event, value) => setSelectedSubjects(value)}
                        filterSelectedOptions
                        renderInput={(params) => (
                          <TextField {...params} label="Subjects" placeholder="Choose subjects" />
                        )}
                        renderTags={(value, getTagProps) =>
                          value.map((option, index) => (
                            <Chip {...getTagProps({ index })} size="small" label={option} key={option} />
                          ))
                        }
                        sx={{ flex: 1 }}
                      />
                      <ToggleButton
                        value="match-all"
                        selected={subjectMode === "all"}
                        onChange={() => setSubjectMode((prev) => (prev === "all" ? "any" : "all"))}
                        disabled={selectedSubjects.length === 0}
                        sx={{
                          borderRadius: 999,
                          px: 3,
                          textTransform: "none",
                          height: 40,
                          alignSelf: { xs: "stretch", md: "center" },
                          border: "1px solid rgba(148,163,184,0.35)",
                          color: "rgba(226,232,240,0.82)",
                          "&:hover": {
                            borderColor: "rgba(56,189,248,0.45)",
                            backgroundColor: "rgba(56,189,248,0.08)",
                          },
                          "&.Mui-selected": {
                            backgroundColor: "rgba(56,189,248,0.22)",
                            borderColor: "rgba(56,189,248,0.45)",
                            color: "rgba(14,165,233,0.95)",
                          },
                          "&.Mui-selected:hover": {
                            backgroundColor: "rgba(56,189,248,0.3)",
                          },
                        }}
                      >
                        Match all subjects
                      </ToggleButton>
                    </Stack>
                    <Autocomplete
                      multiple
                      size="small"
                      options={filterOptions.authors}
                      value={selectedAuthors}
                      onChange={(_event, value) => setSelectedAuthors(value)}
                      filterSelectedOptions
                      renderInput={(params) => <TextField {...params} label="Authors" placeholder="Select authors" />}
                      renderTags={(value, getTagProps) =>
                        value.map((option, index) => (
                          <Chip {...getTagProps({ index })} size="small" label={option} key={option} />
                        ))
                      }
                    />
                    <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                      <Autocomplete
                        multiple
                        size="small"
                        options={filterOptions.publishers}
                        value={selectedPublishers}
                        onChange={(_event, value) => setSelectedPublishers(value)}
                        filterSelectedOptions
                        renderInput={(params) => (
                          <TextField {...params} label="Publishers" placeholder="Select publishers" />
                        )}
                        renderTags={(value, getTagProps) =>
                          value.map((option, index) => (
                            <Chip {...getTagProps({ index })} size="small" label={option} key={option} />
                          ))
                        }
                        sx={{ flex: 1 }}
                      />
                      <Autocomplete
                        multiple
                        size="small"
                        options={filterOptions.shelves}
                        value={selectedShelves}
                        onChange={(_event, value) => setSelectedShelves(value)}
                        filterSelectedOptions
                        renderInput={(params) => <TextField {...params} label="Shelves" placeholder="Select shelves" />}
                        renderTags={(value, getTagProps) =>
                          value.map((option, index) => (
                            <Chip {...getTagProps({ index })} size="small" label={option} key={option} />
                          ))
                        }
                        sx={{ flex: 1 }}
                      />
                    </Stack>
                    <Stack direction={{ xs: "column", sm: "row" }} spacing={1} justifyContent="flex-end">
                      <Button
                        onClick={handleClearAdvancedFilters}
                        disabled={!hasAdvancedFilters}
                        variant="text"
                        sx={{ alignSelf: { xs: "stretch", sm: "center" } }}
                      >
                        Clear filters
                      </Button>
                    </Stack>
                  </Stack>
                )}
              </Box>
            </Collapse>
          </Stack>
        </Paper>
      </Stack>

      {booksQuery.isLoading ? (
        <Stack alignItems="center" py={6}>
          <CircularProgress />
        </Stack>
      ) : books.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          {debouncedTerm
            ? "No books match your search."
            : "Your collection is empty. Add books from the search tab to get started."}
        </Typography>
      ) : (
        <Stack spacing={6}>
          <Box>
            <Typography variant="subtitle1" gutterBottom sx={{ fontWeight: 600 }}>
              Unplaced Books ({unplacedBooks.length})
            </Typography>
            {unplacedBooks.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                All books are currently placed on shelves.
              </Typography>
            ) : (
              <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
                {unplacedBooks.map((book) => (
                  <CollectionCard
                    key={book.id}
                    book={book}
                    onMove={setPlacementTarget}
                    onDelete={handleDelete}
                    onView={setDetailTarget}
                  />
                ))}
              </Stack>
            )}
          </Box>

          <Box>
            <Typography variant="subtitle1" gutterBottom sx={{ fontWeight: 600 }}>
              Placed Books ({placedBooks.length})
            </Typography>
            {placedBooks.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                No books are currently placed on shelves.
              </Typography>
            ) : (
              <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
                {placedBooks.map((book) => (
                  <CollectionCard
                    key={book.id}
                    book={book}
                    onMove={setPlacementTarget}
                    onDelete={handleDelete}
                    onView={setDetailTarget}
                    onRemovePlacement={(b) => clearPlacementMutation.mutate(b.id)}
                  />
                ))}
              </Stack>
            )}
          </Box>
        </Stack>
      )}

      <PlacementDialog
        open={Boolean(placementTarget)}
        book={placementTarget}
        onClose={() => setPlacementTarget(null)}
        onPlaced={() => {
          queryClient.invalidateQueries({ queryKey: ["inventory-search"] });
          queryClient.invalidateQueries({ queryKey: ["shelf-structure"] });
          setPlacementTarget(null);
        }}
      />

      <BookDetailDialog
        open={Boolean(detailTarget)}
        bookId={detailTarget?.id ?? null}
        onClose={() => setDetailTarget(null)}
      />

      <Snackbar
        open={snackbar.open}
        autoHideDuration={4000}
        onClose={() => setSnackbar((prev) => ({ ...prev, open: false }))}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert
          severity={snackbar.severity}
          onClose={() => setSnackbar((prev) => ({ ...prev, open: false }))}
          variant="filled"
          sx={{ minWidth: 260 }}
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Box>
  );
}

