import {
  Box,
  Chip,
  Dialog,
  DialogContent,
  DialogTitle,
  IconButton,
  Link,
  Stack,
  Typography,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import { useQuery } from "@tanstack/react-query";
import { api, buildAssetUrl } from "../api/client";
import type { BookSummary } from "../api/types";

interface BookDetailDialogProps {
  bookId: number | null;
  open: boolean;
  onClose: () => void;
}

export function BookDetailDialog({ bookId, open, onClose }: BookDetailDialogProps) {
  const summaryQuery = useQuery<BookSummary>({
    queryKey: ["book-summary", bookId],
    queryFn: async () => {
      const response = await api.get<BookSummary>(`/api/books/${bookId}/summary`);
      return response.data;
    },
    enabled: open && Boolean(bookId),
  });

  const summary = summaryQuery.data;
  const book = summary?.book;
  const coverSrc = buildAssetUrl(book?.cover_asset ?? book?.cover_path ?? book?.cover_url ?? undefined);

  return (
    <Dialog
      open={open}
      onClose={onClose}
      scroll="paper"
      fullWidth
      maxWidth="sm"
      aria-labelledby="book-detail-title"
    >
      <DialogTitle
        id="book-detail-title"
        sx={{ pr: 6, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 2 }}
      >
        <Typography variant="h6" component="span" sx={{ fontWeight: 600 }}>
          {book?.title ?? "Book Details"}
        </Typography>
        <IconButton edge="end" onClick={onClose}>
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers>
        {summaryQuery.isLoading && (
          <Typography variant="body2" color="text.secondary">
            Loading…
          </Typography>
        )}
        {summaryQuery.isError && (
          <Typography variant="body2" color="error">
            Unable to load book details.
          </Typography>
        )}
        {book && (
          <Stack spacing={2}>
            <Box
              sx={{
                width: "100%",
                borderRadius: 2,
                overflow: "hidden",
                border: "1px solid rgba(148,163,184,0.2)",
                backgroundColor: "rgba(148,163,184,0.1)",
              }}
            >
              <Box
                sx={{
                  position: "relative",
                  pt: "150%",
                  backgroundImage: coverSrc ? `url(${coverSrc})` : "none",
                  backgroundSize: "cover",
                  backgroundPosition: "center",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: "rgba(148,163,184,0.8)",
                  textTransform: "uppercase",
                  letterSpacing: 2,
                  fontSize: 13,
                }}
              >
                {!coverSrc && "No cover available"}
              </Box>
            </Box>

            <Stack spacing={0.5}>
              <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                {book.title}
              </Typography>
              {book.subtitle && (
                <Typography variant="body2" color="text.secondary">
                  {book.subtitle}
                </Typography>
              )}
              <Typography variant="body2">
                <strong>Author(s):</strong> {book.authors || "Unknown"}
              </Typography>
              <Typography variant="body2">
                <strong>First published:</strong>{" "}
                {book.first_publish_year ?? "N/A"}
              </Typography>
              {book.publisher && (
                <Typography variant="body2">
                  <strong>Publisher:</strong> {book.publisher}
                </Typography>
              )}
              {book.isbn && (
                <Typography variant="body2">
                  <strong>ISBN:</strong> {book.isbn}
                </Typography>
              )}
              {book.number_of_pages_median && (
                <Typography variant="body2">
                  <strong>Pages:</strong> {book.number_of_pages_median}
                </Typography>
              )}
              {book.shelf_name && (
                <Typography variant="body2">
                  <strong>Location:</strong> {book.shelf_name}
                  {book.row_name ? ` · ${book.row_name}` : ""}{" "}
                  {book.slot_index ? `(slot ${book.slot_index})` : ""}
                </Typography>
              )}
            </Stack>

            {summary?.description && (
              <Stack spacing={0.5}>
                <Typography variant="subtitle2">Description</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: "pre-wrap" }}>
                  {summary.description}
                </Typography>
              </Stack>
            )}

            {summary?.subjects?.length ? (
              <Stack spacing={1}>
                <Typography variant="subtitle2">Subjects</Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  {summary.subjects.slice(0, 12).map((subject) => (
                    <Chip key={subject} label={subject} size="small" />
                  ))}
                </Stack>
              </Stack>
            ) : null}

            {summary?.openlibrary_url && (
              <Typography variant="body2">
                <Link href={summary.openlibrary_url} target="_blank" rel="noopener">
                  View on Open Library
                </Link>
              </Typography>
            )}
          </Stack>
        )}
      </DialogContent>
    </Dialog>
  );
}

export default BookDetailDialog;


