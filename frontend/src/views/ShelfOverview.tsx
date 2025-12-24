import { useState } from "react";
import {
  Box,
  CircularProgress,
  IconButton,
  Paper,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { api, buildAssetUrl } from "../api/client";
import type { Book, ShelfBlock } from "../api/types";
import BookDetailDialog from "../components/BookDetailDialog";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";

const CARD_WIDTH = 140;
const CARD_HEIGHT = 210;
const MAX_VISIBLE = 10;

export default function ShelfOverview() {
  const structureQuery = useQuery<ShelfBlock[]>({
    queryKey: ["shelf-structure"],
    queryFn: async () => {
      const response = await api.get<ShelfBlock[]>("/api/shelf-structure");
      return response.data;
    },
    staleTime: 30 * 1000,
  });
  const [detailTarget, setDetailTarget] = useState<Book | null>(null);
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set());
  const [rowOffsets, setRowOffsets] = useState<Record<number, number>>({});

  if (structureQuery.isLoading) {
    return (
      <Stack alignItems="center" py={6}>
        <CircularProgress />
      </Stack>
    );
  }

  if (structureQuery.isError) {
    return (
      <Paper variant="outlined" sx={{ p: 4, textAlign: "center" }}>
        <Typography variant="body1" color="error">
          Unable to load shelf overview. Please try again shortly.
        </Typography>
      </Paper>
    );
  }

  const data = structureQuery.data ?? [];

  if (data.length === 0) {
    return (
      <Paper variant="outlined" sx={{ p: 4, textAlign: "center" }}>
        <Typography variant="body1" color="text.secondary">
          No shelves found. Create shelves and rows to visualize your collection.
        </Typography>
      </Paper>
    );
  }

  return (
    <Stack spacing={3}>
      {data.map((block) => (
        <Paper key={block.shelf.id} sx={{ p: 3, borderRadius: 3 }}>
          <Typography variant="h6" gutterBottom>
            {block.shelf.name}
          </Typography>
          {block.shelf.description && (
            <Typography variant="body2" color="text.secondary" gutterBottom>
              {block.shelf.description}
            </Typography>
          )}
          <Stack spacing={2}>
            {block.rows.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                No rows created for this shelf yet.
              </Typography>
            ) : (
              block.rows.map((row) => {
                const placements = [...row.placements].sort((a, b) => a.slot_index - b.slot_index);
                const rowId = row.row.id;
                const isExpanded = expandedRows.has(rowId);
                const maxOffset = Math.max(0, placements.length - MAX_VISIBLE);
                const currentOffset = Math.min(rowOffsets[rowId] ?? 0, maxOffset);
                const visiblePlacements = placements.slice(currentOffset, currentOffset + MAX_VISIBLE);

                const toggleRow = () => {
                  setExpandedRows((prev) => {
                    const next = new Set(prev);
                    if (next.has(rowId)) {
                      next.delete(rowId);
                    } else {
                      next.add(rowId);
                    }
                    return next;
                  });
                };

                const adjustOffset = (delta: number) => {
                  setRowOffsets((prev) => {
                    const current = Math.min(prev[rowId] ?? 0, maxOffset);
                    const next = Math.min(Math.max(current + delta, 0), maxOffset);
                    if (next === current) {
                      return prev;
                    }
                    return { ...prev, [rowId]: next };
                  });
                };

                return (
                  <Box key={row.row.id}>
                    <Stack
                      direction="row"
                      alignItems="center"
                      justifyContent="space-between"
                      sx={{ mb: 1 }}
                    >
                      <Typography variant="subtitle2">
                        {row.row.name ? row.row.name : `Row ${row.row.position}`} ·{" "}
                        {placements.length} {placements.length === 1 ? "book" : "books"}
                      </Typography>
                      <Stack direction="row" spacing={1} alignItems="center">
                        {placements.length > MAX_VISIBLE && (
                          <Typography variant="caption" color="text.secondary">
                            Showing {Math.min(visiblePlacements.length, MAX_VISIBLE)} of{" "}
                            {placements.length}
                          </Typography>
                        )}
                        <Tooltip title={isExpanded ? "Collapse row" : "Expand row"}>
                          <IconButton size="small" onClick={toggleRow}>
                            {isExpanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                          </IconButton>
                        </Tooltip>
                      </Stack>
                    </Stack>
                    {isExpanded ? (
                      placements.length === 0 ? (
                        <Typography variant="body2" color="text.secondary" sx={{ pl: 1 }}>
                          No books placed in this row yet.
                        </Typography>
                      ) : (
                        <Stack
                          direction="row"
                          alignItems="center"
                          spacing={1}
                          sx={{
                            backgroundColor: "rgba(255,255,255,0.04)",
                            borderRadius: 2,
                            p: 1,
                          }}
                        >
                          <IconButton
                            size="small"
                            onClick={() => adjustOffset(-1)}
                            disabled={currentOffset === 0}
                          >
                            <ChevronLeftIcon fontSize="small" />
                          </IconButton>
                          <Box
                            sx={{
                              flex: 1,
                              display: "grid",
                              gap: 1,
                              gridTemplateColumns: `repeat(${Math.max(
                                visiblePlacements.length,
                                1,
                              )}, ${CARD_WIDTH}px)`,
                              justifyContent: "flex-start",
                              overflow: "hidden",
                            }}
                          >
                            {visiblePlacements.map((placement) => {
                              const assetUrl = buildAssetUrl(placement.cover_asset);
                              return (
                                <Box
                                  key={placement.slot_index}
                                  sx={{
                                    width: CARD_WIDTH,
                                    minHeight: CARD_HEIGHT,
                                    borderRadius: 3,
                                    border: "1px solid",
                                    borderColor: "primary.main",
                                    backgroundColor: "rgba(15, 23, 42, 0.6)",
                                    display: "flex",
                                    flexDirection: "column",
                                    alignItems: "center",
                                    justifyContent: "flex-start",
                                    overflow: "hidden",
                                  }}
                                >
                                  <Box
                                    onClick={() =>
                                      setDetailTarget({
                                        id: placement.book_id,
                                        title: placement.title ?? null,
                                        authors: placement.authors ?? null,
                                        cover_asset: placement.cover_asset ?? null,
                                        cover_path: placement.cover_path ?? null,
                                        shelf_row_id: row.row.id,
                                        shelf_id: block.shelf.id,
                                        shelf_name: block.shelf.name,
                                        row_name: row.row.name ?? `Row ${row.row.position}`,
                                        slot_index: placement.slot_index,
                                        subtitle: null,
                                        first_publish_year: null,
                                        edition_count: null,
                                        openlibrary_key: null,
                                        cover_url: assetUrl ?? null,
                                        isbn: null,
                                        subjects: null,
                                        publisher: null,
                                        number_of_pages_median: null,
                                      })
                                    }
                                    sx={{
                                      width: "100%",
                                      height: CARD_HEIGHT - 60,
                                      backgroundColor: "rgba(255,255,255,0.04)",
                                      cursor: "pointer",
                                      display: "flex",
                                      alignItems: "center",
                                      justifyContent: "center",
                                      overflow: "hidden",
                                      borderBottom: "1px solid rgba(255,255,255,0.06)",
                                    }}
                                  >
                                    {assetUrl ? (
                                      <Box
                                        component="img"
                                        src={assetUrl}
                                        alt={placement.title ?? "Book cover"}
                                        sx={{
                                          maxWidth: "100%",
                                          maxHeight: "100%",
                                          objectFit: "contain",
                                        }}
                                      />
                                    ) : (
                                      <Stack
                                        spacing={0.5}
                                        alignItems="center"
                                        justifyContent="center"
                                        sx={{
                                          width: "100%",
                                          height: "100%",
                                          color: "grey.500",
                                          fontSize: 12,
                                          textTransform: "uppercase",
                                          letterSpacing: 1,
                                        }}
                                      >
                                        No cover
                                      </Stack>
                                    )}
                                  </Box>
                                  <Box
                                    sx={{
                                      p: 1,
                                      width: "100%",
                                      textAlign: "center",
                                      minHeight: 60,
                                    }}
                                  >
                                    <Typography variant="caption" sx={{ fontWeight: 600 }} noWrap>
                                      {placement.title ?? "Untitled"}
                                    </Typography>
                                    <Typography variant="caption" color="text.secondary" noWrap>
                                      {placement.authors ?? "Unknown author"}
                                    </Typography>
                                  </Box>
                                </Box>
                              );
                            })}
                          </Box>
                          <IconButton
                            size="small"
                            onClick={() => adjustOffset(1)}
                            disabled={currentOffset >= maxOffset}
                          >
                            <ChevronRightIcon fontSize="small" />
                          </IconButton>
                        </Stack>
                      )
                    ) : null}
                  </Box>
                );
              })
            )}
          </Stack>
        </Paper>
      ))}
      <BookDetailDialog
        open={Boolean(detailTarget)}
        bookId={detailTarget?.id ?? null}
        onClose={() => setDetailTarget(null)}
      />
    </Stack>
  );
}

