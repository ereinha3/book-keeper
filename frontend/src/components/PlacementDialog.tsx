import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Book, ShelfBlock } from "../api/types";
import { api } from "../api/client";

export interface PlacementDialogProps {
  open: boolean;
  book: Book | null;
  onClose: () => void;
  onPlaced?: () => void;
}

function computeAvailableSlots(placements: Array<{ slot_index: number }>): number[] {
  const occupied = placements.map((p) => p.slot_index).sort((a, b) => a - b);
  const maxSlot = occupied.length ? occupied[occupied.length - 1] : 0;
  const available: number[] = [];
  const seen = new Set(occupied);

  for (let i = 1; i <= maxSlot; i += 1) {
    if (!seen.has(i)) {
      available.push(i);
    }
  }
  available.push(maxSlot + 1 || 1);
  return available;
}

export function PlacementDialog({ open, book, onClose, onPlaced }: PlacementDialogProps) {
  const queryClient = useQueryClient();
  const [selectedShelf, setSelectedShelf] = useState<number | "">("");
  const [selectedRow, setSelectedRow] = useState<number | "">("");
  const [selectedSlot, setSelectedSlot] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const shelvesQuery = useQuery({
    queryKey: ["shelves"],
    queryFn: async () => {
      const response = await api.get("/api/shelves");
      return response.data;
    },
    enabled: open,
    staleTime: 5 * 60 * 1000,
  });

  const structureQuery = useQuery<ShelfBlock[]>({
    queryKey: ["shelf-structure"],
    queryFn: async () => {
      const response = await api.get<ShelfBlock[]>("/api/shelf-structure");
      return response.data;
    },
    enabled: open,
  });

  useEffect(() => {
    if (open) {
      setSelectedShelf(book?.shelf_id ?? "");
      setSelectedRow(book?.shelf_row_id ?? "");
      setSelectedSlot(book?.slot_index ?? null);
      setError(null);
    }
  }, [open, book]);

  const shelfBlocks = structureQuery.data ?? [];
  const rowsForShelf = useMemo(() => {
    if (!selectedShelf) {
      return [];
    }
    const shelf = shelfBlocks.find((block) => block.shelf.id === selectedShelf);
    return shelf?.rows ?? [];
  }, [shelfBlocks, selectedShelf]);

  const placementsForRow = useMemo(() => {
    if (!selectedRow) {
      return [];
    }
    return rowsForShelf.find((row) => row.row.id === selectedRow)?.placements ?? [];
  }, [rowsForShelf, selectedRow]);

  const availableSlots = useMemo(() => computeAvailableSlots(placementsForRow), [placementsForRow]);

  useEffect(() => {
    if (selectedRow && availableSlots.length > 0) {
      if (!selectedSlot || !availableSlots.includes(selectedSlot)) {
        setSelectedSlot(availableSlots[0]);
      }
    }
  }, [selectedRow, availableSlots, selectedSlot]);

  const placementMutation = useMutation({
    mutationFn: async () => {
      if (!book || !selectedRow || !selectedSlot) {
        throw new Error("Missing placement details.");
      }
      await api.post(`/api/books/${book.id}/placement`, {
        shelf_row_id: selectedRow,
        slot_index: selectedSlot,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["books"] });
      queryClient.invalidateQueries({ queryKey: ["shelf-structure"] });
      queryClient.invalidateQueries({ queryKey: ["unplaced-books"] });
      setError(null);
      if (onPlaced) {
        onPlaced();
      }
      onClose();
    },
    onError: (mutationError: any) => {
      setError(
        mutationError?.response?.data?.detail ??
          mutationError?.message ??
          "Unable to update placement. Please try again."
      );
    },
  });

  const handleShelfChange = (value: number | "") => {
    setSelectedShelf(value);
    setSelectedRow("");
    setSelectedSlot(null);
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    placementMutation.mutate();
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Place “{book?.title ?? "Unknown title"}”</DialogTitle>
      <DialogContent>
        <Stack spacing={2} mt={1} component="form" onSubmit={handleSubmit}>
          <TextField
            select
            label="Shelf"
            value={selectedShelf}
            onChange={(event) => handleShelfChange(event.target.value as number | "")}
            fullWidth
            required
            helperText="Choose the shelf for this book"
          >
            {shelvesQuery.data?.map((shelf: any) => (
              <MenuItem key={shelf.id} value={shelf.id}>
                {shelf.name}
              </MenuItem>
            ))}
          </TextField>

          <TextField
            select
            label="Row"
            value={selectedRow}
            onChange={(event) => setSelectedRow(event.target.value as number | "")}
            fullWidth
            required
            disabled={!selectedShelf}
            helperText={selectedShelf ? "Select a row within this shelf" : "Select a shelf first"}
          >
            {rowsForShelf.map((row) => (
              <MenuItem key={row.row.id} value={row.row.id}>
                {row.row.name ? `${row.row.name}` : `Row ${row.row.position}`} · {row.placements.length} books
              </MenuItem>
            ))}
          </TextField>

          <Stack spacing={1} sx={{ opacity: selectedRow ? 1 : 0.4 }}>
            <Typography variant="subtitle2">Choose a slot</Typography>
            <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
              {availableSlots.map((slot) => (
                <Button
                  key={slot}
                  size="small"
                  variant={selectedSlot === slot ? "contained" : "outlined"}
                  onClick={() => setSelectedSlot(slot)}
                  disabled={!selectedRow}
                >
                  {slot === Math.max(...availableSlots) ? `Slot ${slot} (end)` : `Slot ${slot}`}
                </Button>
              ))}
              {selectedRow && placementsForRow.some((p) => p.slot_index === selectedSlot) && (
                <Button
                  size="small"
                  variant="outlined"
                  onClick={() => setSelectedSlot((placementsForRow.length || 0) + 1)}
                >
                  Place at end
                </Button>
              )}
            </Box>
          </Stack>

          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 3 }}>
        <Button onClick={onClose} variant="text">
          Skip placement
        </Button>
        <Button
          onClick={handleSubmit}
          variant="contained"
          disabled={placementMutation.isPending || !selectedRow || !selectedSlot}
        >
          Save placement
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export default PlacementDialog;


