import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { WheelEvent } from "react";
import {
  Box,
  Button,
  CircularProgress,
  IconButton,
  Paper,
  Stack,
  Tooltip,
  Typography,
  Snackbar,
  TextField,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, buildAssetUrl } from "../api/client";
import type { Book, Shelf, ShelfBlock, ShelfPlacement } from "../api/types";
import BookDetailDialog from "../components/BookDetailDialog";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import type { DragEndEvent } from "@dnd-kit/core";
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { SortableContext, arrayMove, rectSwappingStrategy, useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

const CARD_WIDTH = 140;
const CARD_HEIGHT = 210;
const CARD_GAP = 12;
const SLOT_WIDTH = CARD_WIDTH + CARD_GAP;
const MIN_VISIBLE_SLOTS = 4;
const MAX_VIEWPORT_SLOTS = 6;

type RowPlacementMap = Record<number, ShelfPlacement[]>;

interface DragMeta {
  sourceType: "row" | "unplaced";
  rowId?: number;
  bookId: number;
  book?: Book;
}

interface DropMeta {
  targetType: "row" | "row-item" | "row-slot";
  rowId: number;
  bookId?: number;
  slotIndex?: number;
}

type AssignPlacementVariables = {
  bookId: number;
  rowId: number;
  slotIndex: number;
  sourceRowId?: number;
};

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
  const unplacedQuery = useQuery<Book[]>({
    queryKey: ["unplaced-books"],
    queryFn: async () => {
      const response = await api.get<Book[]>("/api/unplaced-books");
      return response.data;
    },
    staleTime: 30 * 1000,
  });

  const [detailTarget, setDetailTarget] = useState<Book | null>(null);
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set());
  const [rowPlacementsMap, setRowPlacementsMap] = useState<RowPlacementMap>({});
  const [snackbar, setSnackbar] = useState<{ open: boolean; message: string }>({
    open: false,
    message: "",
  });
  const [pendingRows, setPendingRows] = useState<Set<number>>(new Set());
  const [showAddShelf, setShowAddShelf] = useState(false);
  const [newShelfName, setNewShelfName] = useState("");
  const [newShelfDescription, setNewShelfDescription] = useState("");

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 6 },
    }),
    useSensor(KeyboardSensor),
  );

  const markRowsPending = (...rowIds: Array<number | undefined>) => {
    const ids = rowIds.filter((id): id is number => typeof id === "number");
    if (ids.length === 0) {
      return;
    }
    setPendingRows((prev) => {
      const next = new Set(prev);
      ids.forEach((id) => next.add(id));
      return next;
    });
  };

  const clearRowsPending = (...rowIds: Array<number | undefined>) => {
    const ids = rowIds.filter((id): id is number => typeof id === "number");
    if (ids.length === 0) {
      return;
    }
    setPendingRows((prev) => {
      if (prev.size === 0) {
        return prev;
      }
      const next = new Set(prev);
      ids.forEach((id) => next.delete(id));
      return next;
    });
  };

  const reorderMutation = useMutation({
    mutationFn: async ({ rowId, order }: { rowId: number; order: number[] }) => {
      await api.put(`/api/rows/${rowId}/order`, { book_ids: order });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["shelf-structure"] });
      queryClient.invalidateQueries({ queryKey: ["inventory-search"] });
    },
    onError: () => {
      queryClient.invalidateQueries({ queryKey: ["shelf-structure"] });
    },
  });

  const assignPlacementMutation = useMutation<void, unknown, AssignPlacementVariables>({
    mutationFn: async ({ bookId, rowId, slotIndex }) => {
      await api.post(`/api/books/${bookId}/placement`, {
        shelf_row_id: rowId,
        slot_index: slotIndex,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["shelf-structure"] });
      queryClient.invalidateQueries({ queryKey: ["unplaced-books"] });
      queryClient.invalidateQueries({ queryKey: ["inventory-search"] });
    },
    onError: () => {
      queryClient.invalidateQueries({ queryKey: ["shelf-structure"] });
      queryClient.invalidateQueries({ queryKey: ["unplaced-books"] });
    },
    onSettled: (_data, _error, variables) => {
      clearRowsPending(variables?.rowId, variables?.sourceRowId);
    },
  });

  const createShelfMutation = useMutation({
    mutationFn: async ({ name, description }: { name: string; description: string }) => {
      const response = await api.post("/api/shelves", { name, description });
      return response.data as Shelf;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["shelf-structure"] });
      setSnackbar({ open: true, message: "Shelf created." });
      setShowAddShelf(false);
      setNewShelfName("");
      setNewShelfDescription("");
    },
    onError: () => {
      setSnackbar({ open: true, message: "Unable to create shelf." });
    },
  });

  const createRowMutation = useMutation({
    mutationFn: async ({ shelfId }: { shelfId: number }) => {
      const response = await api.post(`/api/shelves/${shelfId}/rows`, { name: "" });
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["shelf-structure"] });
      setSnackbar({ open: true, message: "Row added." });
    },
    onError: () => {
      setSnackbar({ open: true, message: "Unable to add row." });
    },
  });

  const data = useMemo(() => structureQuery.data ?? [], [structureQuery.data]);
  const unplacedBooks = useMemo(() => unplacedQuery.data ?? [], [unplacedQuery.data]);

  useEffect(() => {
    if (!data.length) {
      setRowPlacementsMap({});
      return;
    }

    const snapshot: RowPlacementMap = {};
    for (const block of data) {
      for (const row of block.rows) {
        snapshot[row.row.id] = [...row.placements].sort((a, b) => a.slot_index - b.slot_index);
      }
    }

    setRowPlacementsMap(snapshot);
  }, [data]);

  const isLoading = structureQuery.isLoading || unplacedQuery.isLoading;
  const hasError = structureQuery.isError || unplacedQuery.isError;

  if (isLoading) {
    return (
      <Stack alignItems="center" py={6}>
        <CircularProgress />
      </Stack>
    );
  }

  if (hasError) {
    return (
      <Paper variant="outlined" sx={{ p: 4, textAlign: "center" }}>
        <Typography variant="body1" color="error">
          Unable to load shelf overview. Please try again shortly.
        </Typography>
      </Paper>
    );
  }

  const addBookToRow = (book: Book, targetRowId: number, targetIndex: number) => {
    const previousRowPlacements = rowPlacementsMap[targetRowId]
      ? [...rowPlacementsMap[targetRowId]]
      : [];
    const previousUnplaced = (queryClient.getQueryData<Book[]>(["unplaced-books"]) ?? []).slice();

    setExpandedRows((prev) => {
      const next = new Set(prev);
      next.add(targetRowId);
      return next;
    });

    setRowPlacementsMap((prev) => {
      const next = { ...prev };
      const placements = [...(next[targetRowId] ?? [])];
      placements.splice(targetIndex, 0, buildPlacementFromBook(book));
      next[targetRowId] = reindexPlacements(placements);
      return next;
    });

    markRowsPending(targetRowId);
    assignPlacementMutation.mutate(
      { bookId: book.id, rowId: targetRowId, slotIndex: targetIndex + 1 },
      {
        onError: (error: any) => {
          setRowPlacementsMap((prev) => ({
            ...prev,
            [targetRowId]: previousRowPlacements,
          }));
          queryClient.setQueryData<Book[]>(["unplaced-books"], previousUnplaced);
          const detail = error?.response?.data?.detail;
          setSnackbar({
            open: true,
            message: detail ?? "Unable to place book. Reverted changes.",
          });
        },
      },
    );

    queryClient.setQueryData<Book[] | undefined>(["unplaced-books"], (previous) =>
      previous ? previous.filter((item) => item.id !== book.id) : previous,
    );
  };

  const moveBookBetweenRows = (bookId: number, sourceRowId: number, targetRowId: number, targetIndex: number) => {
    if (sourceRowId === targetRowId) {
      return;
    }

    const previousSourcePlacements = rowPlacementsMap[sourceRowId]
      ? [...rowPlacementsMap[sourceRowId]]
      : [];
    const previousTargetPlacements = rowPlacementsMap[targetRowId]
      ? [...rowPlacementsMap[targetRowId]]
      : [];
    const initialTargetLength = previousTargetPlacements.length;
    let nextTargetOrder: number[] = [];

    setExpandedRows((prev) => {
      const next = new Set(prev);
      next.add(targetRowId);
      return next;
    });

    setRowPlacementsMap((prev) => {
      const source = [...(prev[sourceRowId] ?? [])];
      const target = [...(prev[targetRowId] ?? [])];
      const movingIndex = source.findIndex((item) => item.book_id === bookId);
      if (movingIndex === -1) {
        return prev;
      }
      const [moving] = source.splice(movingIndex, 1);
      target.splice(targetIndex, 0, moving);
      const nextSource = reindexPlacements(source);
      const nextTarget = reindexPlacements(target);
      nextTargetOrder = nextTarget.map((item) => item.book_id);
      return {
        ...prev,
        [sourceRowId]: nextSource,
        [targetRowId]: nextTarget,
      };
    });

    markRowsPending(sourceRowId, targetRowId);
    const shouldReorderAfterMove = targetIndex !== initialTargetLength;
    assignPlacementMutation.mutate(
      {
        bookId,
        rowId: targetRowId,
        slotIndex: initialTargetLength + 1,
        sourceRowId,
      },
      {
        onSuccess: () => {
          if (shouldReorderAfterMove && nextTargetOrder.length > 0) {
            reorderMutation.mutate({ rowId: targetRowId, order: nextTargetOrder });
          }
        },
        onError: (error: any) => {
          setRowPlacementsMap((prev) => ({
            ...prev,
            [sourceRowId]: previousSourcePlacements,
            [targetRowId]: previousTargetPlacements,
          }));
          const detail = error?.response?.data?.detail;
          setSnackbar({
            open: true,
            message: detail ?? "Unable to move book between rows. Reverted changes.",
          });
        },
      },
    );
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over) {
      return;
    }

    const activeMeta = active.data.current as DragMeta | undefined;
    const overMeta = over.data.current as DropMeta | undefined;

    if (!activeMeta || !overMeta) {
      return;
    }

    const resolveInsertionIndex = (rowId: number, slotIndex?: number) => {
      const placements = rowPlacementsMap[rowId] ?? [];
      if (!slotIndex) {
        return placements.length;
      }
      return Math.max(0, Math.min(slotIndex - 1, placements.length));
    };

    if (activeMeta.sourceType === "row") {
      const sourceRowId = activeMeta.rowId;
      if (typeof sourceRowId !== "number") {
        return;
      }

      const sourcePlacements = rowPlacementsMap[sourceRowId] ?? [];
      const fromIndex = sourcePlacements.findIndex((item) => item.book_id === activeMeta.bookId);
      if (fromIndex === -1) {
        return;
      }

      const reorderWithinRow = (toIndex: number) => {
        const previousRowState = [...sourcePlacements];
        const updatedRow = reindexPlacements(arrayMove([...sourcePlacements], fromIndex, toIndex));
        setRowPlacementsMap((prev) => ({
          ...prev,
          [sourceRowId]: updatedRow,
        }));
        markRowsPending(sourceRowId);
        reorderMutation.mutate(
          { rowId: sourceRowId, order: updatedRow.map((item) => item.book_id) },
          {
            onError: (error: any) => {
              setRowPlacementsMap((prev) => ({
                ...prev,
                [sourceRowId]: previousRowState,
              }));
              const detail = error?.response?.data?.detail;
              setSnackbar({
                open: true,
                message: detail ?? "Unable to reorder books. Reverted changes.",
              });
            },
            onSettled: () => clearRowsPending(sourceRowId),
          },
        );
      };

      if (overMeta.targetType === "row-item") {
        const targetRowId = overMeta.rowId;
        if (targetRowId === sourceRowId) {
          const overBookId =
            overMeta.bookId ?? (typeof over.id === "number" ? (over.id as number) : undefined);
          if (overBookId === undefined) {
            return;
          }
          const toIndex = sourcePlacements.findIndex((item) => item.book_id === overBookId);
          if (toIndex === -1 || toIndex === fromIndex) {
            return;
          }
          reorderWithinRow(toIndex);
          return;
        }

        const targetPlacements = rowPlacementsMap[targetRowId] ?? [];
        const overBookId =
          overMeta.bookId ?? (typeof over.id === "number" ? (over.id as number) : undefined);
        const insertionIndex =
          overBookId === undefined
            ? targetPlacements.length
            : targetPlacements.findIndex((item) => item.book_id === overBookId);
        moveBookBetweenRows(
          activeMeta.bookId,
          sourceRowId,
          targetRowId,
          insertionIndex === -1 ? targetPlacements.length : insertionIndex,
        );
        return;
      }

      if (overMeta.targetType === "row-slot") {
        const targetRowId = overMeta.rowId;
        const insertionIndex = resolveInsertionIndex(targetRowId, overMeta.slotIndex);
        if (targetRowId === sourceRowId) {
          let adjustedIndex = insertionIndex;
          if (fromIndex < adjustedIndex) {
            adjustedIndex = Math.max(0, adjustedIndex - 1);
          }
          if (adjustedIndex === fromIndex) {
            return;
          }
          reorderWithinRow(adjustedIndex);
          return;
        }

        moveBookBetweenRows(activeMeta.bookId, sourceRowId, targetRowId, insertionIndex);
        return;
      }

      if (overMeta.targetType === "row") {
        const targetRowId = overMeta.rowId;
        if (targetRowId === sourceRowId) {
          if (fromIndex === sourcePlacements.length - 1) {
            return;
          }
          reorderWithinRow(sourcePlacements.length - 1);
          return;
        }

        const targetPlacements = rowPlacementsMap[targetRowId] ?? [];
        moveBookBetweenRows(activeMeta.bookId, sourceRowId, targetRowId, targetPlacements.length);
        return;
      }
    }

    if (activeMeta.sourceType === "unplaced") {
      const book = activeMeta.book;
      if (!book) {
        return;
      }

      if (overMeta.targetType === "row-item") {
        const targetRowId = overMeta.rowId;
        const targetPlacements = rowPlacementsMap[targetRowId] ?? [];
        const targetBookId =
          overMeta.bookId ?? (typeof over.id === "number" ? (over.id as number) : undefined);
        const insertionIndex =
          targetBookId === undefined
            ? targetPlacements.length
            : targetPlacements.findIndex((item) => item.book_id === targetBookId);
        addBookToRow(
          book,
          targetRowId,
          insertionIndex === -1 ? targetPlacements.length : insertionIndex,
        );
        return;
      }

      if (overMeta.targetType === "row-slot") {
        const targetRowId = overMeta.rowId;
        const insertionIndex = resolveInsertionIndex(targetRowId, overMeta.slotIndex);
        addBookToRow(book, targetRowId, insertionIndex);
        return;
      }

      if (overMeta.targetType === "row") {
        const targetRowId = overMeta.rowId;
        const targetPlacements = rowPlacementsMap[targetRowId] ?? [];
        addBookToRow(book, targetRowId, targetPlacements.length);
        return;
      }
    }
  };

  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
      <Box sx={{ display: { xs: "block", lg: "flex" }, gap: { xs: 2, lg: 3 } }}>
        <Box
          sx={{
            width: { xs: "100%", lg: 300 },
            flexShrink: 0,
            position: { lg: "sticky" },
            top: { lg: 76 },
            alignSelf: { lg: "flex-start" },
          }}
        >
          <UnplacedColumn books={unplacedBooks} />
        </Box>
        <Stack spacing={3} sx={{ flexGrow: 1 }}>
          <Paper sx={{ p: 3, borderRadius: 3 }}>
            <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems={{ xs: "flex-start", md: "center" }}>
              <Typography variant="h6" sx={{ flexGrow: 1 }}>
                Shelf Layout
              </Typography>
              <Button variant="contained" size="small" onClick={() => setShowAddShelf((prev) => !prev)}>
                {showAddShelf ? "Cancel" : "Add shelf"}
              </Button>
            </Stack>
            {showAddShelf && (
              <Stack spacing={2} sx={{ mt: 2 }}>
                <TextField
                  label="Shelf name"
                  value={newShelfName}
                  onChange={(event) => setNewShelfName(event.target.value)}
                  fullWidth
                  size="small"
                />
                <TextField
                  label="Description (optional)"
                  value={newShelfDescription}
                  onChange={(event) => setNewShelfDescription(event.target.value)}
                  fullWidth
                  size="small"
                  multiline
                  minRows={2}
                />
                <Button
                  variant="contained"
                  onClick={() =>
                    createShelfMutation.mutate({
                      name: newShelfName.trim() || "New shelf",
                      description: newShelfDescription.trim(),
                    })
                  }
                  disabled={createShelfMutation.isPending}
                >
                  Save shelf
                </Button>
              </Stack>
            )}
          </Paper>

          {data.length === 0 ? (
            <Paper sx={{ p: 3, borderRadius: 3 }}>
              <Typography variant="subtitle2" color="text.secondary">
                No shelves created yet. Add a shelf to get started.
              </Typography>
            </Paper>
          ) : (
            data.map((block) => (
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
                      const basePlacements = [...row.placements].sort((a, b) => a.slot_index - b.slot_index);
                      const rowId = row.row.id;
                      const rowPlacements = rowPlacementsMap[rowId] ?? basePlacements;
                      const isExpanded = expandedRows.has(rowId);
                      const isRowPending = pendingRows.has(rowId);

                      const handleSelectPlacement = (placement: ShelfPlacement) => {
                        setDetailTarget({
                          id: placement.book_id,
                          title: placement.title ?? null,
                          authors: placement.authors ?? null,
                          cover_asset: placement.cover_asset ?? null,
                          cover_path: placement.cover_path ?? null,
                          cover_url:
                            buildAssetUrl(placement.cover_asset ?? placement.cover_path ?? undefined) ?? null,
                          shelf_id: block.shelf.id,
                          shelf_name: block.shelf.name,
                          shelf_row_id: row.row.id,
                          row_name: row.row.name ?? `Row ${row.row.position}`,
                          slot_index: placement.slot_index,
                          subtitle: null,
                          first_publish_year: null,
                          edition_count: null,
                          openlibrary_key: null,
                          isbn: null,
                          subjects: null,
                          publisher: null,
                          number_of_pages_median: null,
                        });
                      };

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

                      return (
                        <ShelfRowSection
                          key={rowId}
                          rowInfo={row}
                          rowPlacements={rowPlacements}
                          isExpanded={isExpanded}
                          toggleRow={toggleRow}
                          isPending={isRowPending}
                          onSelectPlacement={handleSelectPlacement}
                        />
                      );
                    })
                  )}
                  <Button
                    variant="outlined"
                    size="small"
                    onClick={() => createRowMutation.mutate({ shelfId: block.shelf.id })}
                    disabled={createRowMutation.isPending}
                  >
                    Add row
                  </Button>
                </Stack>
              </Paper>
            ))
          )}
        </Stack>
      </Box>
      <BookDetailDialog open={Boolean(detailTarget)} bookId={detailTarget?.id ?? null} onClose={() => setDetailTarget(null)} />
      <Snackbar
        open={snackbar.open}
        autoHideDuration={4000}
        onClose={() => setSnackbar((prev) => ({ ...prev, open: false }))}
        message={snackbar.message}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      />
    </DndContext>
  );
}

interface ShelfRowSectionProps {
  rowInfo: ShelfBlock["rows"][number];
  rowPlacements: ShelfPlacement[];
  isExpanded: boolean;
  toggleRow: () => void;
  isPending: boolean;
  onSelectPlacement: (placement: ShelfPlacement) => void;
}

function ShelfRowSection({ rowInfo, rowPlacements, isExpanded, toggleRow, isPending, onSelectPlacement }: ShelfRowSectionProps) {
  const rowId = rowInfo.row.id;
  const placementCount = rowPlacements.length;
  const { setNodeRef, isOver } = useDroppable({
    id: `row-drop-${rowId}`,
    data: { targetType: "row", rowId },
  });
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const [visibleSlots, setVisibleSlots] = useState(MIN_VISIBLE_SLOTS);
  const [slotOffset, setSlotOffset] = useState(0);
  const placementBySlot = useMemo(() => {
    const map = new Map<number, ShelfPlacement>();
    for (const placement of rowPlacements) {
      map.set(placement.slot_index, placement);
    }
    return map;
  }, [rowPlacements]);
  const totalSlots = useMemo(() => {
    const baseCount = rowPlacements.length;
    const capacity =
      rowInfo.row.capacity && rowInfo.row.capacity > 0 ? rowInfo.row.capacity : Number.POSITIVE_INFINITY;
    const hasRoomForNewPlacement = capacity === Number.POSITIVE_INFINITY || baseCount < capacity;
    const minimumSlots = hasRoomForNewPlacement ? baseCount + 1 : baseCount;
    const desired = Math.max(minimumSlots, visibleSlots);
    return capacity === Number.POSITIVE_INFINITY ? desired : Math.min(desired, capacity);
  }, [rowPlacements.length, rowInfo.row.capacity, visibleSlots]);
  const sliceLength = useMemo(() => Math.min(visibleSlots, Math.max(totalSlots, 0)), [totalSlots, visibleSlots]);
  const maxOffset = useMemo(() => Math.max(0, totalSlots - sliceLength), [totalSlots, sliceLength]);
  useEffect(() => {
    setSlotOffset((prev) => {
      if (prev > maxOffset) {
        return maxOffset;
      }
      if (prev < 0) {
        return 0;
      }
      return prev;
    });
  }, [maxOffset]);
  const visibleSlotNumbers = useMemo(() => {
    if (sliceLength === 0 || totalSlots === 0) {
      return [] as number[];
    }
    const start = Math.min(slotOffset, maxOffset);
    return Array.from({ length: sliceLength }, (_, index) => start + index + 1);
  }, [sliceLength, slotOffset, maxOffset, totalSlots]);
  const visiblePlacementIds = useMemo(() => {
    const ids: number[] = [];
    for (const slot of visibleSlotNumbers) {
      const placement = placementBySlot.get(slot);
      if (placement) {
        ids.push(placement.book_id);
      }
    }
    return ids;
  }, [placementBySlot, visibleSlotNumbers]);
  const trackSlots = useMemo(() => {
    if (visibleSlotNumbers.length === 0) {
      return Math.min(Math.max(totalSlots, 1), visibleSlots);
    }
    return Math.max(visibleSlotNumbers.length, Math.min(Math.max(totalSlots, 1), visibleSlots));
  }, [totalSlots, visibleSlotNumbers.length, visibleSlots]);
  const trackWidth = useMemo(() => trackSlots * SLOT_WIDTH, [trackSlots]);
  const canScrollLeft = slotOffset > 0;
  const canScrollRight = slotOffset < maxOffset;

  const handleWheel = useCallback(
    (event: WheelEvent<HTMLDivElement>) => {
      if (Math.abs(event.deltaX) < Math.abs(event.deltaY)) {
        event.preventDefault();
        const direction = event.deltaY > 0 ? 1 : -1;
        setSlotOffset((prev) => {
          const next = prev + direction;
          if (next < 0) {
            return 0;
          }
          if (next > maxOffset) {
            return maxOffset;
          }
          return next;
        });
      }
    },
    [maxOffset],
  );

  useEffect(() => {
    const node = scrollContainerRef.current;
    if (!node || !isExpanded) {
      setVisibleSlots(MIN_VISIBLE_SLOTS);
      return;
    }

    const computeVisibleSlots = (width: number) => {
      if (!width || Number.isNaN(width)) {
        setVisibleSlots(MIN_VISIBLE_SLOTS);
        return;
      }
      const slotsFit = Math.floor(width / SLOT_WIDTH);
      const clamped = Math.max(
        MIN_VISIBLE_SLOTS,
        Math.min(MAX_VIEWPORT_SLOTS, slotsFit > 0 ? slotsFit : MIN_VISIBLE_SLOTS),
      );
      setVisibleSlots(clamped);
    };

    computeVisibleSlots(node.clientWidth);

    const ObserverClass =
      typeof window !== "undefined" && "ResizeObserver" in window
        ? window.ResizeObserver
        : typeof globalThis !== "undefined" && "ResizeObserver" in globalThis
          ? (globalThis.ResizeObserver as typeof ResizeObserver)
          : undefined;
    if (!ObserverClass) {
      return;
    }

    const observer = new ObserverClass((entries: ResizeObserverEntry[]) => {
      for (const entry of entries) {
        computeVisibleSlots(entry.contentRect.width);
      }
    });
    observer.observe(node);

    return () => observer.disconnect();
  }, [isExpanded, rowId]);

  useEffect(() => {
    setSlotOffset(0);
  }, [rowId]);

  const handleScroll = (direction: "left" | "right") => {
    const step = Math.max(1, visibleSlots - 1);
    setSlotOffset((prev) => {
      const next = direction === "left" ? prev - step : prev + step;
      if (next < 0) {
        return 0;
      }
      if (next > maxOffset) {
        return maxOffset;
      }
      return next;
    });
  };

  return (
    <Box
      ref={setNodeRef}
      sx={{
        position: "relative",
        width: "100%",
        maxWidth: "100%",
        overflow: "hidden",
        borderRadius: 2,
        border: "1px dashed",
        borderColor: isOver ? "primary.light" : "transparent",
        transition: "border-color 0.2s ease",
        px: 1,
        py: 0.5,
      }}
    >
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Typography variant="subtitle2">
          {rowInfo.row.name ? rowInfo.row.name : `Row ${rowInfo.row.position}`} · {placementCount}{" "}
          {placementCount === 1 ? "book" : "books"}
        </Typography>
        <Tooltip title={isExpanded ? "Collapse row" : "Expand row"}>
          <IconButton size="small" onClick={toggleRow}>
            {isExpanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
          </IconButton>
        </Tooltip>
      </Stack>
      {isExpanded && (
        <Box sx={{ position: "relative", mt: 1 }}>
          {isPending && (
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
          <SortableContext items={visiblePlacementIds} strategy={rectSwappingStrategy}>
            <Box sx={{ position: "relative" }}>
              <Box
                ref={scrollContainerRef}
                onWheel={handleWheel}
                sx={{
                  display: "flex",
                  gap: `${CARD_GAP}px`,
                  overflow: "hidden",
                  p: 1,
                  borderRadius: 2,
                  backgroundColor: "rgba(255,255,255,0.04)",
                  minHeight: CARD_HEIGHT,
                  width: "100%",
                  maxWidth: `${MAX_VIEWPORT_SLOTS * SLOT_WIDTH}px`,
                  position: "relative",
                }}
              >
                <Box
                  sx={{
                    display: "flex",
                    gap: `${CARD_GAP}px`,
                    width: `${trackWidth}px`,
                  }}
                >
                  {visibleSlotNumbers.map((slotIndex) => {
                    const placement = placementBySlot.get(slotIndex);
                    if (placement) {
                      return (
                        <SortablePlacementCard
                          key={placement.book_id}
                          placement={placement}
                          rowId={rowId}
                          onSelect={() => onSelectPlacement(placement)}
                        />
                      );
                    }
                    return <RowSlotPlaceholder key={`slot-${rowId}-${slotIndex}`} rowId={rowId} slotIndex={slotIndex} />;
                  })}
                </Box>
              </Box>
              {canScrollLeft && (
                <IconButton
                  size="small"
                  onClick={() => handleScroll("left")}
                  sx={{
                    position: "absolute",
                    top: "50%",
                    left: 4,
                    transform: "translateY(-50%)",
                    backgroundColor: "rgba(15,23,42,0.85)",
                    color: "common.white",
                    boxShadow: 1,
                    "&:hover": { backgroundColor: "rgba(15,23,42,0.9)" },
                  }}
                >
                  <ChevronLeftIcon fontSize="small" />
                </IconButton>
              )}
              {canScrollRight && (
                <IconButton
                  size="small"
                  onClick={() => handleScroll("right")}
                  sx={{
                    position: "absolute",
                    top: "50%",
                    right: 4,
                    transform: "translateY(-50%)",
                    backgroundColor: "rgba(15,23,42,0.85)",
                    color: "common.white",
                    boxShadow: 1,
                    "&:hover": { backgroundColor: "rgba(15,23,42,0.9)" },
                  }}
                >
                  <ChevronRightIcon fontSize="small" />
                </IconButton>
              )}
            </Box>
          </SortableContext>
        </Box>
      )}
    </Box>
  );
}

function SortablePlacementCard({
  placement,
  rowId,
  onSelect,
}: {
  placement: ShelfPlacement;
  rowId: number;
  onSelect: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging, isOver } = useSortable({
    id: placement.book_id,
    data: {
      sourceType: "row",
      targetType: "row-item",
      rowId,
      bookId: placement.book_id,
    },
  });

  const style = {
    transform: transform ? CSS.Transform.toString(transform) : undefined,
    transition,
    opacity: isDragging ? 0.6 : 1,
    cursor: "grab",
  };

  const assetUrl = buildAssetUrl(placement.cover_asset ?? placement.cover_path ?? undefined);

  return (
    <Box
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      sx={{ flex: "0 0 auto" }}
    >
      <Box
        sx={{
          width: CARD_WIDTH,
          minHeight: CARD_HEIGHT,
          borderRadius: 3,
          border: "1px solid",
          borderColor: isOver ? "primary.light" : "primary.main",
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
              sx={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain" }}
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

function RowSlotPlaceholder({ rowId, slotIndex }: { rowId: number; slotIndex: number }) {
  const { setNodeRef, isOver } = useDroppable({
    id: `row-slot-${rowId}-${slotIndex}`,
    data: {
      targetType: "row-slot",
      rowId,
      slotIndex,
    },
  });

  return (
    <Box
      ref={setNodeRef}
      sx={{
        flex: "0 0 auto",
        width: CARD_WIDTH,
        minHeight: CARD_HEIGHT,
        borderRadius: 3,
        border: "2px dashed",
        borderColor: isOver ? "primary.light" : "rgba(148,163,184,0.4)",
        backgroundColor: "rgba(15,23,42,0.32)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        color: "rgba(148,163,184,0.7)",
        fontSize: 12,
        textTransform: "uppercase",
        letterSpacing: 1,
      }}
    >
      Slot {slotIndex}
    </Box>
  );
}

function UnplacedColumn({ books }: { books: Book[] }) {
  return (
    <Paper sx={{ p: 3, borderRadius: 3, backgroundColor: "rgba(15,23,42,0.45)" }}>
      <Typography variant="h6" gutterBottom>
        Unplaced Books
      </Typography>
      {books.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          All books are currently placed on shelves.
        </Typography>
      ) : (
        <Stack
          spacing={2}
          sx={{
            maxHeight: { xs: 280, lg: "calc(100vh - 220px)" },
            overflowY: "auto",
            pr: 1,
          }}
        >
          {books.map((book) => (
            <UnplacedDraggable key={book.id} book={book} />
          ))}
        </Stack>
      )}
    </Paper>
  );
}

function UnplacedDraggable({ book }: { book: Book }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: `unplaced-${book.id}`,
    data: {
      sourceType: "unplaced",
      bookId: book.id,
      book,
    },
  });

  const style = {
    transform: transform ? CSS.Transform.toString(transform) : undefined,
    opacity: isDragging ? 0.6 : 1,
    cursor: "grab",
  };

  const coverSrc = buildAssetUrl(book.cover_asset ?? book.cover_path ?? book.cover_url ?? undefined);

  return (
    <Box ref={setNodeRef} style={style} {...attributes} {...listeners}>
      <Box
        sx={{
          borderRadius: 3,
          border: "1px solid rgba(148,163,184,0.3)",
          backgroundColor: "rgba(15, 23, 42, 0.6)",
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <Box
          sx={{
            height: 200,
            backgroundColor: "rgba(148,163,184,0.1)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            overflow: "hidden",
          }}
        >
          {coverSrc ? (
            <Box component="img" src={coverSrc} alt={book.title ?? "Book cover"} sx={{ maxHeight: "100%", objectFit: "contain" }} />
          ) : (
            <Typography variant="caption" color="text.secondary">
              No cover
            </Typography>
          )}
        </Box>
        <Box sx={{ p: 1 }}>
          <Typography variant="subtitle2" noWrap>
            {book.title ?? "Untitled"}
          </Typography>
          <Typography variant="caption" color="text.secondary" noWrap>
            {book.authors ?? "Unknown author"}
          </Typography>
        </Box>
      </Box>
    </Box>
  );
}

function buildPlacementFromBook(book: Book): ShelfPlacement {
  return {
    book_id: book.id,
    title: book.title ?? null,
    authors: book.authors ?? null,
    cover_asset: book.cover_asset ?? undefined,
    cover_path: book.cover_path ?? undefined,
    slot_index: 1,
  };
}

function reindexPlacements(placements: ShelfPlacement[]): ShelfPlacement[] {
  return placements.map((placement, index) => ({
    ...placement,
    slot_index: index + 1,
  }));
}
