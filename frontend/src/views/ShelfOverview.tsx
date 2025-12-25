import { useEffect, useMemo, useState } from "react";
import {
  Box,
  CircularProgress,
  IconButton,
  Paper,
  Stack,
  Tooltip,
  Typography,
  Snackbar,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, buildAssetUrl } from "../api/client";
import type { Book, ShelfBlock, ShelfPlacement } from "../api/types";
import BookDetailDialog from "../components/BookDetailDialog";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import type { DragEndEvent } from "@dnd-kit/core";
import { DndContext, KeyboardSensor, PointerSensor, closestCenter, useSensor, useSensors } from "@dnd-kit/core";
import { SortableContext, arrayMove, rectSwappingStrategy, useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

const CARD_WIDTH = 140;
const CARD_HEIGHT = 210;

export default function ShelfOverview() {
  const queryClient = useQueryClient();
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
  const [rowPlacementsMap, setRowPlacementsMap] = useState<Record<number, ShelfPlacement[]>>({});
  const [snackbar, setSnackbar] = useState<{ open: boolean; message: string }>({
    open: false,
    message: "",
  });
  const [pendingRowId, setPendingRowId] = useState<number | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 6 },
    }),
    useSensor(KeyboardSensor),
  );

  const reorderMutation = useMutation({
    mutationFn: async ({ rowId, order }: { rowId: number; order: number[] }) => {
      await api.put(`/api/rows/${rowId}/order`, { book_ids: order });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["shelf-structure"] });
      queryClient.invalidateQueries({ queryKey: ["inventory-search"] });
    },
    onError: () => {
      setSnackbar({ open: true, message: "Unable to reorder books. Refreshed layout." });
      queryClient.invalidateQueries({ queryKey: ["shelf-structure"] });
    },
    onSettled: () => {
      setPendingRowId(null);
    },
  });

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

  const data = useMemo(() => structureQuery.data ?? [], [structureQuery.data]);

  useEffect(() => {
    if (!data || data.length === 0) {
      setRowPlacementsMap({});
      return;
    }

    const snapshot: Record<number, ShelfPlacement[]> = {};
    for (const block of data) {
      for (const row of block.rows) {
        snapshot[row.row.id] = [...row.placements].sort((a, b) => a.slot_index - b.slot_index);
      }
    }

    setRowPlacementsMap(snapshot);
  }, [data]);

  if (data.length === 0) {
    return null;
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
                const rowPlacements = rowPlacementsMap[rowId] ?? placements;
                const isRowPending = pendingRowId === rowId && reorderMutation.isPending;

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

                const handleRowDragEnd = (event: DragEndEvent) => {
                  const { active, over } = event;
                  if (!over || active.id === over.id) {
                    return;
                  }
                  const oldIndex = rowPlacements.findIndex((item) => item.book_id === active.id);
                  const newIndex = rowPlacements.findIndex((item) => item.book_id === over.id);
                  if (oldIndex === -1 || newIndex === -1) {
                    return;
                  }

                  const updatedRow = arrayMove(rowPlacements, oldIndex, newIndex).map((item, index) => ({
                    ...item,
                    slot_index: index + 1,
                  }));

                  setRowPlacementsMap((prev) => ({
                    ...prev,
                    [rowId]: updatedRow,
                  }));

                  setPendingRowId(rowId);
                  reorderMutation.mutate(
                    {
                      rowId,
                      order: updatedRow.map((item) => item.book_id),
                    },
                    {
                      onError: () => {
                        setSnackbar({ open: true, message: "Unable to reorder books. Refreshed layout." });
                        queryClient.invalidateQueries({ queryKey: ["shelf-structure"] });
                      },
                      onSuccess: () => {
                        queryClient.invalidateQueries({ queryKey: ["shelf-structure"] });
                      },
                      onSettled: () => {
                        setPendingRowId(null);
                      },
                    },
                  );
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
                      <Tooltip title={isExpanded ? "Collapse row" : "Expand row"}>
                        <IconButton size="small" onClick={toggleRow}>
                          {isExpanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                        </IconButton>
                      </Tooltip>
                    </Stack>
                    {isExpanded ? (
                      placements.length === 0 ? (
                        <Typography variant="body2" color="text.secondary" sx={{ pl: 1 }}>
                          No books placed in this row yet.
                        </Typography>
                      ) : (
                        <Box sx={{ position: "relative" }}>
                          {isRowPending && (
                            <Box
                              sx={{
                                position: "absolute",
                                inset: 0,
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                zIndex: 2,
                                backgroundColor: "rgba(15,23,42,0.45)",
                                borderRadius: 2,
                              }}
                            >
                              <CircularProgress size={24} />
                            </Box>
                          )}
                          <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleRowDragEnd}>
                            <SortableContext
                              items={rowPlacements.map((item) => item.book_id)}
                              strategy={rectSwappingStrategy}
                            >
                              <Box
                                sx={{
                                  display: "flex",
                                  gap: 1,
                                  overflowX: "auto",
                                  p: 1,
                                  backgroundColor: "rgba(255,255,255,0.04)",
                                  borderRadius: 2,
                                  opacity: isRowPending ? 0.6 : 1,
                                  pointerEvents: isRowPending ? "none" : "auto",
                                  transition: "opacity 0.2s ease",
                                }}
                              >
                                {rowPlacements.map((placement) => (
                                  <SortablePlacementCard
                                    key={placement.book_id}
                                    placement={placement}
                                    onSelect={() =>
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
                                        cover_url: buildAssetUrl(placement.cover_asset) ?? null,
                                        isbn: null,
                                        subjects: null,
                                        publisher: null,
                                        number_of_pages_median: null,
                                      })
                                    }
                                  />
                                ))}
                              </Box>
                            </SortableContext>
                          </DndContext>
                        </Box>
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
      <Snackbar
        open={snackbar.open}
        autoHideDuration={4000}
        onClose={() => setSnackbar((prev) => ({ ...prev, open: false }))}
        message={snackbar.message}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      />
    </Stack>
  );
}

function SortablePlacementCard({
  placement,
  onSelect,
}: {
  placement: ShelfPlacement;
  onSelect: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: placement.book_id,
  });
  const style = useMemo(
    () => ({
      transform: CSS.Transform.toString(transform),
      transition,
      opacity: isDragging ? 0.6 : 1,
      cursor: "grab",
    }),
    [isDragging, transform, transition],
  );
  const assetUrl = buildAssetUrl(placement.cover_asset);

  return (
    <Box ref={setNodeRef} style={style} {...attributes} {...listeners}>
      <Box
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
          onClick={onSelect}
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
    </Box>
  );
}


