import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  IconButton,
  Paper,
  Snackbar,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import AddOutlined from "@mui/icons-material/AddOutlined";
import DeleteOutline from "@mui/icons-material/DeleteOutline";
import EditOutlined from "@mui/icons-material/EditOutlined";
import WarehouseOutlined from "@mui/icons-material/WarehouseOutlined";
import { api } from "../api/client";
import type { Shelf, ShelfRow } from "../api/types";

interface ShelfFormDialogProps {
  open: boolean;
  initialShelf?: Shelf | null;
  onClose: () => void;
}

function ShelfFormDialog({ open, initialShelf, onClose }: ShelfFormDialogProps) {
  const queryClient = useQueryClient();
  const isEdit = Boolean(initialShelf);
  const [name, setName] = useState(initialShelf?.name ?? "");
  const [description, setDescription] = useState(initialShelf?.description ?? "");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setName(initialShelf?.name ?? "");
      setDescription(initialShelf?.description ?? "");
      setError(null);
    }
  }, [open, initialShelf]);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!name.trim()) {
        throw new Error("Shelf name is required.");
      }
      if (isEdit && initialShelf) {
        await api.put(`/api/shelves/${initialShelf.id}`, {
          name: name.trim(),
          description: description.trim(),
        });
      } else {
        await api.post("/api/shelves", {
          name: name.trim(),
          description: description.trim() || undefined,
        });
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["shelves"] });
      queryClient.invalidateQueries({ queryKey: ["shelf-structure"] });
      onClose();
    },
    onError: (mutationError: any) => {
      setError(mutationError?.response?.data?.detail ?? mutationError?.message ?? "Unable to save shelf.");
    },
  });

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    mutation.mutate();
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{isEdit ? "Edit shelf" : "Create shelf"}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} component="form" onSubmit={handleSubmit} mt={1}>
          <TextField
            label="Shelf name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            required
            fullWidth
            autoFocus
          />
          <TextField
            label="Description"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            multiline
            minRows={2}
            fullWidth
          />
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} color="inherit">
          Cancel
        </Button>
        <Button onClick={handleSubmit} disabled={mutation.isPending} variant="contained">
          {isEdit ? "Save changes" : "Create shelf"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

interface RowFormDialogProps {
  open: boolean;
  shelfId: number | null;
  initialRow?: ShelfRow | null;
  onClose: () => void;
}

function RowFormDialog({ open, shelfId, initialRow, onClose }: RowFormDialogProps) {
  const queryClient = useQueryClient();
  const isEdit = Boolean(initialRow);
  const [name, setName] = useState(initialRow?.name ?? "");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setName(initialRow?.name ?? "");
      setError(null);
    }
  }, [open, initialRow]);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!shelfId) {
        throw new Error("Shelf not selected.");
      }
      if (isEdit && initialRow) {
        await api.put(`/api/rows/${initialRow.id}`, {
          name: name.trim() || undefined,
        });
      } else {
        await api.post(`/api/shelves/${shelfId}/rows`, {
          name: name.trim() || undefined,
        });
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["shelves", shelfId, "rows"] });
      queryClient.invalidateQueries({ queryKey: ["shelf-structure"] });
      setError(null);
      onClose();
    },
    onError: (mutationError: any) => {
      setError(mutationError?.response?.data?.detail ?? mutationError?.message ?? "Unable to save row.");
    },
  });

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    mutation.mutate();
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{isEdit ? "Edit row" : "Create row"}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} component="form" onSubmit={handleSubmit} mt={1}>
          <TextField
            label="Row name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            helperText="Optional — leave blank to use a numeric label"
            fullWidth
          />
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} color="inherit">
          Cancel
        </Button>
        <Button onClick={handleSubmit} disabled={mutation.isPending} variant="contained">
          {isEdit ? "Save changes" : "Create row"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export default function ShelvesView() {
  const queryClient = useQueryClient();
  const [selectedShelfId, setSelectedShelfId] = useState<number | null>(null);
  const [shelfDialog, setShelfDialog] = useState<{ open: boolean; shelf?: Shelf | null }>({ open: false });
  const [rowDialog, setRowDialog] = useState<{ open: boolean; row?: ShelfRow | null }>({ open: false });
  const [snackbar, setSnackbar] = useState<{ open: boolean; message: string; severity: "success" | "error" }>({
    open: false,
    message: "",
    severity: "success",
  });

  const shelvesQuery = useQuery<Shelf[]>({
    queryKey: ["shelves"],
    queryFn: async () => {
      const response = await api.get<Shelf[]>("/api/shelves");
      return response.data;
    },
  });

  const rowsQuery = useQuery<ShelfRow[]>({
    queryKey: ["shelves", selectedShelfId, "rows"],
    queryFn: async () => {
      const response = await api.get<ShelfRow[]>(`/api/shelves/${selectedShelfId}/rows`);
      return response.data;
    },
    enabled: selectedShelfId !== null,
  });

  useEffect(() => {
    if (shelvesQuery.data && shelvesQuery.data.length > 0 && selectedShelfId === null) {
      setSelectedShelfId(shelvesQuery.data[0].id);
    }
  }, [shelvesQuery.data, selectedShelfId]);

  const deleteShelfMutation = useMutation({
    mutationFn: async (shelfId: number) => {
      await api.delete(`/api/shelves/${shelfId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["shelves"] });
      queryClient.invalidateQueries({ queryKey: ["shelf-structure"] });
      setSnackbar({ open: true, message: "Shelf deleted.", severity: "success" });
      setSelectedShelfId(null);
    },
    onError: (error: any) => {
      const message =
        error?.response?.data?.detail ??
        "Unable to delete shelf. Remove rows first or ensure no books are assigned.";
      setSnackbar({ open: true, message, severity: "error" });
    },
  });

  const deleteRowMutation = useMutation({
    mutationFn: async (rowId: number) => {
      await api.delete(`/api/rows/${rowId}`);
    },
    onSuccess: () => {
      if (selectedShelfId) {
        queryClient.invalidateQueries({ queryKey: ["shelves", selectedShelfId, "rows"] });
        queryClient.invalidateQueries({ queryKey: ["shelf-structure"] });
      }
      setSnackbar({ open: true, message: "Row deleted.", severity: "success" });
    },
    onError: (error: any) => {
      const message = error?.response?.data?.detail ?? "Unable to delete row.";
      setSnackbar({ open: true, message, severity: "error" });
    },
  });

  const shelves = shelvesQuery.data ?? [];
  const selectedShelf = shelves.find((shelf) => shelf.id === selectedShelfId) ?? null;
  const rows = rowsQuery.data ?? [];

  return (
    <Box>
      <Stack direction={{ xs: "column", md: "row" }} spacing={3} alignItems="flex-start">
        <Box flex={1} width="100%">
          <Stack direction="row" alignItems="center" justifyContent="space-between" mb={2}>
            <Typography variant="h6" sx={{ display: "flex", alignItems: "center", gap: 1 }}>
              <WarehouseOutlined fontSize="small" />
              Bookshelves
            </Typography>
            <Button
              variant="contained"
              startIcon={<AddOutlined />}
              onClick={() => setShelfDialog({ open: true, shelf: null })}
            >
              New shelf
            </Button>
          </Stack>

          <Stack spacing={1.5}>
            {shelves.length === 0 ? (
              <Paper variant="outlined" sx={{ p: 3, textAlign: "center" }}>
                <Typography variant="body2" color="text.secondary">
                  No shelves created yet. Add your first shelf to start organizing rows.
                </Typography>
              </Paper>
            ) : (
              shelves.map((shelf) => {
                const isActive = shelf.id === selectedShelfId;
                return (
                  <Paper
                    key={shelf.id}
                    variant={isActive ? "elevation" : "outlined"}
                    elevation={isActive ? 6 : 0}
                    sx={{
                      p: 2,
                      borderRadius: 3,
                      cursor: "pointer",
                      bgcolor: isActive ? "primary.main" : "background.paper",
                      color: isActive ? "primary.contrastText" : "text.primary",
                      transition: "transform 0.15s ease",
                      "&:hover": { transform: "translateY(-2px)" },
                    }}
                    onClick={() => setSelectedShelfId(shelf.id)}
                  >
                    <Stack direction="row" justifyContent="space-between">
                      <Box>
                        <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                          {shelf.name}
                        </Typography>
                        {shelf.description && (
                          <Typography variant="body2" sx={{ opacity: 0.8 }}>
                            {shelf.description}
                          </Typography>
                        )}
                        <Typography variant="caption" sx={{ opacity: 0.7 }}>
                          {shelf.row_count} row{shelf.row_count === 1 ? "" : "s"}
                        </Typography>
                      </Box>
                      <Stack direction="row" spacing={1}>
                        <Tooltip title="Edit shelf">
                          <IconButton
                            size="small"
                            color={isActive ? "inherit" : "default"}
                            onClick={(event) => {
                              event.stopPropagation();
                              setShelfDialog({ open: true, shelf });
                            }}
                          >
                            <EditOutlined fontSize="small" />
                          </IconButton>
                        </Tooltip>
                        <Tooltip title="Delete shelf">
                          <IconButton
                            size="small"
                            color={isActive ? "inherit" : "default"}
                            onClick={(event) => {
                              event.stopPropagation();
                              if (window.confirm("Delete this shelf? Rows must be empty before deletion.")) {
                                deleteShelfMutation.mutate(shelf.id);
                              }
                            }}
                          >
                            <DeleteOutline fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      </Stack>
                    </Stack>
                  </Paper>
                );
              })
            )}
          </Stack>
        </Box>

        <Divider orientation="vertical" flexItem sx={{ display: { xs: "none", md: "block" } }} />

        <Box flex={2} width="100%">
          <Stack direction="row" alignItems="center" justifyContent="space-between" mb={2}>
            <Typography variant="h6">
              {selectedShelf ? `Rows in “${selectedShelf.name}”` : "Select a shelf"}
            </Typography>
            <Button
              variant="outlined"
              startIcon={<AddOutlined />}
              disabled={!selectedShelf}
              onClick={() => setRowDialog({ open: true, row: null })}
            >
              New row
            </Button>
          </Stack>

          {selectedShelf ? (
            rows.length === 0 ? (
              <Paper variant="outlined" sx={{ p: 3, textAlign: "center" }}>
                <Typography variant="body2" color="text.secondary">
                  No rows created for this shelf yet. Add rows to start placing books.
                </Typography>
              </Paper>
            ) : (
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Name</TableCell>
                    <TableCell align="center">Position</TableCell>
                    <TableCell align="center">Books</TableCell>
                    <TableCell align="center">Next slot</TableCell>
                    <TableCell align="right">Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {rows.map((row) => (
                    <TableRow key={row.id} hover>
                      <TableCell>{row.name || `Row ${row.position}`}</TableCell>
                      <TableCell align="center">{row.position}</TableCell>
                      <TableCell align="center">{row.used}</TableCell>
                      <TableCell align="center">{(row as any).max_slot + 1}</TableCell>
                      <TableCell align="right">
                        <Tooltip title="Edit row">
                          <IconButton size="small" onClick={() => setRowDialog({ open: true, row })}>
                            <EditOutlined fontSize="small" />
                          </IconButton>
                        </Tooltip>
                        <Tooltip title="Delete row">
                          <IconButton
                            size="small"
                            onClick={() => {
                              if (window.confirm("Delete this row? It must not contain any books.")) {
                                deleteRowMutation.mutate(row.id);
                              }
                            }}
                          >
                            <DeleteOutline fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )
          ) : (
            <Paper variant="outlined" sx={{ p: 3, textAlign: "center" }}>
              <Typography variant="body2" color="text.secondary">
                Select a shelf to view and manage its rows.
              </Typography>
            </Paper>
          )}
        </Box>
      </Stack>

      <ShelfFormDialog
        open={shelfDialog.open}
        initialShelf={shelfDialog.shelf ?? null}
        onClose={() => setShelfDialog({ open: false })}
      />
      <RowFormDialog
        open={rowDialog.open}
        shelfId={selectedShelfId}
        initialRow={rowDialog.row ?? null}
        onClose={() => setRowDialog({ open: false })}
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

