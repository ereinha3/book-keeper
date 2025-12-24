import { useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardActions,
  CardContent,
  CardMedia,
  Chip,
  CircularProgress,
  Snackbar,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import AddCircleOutline from "@mui/icons-material/AddCircleOutline";
import RestartAltOutlined from "@mui/icons-material/RestartAltOutlined";
import SearchOutlined from "@mui/icons-material/SearchOutlined";
import { api } from "../api/client";
import type { Book, OpenLibraryDocument, SearchResponse } from "../api/types";
import PlacementDialog from "../components/PlacementDialog";

interface SearchParams {
  q?: string;
  title?: string;
  author?: string;
  year?: number;
  page: number;
  pageSize: number;
}

const DEFAULT_FORM: SearchParams = {
  q: "",
  title: "",
  author: "",
  year: undefined,
  page: 1,
  pageSize: 10,
};

const coverUrlForDoc = (doc: OpenLibraryDocument): string | undefined => {
  if (doc.cover_i) {
    return `https://covers.openlibrary.org/b/id/${doc.cover_i}-M.jpg`;
  }
  if (doc.cover_edition_key) {
    return `https://covers.openlibrary.org/b/olid/${doc.cover_edition_key}-M.jpg`;
  }
  return undefined;
};

export default function SearchView() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<SearchParams>({ ...DEFAULT_FORM });
  const [activeParams, setActiveParams] = useState<SearchParams | null>(null);
  const [snackbar, setSnackbar] = useState<{ open: boolean; message: string; severity: "success" | "error" }>({
    open: false,
    message: "",
    severity: "success",
  });
  const [pendingPlacement, setPendingPlacement] = useState<Book | null>(null);

  const searchQuery = useQuery<SearchResponse>({
    queryKey: ["search", activeParams],
    queryFn: async () => {
      if (!activeParams) {
        return { results: [], total: 0, page: 1, page_size: form.pageSize };
      }
      const response = await api.get<SearchResponse>("/api/search", {
        params: {
          q: activeParams.q || undefined,
          title: activeParams.title || undefined,
          author: activeParams.author || undefined,
          year: activeParams.year || undefined,
          page: activeParams.page,
          page_size: activeParams.pageSize,
        },
      });
      return response.data;
    },
    enabled: !!activeParams,
    placeholderData: keepPreviousData,
  });

  const addBookMutation = useMutation({
    mutationFn: async (doc: OpenLibraryDocument) => {
      const response = await api.post<Book>("/api/books", { document: doc });
      return response.data;
    },
    onSuccess: (book) => {
      setPendingPlacement(book);
      queryClient.invalidateQueries({ queryKey: ["books"] });
      queryClient.invalidateQueries({ queryKey: ["inventory-search"] });
      queryClient.invalidateQueries({ queryKey: ["unplaced-books"] });
      setSnackbar({ open: true, message: "Book added. Choose a shelf placement.", severity: "success" });
    },
    onError: (error: any) => {
      const message = error?.response?.data?.detail ?? "Failed to add book.";
      setSnackbar({ open: true, message, severity: "error" });
    },
  });

  const handleSearch = (override?: Partial<SearchParams>) => {
    const params: SearchParams = {
      ...form,
      ...override,
      year: form.year ? Number(form.year) : undefined,
    };
    setActiveParams(params);
  };

  const handleReset = () => {
    setForm({ ...DEFAULT_FORM });
    setActiveParams(null);
  };

  const searchData = searchQuery.data ?? { results: [], total: 0, page: 1, page_size: form.pageSize };

  const totalPages = useMemo(() => {
    return Math.max(1, Math.ceil((searchData.total || 0) / (searchData.page_size || form.pageSize)));
  }, [searchData.total, searchData.page_size, form.pageSize]);

  return (
    <Box>
      <Stack direction="row" spacing={2} alignItems="flex-end" flexWrap="wrap" useFlexGap mb={3}>
        <TextField
          label="Keywords"
          value={form.q ?? ""}
          onChange={(event) => setForm((prev) => ({ ...prev, q: event.target.value }))}
          size="small"
          sx={{ minWidth: 200 }}
        />
        <TextField
          label="Title"
          value={form.title ?? ""}
          onChange={(event) => setForm((prev) => ({ ...prev, title: event.target.value }))}
          size="small"
          sx={{ minWidth: 200 }}
        />
        <TextField
          label="Author"
          value={form.author ?? ""}
          onChange={(event) => setForm((prev) => ({ ...prev, author: event.target.value }))}
          size="small"
          sx={{ minWidth: 200 }}
        />
        <TextField
          label="Year"
          type="number"
          value={form.year ?? ""}
          onChange={(event) =>
            setForm((prev) => ({
              ...prev,
              year: event.target.value ? Number(event.target.value) : undefined,
            }))
          }
          size="small"
          sx={{ width: 120 }}
        />
        <TextField
          label="Results per page"
          type="number"
          size="small"
          value={form.pageSize}
          onChange={(event) => setForm((prev) => ({ ...prev, pageSize: Math.max(1, Number(event.target.value) || 1) }))}
          sx={{ width: 160 }}
        />

        <Stack direction="row" spacing={1} sx={{ mt: { xs: 2, sm: 0 } }}>
          <Button
            variant="contained"
            startIcon={<SearchOutlined />}
            onClick={() => handleSearch({ page: 1 })}
            disabled={addBookMutation.isPending}
          >
            Search
          </Button>
          <Button variant="outlined" startIcon={<RestartAltOutlined />} onClick={handleReset}>
            Reset
          </Button>
        </Stack>
      </Stack>

      {searchQuery.isLoading && (
        <Stack alignItems="center" py={6}>
          <CircularProgress />
        </Stack>
      )}

      {activeParams && (
        <Stack spacing={2}>
          <Stack direction="row" justifyContent="space-between" alignItems="center">
            <Typography variant="h6">
              {searchData.total.toLocaleString()} result
              {searchData.total === 1 ? "" : "s"} found
            </Typography>
            <Stack direction="row" spacing={1} alignItems="center">
              <Button
                variant="text"
                disabled={searchQuery.isFetching || (activeParams?.page ?? 1) <= 1}
                onClick={() => handleSearch({ page: (activeParams?.page ?? 1) - 1 })}
              >
                Previous
              </Button>
              <Typography variant="body2">
                Page {searchData.page} of {totalPages}
              </Typography>
              <Button
                variant="text"
                disabled={searchQuery.isFetching || searchData.page >= totalPages}
                onClick={() => handleSearch({ page: (activeParams?.page ?? 1) + 1 })}
              >
                Next
              </Button>
            </Stack>
          </Stack>

          <Box
            sx={{
              display: "grid",
              gap: 2,
              gridTemplateColumns: {
                xs: "repeat(1, minmax(0, 1fr))",
                sm: "repeat(2, minmax(0, 1fr))",
                md: "repeat(3, minmax(0, 1fr))",
                lg: "repeat(4, minmax(0, 1fr))",
              },
            }}
          >
            {searchData.results.map((doc: OpenLibraryDocument, index) => {
              const coverUrl = coverUrlForDoc(doc);
              const authors = doc.author_name?.join(", ") ?? "Unknown author";
              const resultKey = doc.key ?? `${doc.title ?? "result"}-${index}`;
              return (
                <Box key={resultKey}>
                  <Card
                    sx={{
                      height: "100%",
                      display: "flex",
                      flexDirection: "column",
                      bgcolor: "background.paper",
                      borderRadius: 3,
                    }}
                  >
                    {coverUrl ? (
                      <CardMedia
                        component="img"
                        loading="lazy"
                        image={coverUrl}
                        alt={doc.title ?? "Book cover"}
                        sx={{ height: 220, objectFit: "cover" }}
                      />
                    ) : (
                      <Box
                        sx={{
                          height: 220,
                          bgcolor: "grey.900",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          color: "grey.500",
                        }}
                      >
                        <Typography variant="body2">No cover available</Typography>
                      </Box>
                    )}

                    <CardContent sx={{ flexGrow: 1 }}>
                      <Typography variant="h6" gutterBottom noWrap>
                        {doc.title ?? "Untitled"}
                      </Typography>
                      <Typography variant="body2" color="text.secondary" gutterBottom noWrap>
                        {authors}
                      </Typography>
                      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                        {doc.first_publish_year && (
                          <Chip label={`First published ${doc.first_publish_year}`} size="small" />
                        )}
                        {doc.edition_count && (
                          <Chip
                            label={`${doc.edition_count} edition${doc.edition_count > 1 ? "s" : ""}`}
                            size="small"
                          />
                        )}
                        {doc.number_of_pages_median && (
                          <Chip label={`${doc.number_of_pages_median} pages`} size="small" />
                        )}
                        {doc.subject?.slice(0, 2).map((subject) => (
                          <Chip key={subject} label={subject} size="small" variant="outlined" />
                        ))}
                      </Stack>
                    </CardContent>
                    <CardActions sx={{ px: 2, pt: 0, pb: 2, justifyContent: "space-between" }}>
                      <Typography variant="caption" color="text.secondary" noWrap>
                        {doc.publisher?.[0] ?? "Unknown publisher"}
                      </Typography>
                      <Button
                        size="small"
                        variant="contained"
                        startIcon={<AddCircleOutline />}
                        disabled={addBookMutation.isPending}
                        onClick={() => addBookMutation.mutate(doc)}
                      >
                        Add
                      </Button>
                    </CardActions>
                  </Card>
                </Box>
              );
            })}
          </Box>
        </Stack>
      )}

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
          sx={{ minWidth: 280 }}
        >
          {snackbar.message}
        </Alert>
      </Snackbar>

      <PlacementDialog
        open={Boolean(pendingPlacement)}
        book={pendingPlacement}
        onClose={() => setPendingPlacement(null)}
        onPlaced={() => {
          queryClient.invalidateQueries({ queryKey: ["shelf-structure"] });
          queryClient.invalidateQueries({ queryKey: ["unplaced-books"] });
          setPendingPlacement(null);
        }}
      />
    </Box>
  );
}
