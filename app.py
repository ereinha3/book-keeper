from __future__ import annotations

import sys
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from api import COVER_URL_TEMPLATE, OpenLibraryQuery, build_record, fetch_records
from inventory import InventoryStore, PlacementInfo
from media import cached_cover_path, fetch_and_cache_cover, load_thumbnail


# --------------------------------------------------------------------------- #
# Utility helpers
# --------------------------------------------------------------------------- #
def truncate(value: str, length: int) -> str:
    if len(value) <= length:
        return value
    return value[: length - 1] + "…"


# --------------------------------------------------------------------------- #
# Search panel
# --------------------------------------------------------------------------- #
class SearchFrame(ttk.Frame):
    def __init__(self, master: ttk.Notebook, controller: "MainApplication"):
        super().__init__(master, padding=12)
        self.controller = controller
        self.results: List[Dict] = []
        self.current_cover_image: Optional[tk.PhotoImage] = None
        self.cards: List[Dict[str, Any]] = []
        self.selected_index: Optional[int] = None
        self.current_query: Optional[OpenLibraryQuery] = None
        self.current_page: int = 0
        self.total_results: int = 0
        self.limit: int = 5
        self.base_bg = self.winfo_toplevel().cget("background")
        self.card_width = 360
        self.card_height = 140
        self.card_default_bg = "#2f2f2f"
        self.card_selected_bg = "#dbe6ff"
        self.inactive_text = "#f2f2f2"
        self.photo_cache_small: Dict[str, tk.PhotoImage] = {}
        self.photo_cache_large: Dict[str, tk.PhotoImage] = {}
        self.pending_small: Set[str] = set()
        self.pending_large: Set[str] = set()
        self.detail_current_key: Optional[str] = None
        self.no_results_label: Optional[tk.Label] = None

        self._build_ui()

    def _build_ui(self) -> None:
        form = ttk.Frame(self)
        form.grid(row=0, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Keywords:").grid(row=0, column=0, sticky="w", pady=2)
        self.keywords_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.keywords_var).grid(
            row=0, column=1, sticky="ew", padx=(4, 0), pady=2
        )

        ttk.Label(form, text="Title:").grid(row=1, column=0, sticky="w", pady=2)
        self.title_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.title_var).grid(
            row=1, column=1, sticky="ew", padx=(4, 0), pady=2
        )

        ttk.Label(form, text="Author:").grid(row=2, column=0, sticky="w", pady=2)
        self.author_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.author_var).grid(
            row=2, column=1, sticky="ew", padx=(4, 0), pady=2
        )

        ttk.Label(form, text="First publish year:").grid(
            row=3, column=0, sticky="w", pady=2
        )
        self.year_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.year_var).grid(
            row=3, column=1, sticky="ew", padx=(4, 0), pady=2
        )

        self.search_button = ttk.Button(
            form, text="Search Open Library", command=self.perform_search
        )
        self.search_button.grid(row=4, column=0, columnspan=2, pady=(8, 12))

        body = ttk.Frame(self)
        body.grid(row=1, column=0, sticky="nsew")
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        body.columnconfigure(0, weight=1, minsize=360)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        results_container = ttk.Frame(body)
        results_container.grid(row=0, column=0, sticky="nsew")
        results_container.columnconfigure(0, weight=1)
        results_container.rowconfigure(0, weight=1)

        self.results_canvas = tk.Canvas(
            results_container,
            highlightthickness=0,
            background=self.winfo_toplevel().cget("background"),
        )
        self.results_canvas.grid(row=0, column=0, sticky="nsew")
        results_scroll = ttk.Scrollbar(
            results_container, orient="vertical", command=self.results_canvas.yview
        )
        results_scroll.grid(row=0, column=1, sticky="ns")
        self.results_canvas.configure(yscrollcommand=results_scroll.set)

        self.results_frame = ttk.Frame(self.results_canvas)
        self.results_window = self.results_canvas.create_window(
            (0, 0), window=self.results_frame, anchor="nw"
        )
        self.results_frame.columnconfigure(0, weight=1)
        self.results_frame.bind(
            "<Configure>",
            lambda _event: self.results_canvas.configure(
                scrollregion=self.results_canvas.bbox("all")
            ),
        )
        self.results_canvas.bind("<Enter>", self._bind_mousewheel)
        self.results_canvas.bind("<Leave>", self._unbind_mousewheel)
        self.results_frame.bind("<Enter>", self._bind_mousewheel)
        self.results_frame.bind("<Leave>", self._unbind_mousewheel)
        self.results_canvas.bind("<Enter>", self._bind_mousewheel)
        self.results_canvas.bind("<Leave>", self._unbind_mousewheel)
        self.results_frame.bind("<Enter>", self._bind_mousewheel)
        self.results_frame.bind("<Leave>", self._unbind_mousewheel)

        nav_frame = ttk.Frame(results_container)
        nav_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        nav_frame.columnconfigure(1, weight=1)

        self.prev_button = ttk.Button(
            nav_frame, text="← Previous", command=self.prev_page, state="disabled"
        )
        self.prev_button.grid(row=0, column=0, padx=(0, 6))

        self.page_label = ttk.Label(nav_frame, text="No results yet.")
        self.page_label.grid(row=0, column=1, sticky="ew")

        self.next_button = ttk.Button(
            nav_frame, text="Next →", command=self.next_page, state="disabled"
        )
        self.next_button.grid(row=0, column=2, padx=(6, 0))

        detail_frame = ttk.Frame(body, padding=(16, 0))
        detail_frame.grid(row=0, column=1, sticky="nsew")
        detail_frame.columnconfigure(0, weight=1)

        self.cover_label = ttk.Label(detail_frame)
        self.cover_label.grid(row=0, column=0, pady=(0, 10))

        self.detail_text = tk.Text(
            detail_frame,
            width=50,
            height=15,
            wrap="word",
            state="disabled",
            background=self.winfo_toplevel().cget("background"),
            relief="flat",
        )
        self.detail_text.grid(row=1, column=0, sticky="nsew")

        button_frame = ttk.Frame(detail_frame)
        button_frame.grid(row=2, column=0, sticky="ew", pady=(12, 0))

        self.add_button = ttk.Button(
            button_frame,
            text="Add to Inventory",
            command=self.add_selected_to_inventory,
            state="disabled",
        )
        self.add_button.grid(row=0, column=0, sticky="w")

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def perform_search(self) -> None:
        year_value = self.year_var.get().strip()
        if year_value and not year_value.isdigit():
            messagebox.showerror(
                "Invalid year", "Please enter the year using digits only."
            )
            return

        self.current_query = OpenLibraryQuery(
            general=self.keywords_var.get().strip() or None,
            title=self.title_var.get().strip() or None,
            author=self.author_var.get().strip() or None,
            year=int(year_value) if year_value else None,
            limit=self.limit,
        )
        self.current_page = 0
        self._fetch_page()

    def _fetch_page(self) -> None:
        if not self.current_query:
            return
        offset = self.current_page * self.limit
        self._set_search_state(active=True)
        self.controller.set_status("Searching Open Library…")
        query = self.current_query
        query.limit = self.limit
        threading.Thread(
            target=self._search_thread, args=(query, offset), daemon=True
        ).start()

    def _search_thread(self, query: OpenLibraryQuery, offset: int) -> None:
        docs, total = fetch_records(query, offset=offset)
        self.after(0, lambda: self._on_search_complete(docs, total))

    def _on_search_complete(self, results: List[Dict], total: int) -> None:
        self._set_search_state(active=False)
        self.results = results
        self.total_results = total
        self.selected_index = None
        self._render_results()
        self._update_navigation()
        if results:
            start = self.current_page * self.limit + 1
            end = start + len(results) - 1
            self.controller.set_status(
                f"Showing results {start}-{end} of {total}."
            )
        else:
            self.controller.set_status("No matches found.")
        self.add_button.configure(state="disabled")
        self._show_details(None)

    def _set_search_state(self, *, active: bool) -> None:
        state = "disabled" if active else "normal"
        self.search_button.configure(state=state)
        if active:
            self.prev_button.configure(state="disabled")
            self.next_button.configure(state="disabled")

    def _render_results(self) -> None:
        needed_cards = max(len(self.results), self.limit)
        self._ensure_card_widgets(needed_cards)

        if self.no_results_label is None:
            self.no_results_label = tk.Label(
                self.results_frame,
                text="No results yet. Enter search details and click search.",
                justify="center",
                background=self.base_bg,
                foreground="#dddddd",
            )

        if not self.results:
            self.no_results_label.pack(pady=12)
            for card in self.cards:
                card["wrapper"].pack_forget()
                card["doc_key"] = None
                card["doc"] = None
            self.results_frame.update_idletasks()
            self.results_canvas.configure(scrollregion=self.results_canvas.bbox("all"))
            return

        self.no_results_label.pack_forget()

        for card in self.cards:
            card["wrapper"].pack_forget()
            card["doc_key"] = None
            card["doc"] = None

        for idx, doc in enumerate(self.results):
            card = self.cards[idx]
            card["wrapper"].pack(fill="x")
            card["doc"] = doc
            identifier = doc.get("key") or doc.get("isbn") or doc.get("title") or str(idx)
            card["doc_key"] = identifier

            frame = card["frame"]
            frame.configure(bg=self.card_default_bg)
            card["title_label"].configure(bg=self.card_default_bg, fg=self.inactive_text)
            card["authors_label"].configure(bg=self.card_default_bg, fg=self.inactive_text)
            card["year_label"].configure(bg=self.card_default_bg, fg=self.inactive_text)

            title = doc.get("title") or "Untitled"
            card["title_label"].configure(text=title)

            authors = ", ".join(doc.get("author_name", [])[:3]) or "Unknown author"
            card["authors_label"].configure(text=authors)

            year = doc.get("first_publish_year")
            card["year_label"].configure(text=f"First published: {year or 'N/A'}")

            cover_id = doc.get("cover_i")
            cover_url = (
                COVER_URL_TEMPLATE.format(cover_id=cover_id) if cover_id else doc.get("cover_url")
            )
            self._set_card_image(card, identifier, cover_url)

        self.results_frame.update_idletasks()
        self.results_canvas.configure(scrollregion=self.results_canvas.bbox("all"))
        self.results_canvas.yview_moveto(0)
        self._apply_card_styles()

    def _ensure_card_widgets(self, count: int) -> None:
        while len(self.cards) < count:
            self.cards.append(self._create_card())

    def _create_card(self) -> Dict[str, Any]:
        wrapper = tk.Frame(self.results_frame, bg=self.base_bg)
        frame = tk.Frame(
            wrapper,
            bg=self.card_default_bg,
            highlightthickness=0,
            bd=0,
            width=self.card_width,
            height=self.card_height,
        )
        frame.pack(pady=6)
        frame.pack_propagate(False)
        frame.columnconfigure(1, weight=1)

        image_label = tk.Label(
            frame,
            bg="#4a4a4a",
            fg="#dcdcdc",
            font=("Helvetica", 9, "bold"),
            text="NO\nCOVER",
            justify="center",
            width=9,
            height=5,
            padx=6,
            pady=6,
        )
        image_label.grid(row=0, column=0, rowspan=3, sticky="nsw", padx=(10, 14))

        title_label = tk.Label(
            frame,
            text="",
            font=("Helvetica", 11, "bold"),
            wraplength=220,
            justify="left",
            bg=self.card_default_bg,
            fg=self.inactive_text,
        )
        title_label.grid(row=0, column=1, sticky="w")

        authors_label = tk.Label(
            frame,
            text="",
            wraplength=220,
            justify="left",
            bg=self.card_default_bg,
            fg=self.inactive_text,
        )
        authors_label.grid(row=1, column=1, sticky="w")

        year_label = tk.Label(
            frame,
            text="",
            bg=self.card_default_bg,
            fg=self.inactive_text,
            justify="left",
        )
        year_label.grid(row=2, column=1, sticky="w")

        card = {
            "wrapper": wrapper,
            "frame": frame,
            "image_label": image_label,
            "title_label": title_label,
            "authors_label": authors_label,
            "year_label": year_label,
            "doc_key": None,
            "doc": None,
        }
        self._bind_card_events(card)
        wrapper.pack_forget()
        return card

    def _bind_card_events(self, card: Dict[str, Any]) -> None:
        def handler(_event, c=card):
            if c.get("doc_key") is None:
                return
            try:
                index = self.cards.index(c)
            except ValueError:
                return
            if index >= len(self.results):
                return
            self._select_index(index)

        for widget in (
            card["frame"],
            card["image_label"],
            card["title_label"],
            card["authors_label"],
            card["year_label"],
        ):
            widget.bind("<Button-1>", handler)

    def _set_placeholder_image(self, label: tk.Label) -> None:
        label.configure(
            image="",
            text="NO\nCOVER",
            font=("Helvetica", 9, "bold"),
            bg="#4a4a4a",
            fg="#dcdcdc",
            justify="center",
            width=9,
            height=5,
            padx=6,
            pady=6,
        )
        label.image = None

    def _set_card_image(self, card: Dict[str, Any], identifier: str, cover_url: Optional[str]) -> None:
        label = card["image_label"]
        if identifier in self.photo_cache_small:
            image = self.photo_cache_small[identifier]
            label.configure(image=image, text="")
            label.image = image
        else:
            self._set_placeholder_image(label)
            if cover_url and identifier not in self.pending_small:
                self.pending_small.add(identifier)
                threading.Thread(
                    target=self._load_cover_background,
                    args=(cover_url, identifier, "small"),
                    daemon=True,
                ).start()

    def _load_cover_background(
        self, cover_url: str, identifier: str, size: str
    ) -> None:
        max_edge = 200 if size == "small" else 600
        path = fetch_and_cache_cover(cover_url, identifier, max_edge=max_edge)

        def apply():
            if size == "small":
                self.pending_small.discard(identifier)
            else:
                self.pending_large.discard(identifier)
            if not path:
                return
            cache = self.photo_cache_small if size == "small" else self.photo_cache_large
            if identifier in cache:
                image = cache[identifier]
            else:
                dims = (80, 120) if size == "small" else (240, 360)
                image = load_thumbnail(Path(path), dims)
                if not image:
                    return
                cache[identifier] = image
            if size == "small":
                self._apply_small_image(identifier, image)
            else:
                self._apply_detail_image(identifier, image)

        self.after(0, apply)

    def _apply_small_image(self, identifier: str, image: tk.PhotoImage) -> None:
        for card in self.cards:
            if card.get("doc_key") == identifier:
                label = card["image_label"]
                label.configure(image=image, text="")
                label.image = image
        self._apply_card_styles()

    def _apply_detail_image(self, identifier: str, image: tk.PhotoImage) -> None:
        self.photo_cache_large[identifier] = image
        if self.detail_current_key == identifier:
            self.current_cover_image = image
            self.cover_label.configure(image=image, text="")

    def _bind_mousewheel(self, _event: tk.Event) -> None:
        self.results_canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.results_frame.bind("<MouseWheel>", self._on_mousewheel)
        self.results_canvas.bind("<Button-4>", self._on_mousewheel)
        self.results_canvas.bind("<Button-5>", self._on_mousewheel)
        self.results_frame.bind("<Button-4>", self._on_mousewheel)
        self.results_frame.bind("<Button-5>", self._on_mousewheel)

    def _unbind_mousewheel(self, _event: tk.Event) -> None:
        self.results_canvas.unbind("<MouseWheel>")
        self.results_frame.unbind("<MouseWheel>")
        self.results_canvas.unbind("<Button-4>")
        self.results_canvas.unbind("<Button-5>")
        self.results_frame.unbind("<Button-4>")
        self.results_frame.unbind("<Button-5>")

    def _on_mousewheel(self, event: tk.Event) -> None:
        delta = 0
        if event.delta:
            if sys.platform == "darwin":
                delta = -int(event.delta)
            else:
                delta = -int(event.delta / 120)
        elif event.num == 4:
            delta = -1
        elif event.num == 5:
            delta = 1
        if delta:
            self.results_canvas.yview_scroll(delta, "units")

    def _card_color(self, selected: bool) -> str:
        if selected:
            return self.card_selected_bg
        return self.card_default_bg

    def _select_index(self, index: int) -> None:
        if index < 0 or index >= len(self.results):
            return
        self.selected_index = index
        self._apply_card_styles()
        doc = self.results[index]
        self.add_button.configure(state="normal")
        self._show_details(doc)

    def _apply_card_styles(self) -> None:
        for idx, card in enumerate(self.cards):
            if not card.get("doc_key"):
                continue
            selected = idx == self.selected_index
            color = self._card_color(selected)
            text_color = "#111111" if selected else self.inactive_text

            frame = card["frame"]
            frame.configure(bg=color)
            card["title_label"].configure(bg=color, fg=text_color)
            card["authors_label"].configure(bg=color, fg=text_color)
            card["year_label"].configure(bg=color, fg=text_color)

            image_label = card["image_label"]
            if getattr(image_label, "image", None):
                image_label.configure(bg=color)
            else:
                image_label.configure(bg="#4a4a4a")

    def _update_navigation(self) -> None:
        if not self.current_query or self.total_results == 0:
            self.prev_button.configure(state="disabled")
            self.next_button.configure(state="disabled")
            self.page_label.configure(text="No results yet.")
            return

        total_pages = max((self.total_results - 1) // self.limit + 1, 1)
        current = self.current_page + 1

        self.prev_button.configure(state="normal" if self.current_page > 0 else "disabled")
        more = (self.current_page + 1) * self.limit < self.total_results
        self.next_button.configure(state="normal" if more else "disabled")

        start = self.current_page * self.limit + 1
        end = start + len(self.results) - 1 if self.results else start
        self.page_label.configure(
            text=f"Results {start}-{end} of {self.total_results} (Page {current}/{total_pages})"
        )

    def prev_page(self) -> None:
        if self.current_page == 0:
            return
        self.current_page -= 1
        self._fetch_page()

    def next_page(self) -> None:
        if not self.current_query:
            return
        if (self.current_page + 1) * self.limit >= self.total_results:
            return
        self.current_page += 1
        self._fetch_page()

    def _show_details(self, doc: Optional[Dict]) -> None:
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        self.cover_label.configure(image="", text="", foreground="#888888")
        self.current_cover_image = None
        self.detail_current_key = None

        if not doc:
            self.detail_text.insert("end", "Select a result to see its details here.")
            self.detail_text.configure(state="disabled")
            return

        lines = [
            f"Title: {doc.get('title', 'Untitled')}",
            f"Author(s): {', '.join(doc.get('author_name', [])) or 'Unknown'}",
        ]
        if doc.get("first_publish_year"):
            lines.append(f"First Publish Year: {doc.get('first_publish_year')}")
        if doc.get("publisher"):
            lines.append(f"Publisher: {', '.join(doc.get('publisher', [])[:2])}")
        if doc.get("subject"):
            lines.append(f"Subjects: {', '.join(doc.get('subject', [])[:6])}")
        lines.append(f"Open Library Key: {doc.get('key')}")

        self.detail_text.insert("end", "\n".join(lines))
        self.detail_text.configure(state="disabled")

        identifier = doc.get("key") or doc.get("isbn") or doc.get("title")
        self.detail_current_key = identifier
        cover_id = doc.get("cover_i")
        cover_url = (
            COVER_URL_TEMPLATE.format(cover_id=cover_id) if cover_id else doc.get("cover_url")
        )

        if identifier and identifier in self.photo_cache_large:
            image = self.photo_cache_large[identifier]
            self.current_cover_image = image
            self.cover_label.configure(image=image, text="")
        elif cover_url and identifier:
            self.cover_label.configure(text="Loading cover…", foreground="#888888")
            if identifier not in self.pending_large:
                self.pending_large.add(identifier)
                threading.Thread(
                    target=self._load_cover_background,
                    args=(cover_url, identifier, "large"),
                    daemon=True,
                ).start()
        else:
            self.cover_label.configure(text="No cover available", foreground="#888888")

    def add_selected_to_inventory(self) -> None:
        if self.selected_index is None:
            return
        doc = self.results[self.selected_index]
        self.controller.add_book_from_doc(doc)


# --------------------------------------------------------------------------- #
# Inventory panel
# --------------------------------------------------------------------------- #
class InventoryFrame(ttk.Frame):
    def __init__(self, master: ttk.Notebook, controller: "MainApplication"):
        super().__init__(master, padding=12)
        self.controller = controller
        self.books: List[Dict] = []
        self.current_cover_image: Optional[tk.PhotoImage] = None
        self._build_ui()

    def _build_ui(self) -> None:
        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Search inventory:").grid(row=0, column=0, sticky="w")
        self.search_var = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self.search_var)
        entry.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self.search_var.trace_add("write", lambda *_: self.refresh_books())

        self.refresh_button = ttk.Button(
            top, text="Refresh", command=self.refresh_books, width=12
        )
        self.refresh_button.grid(row=0, column=2, padx=(8, 0))

        body = ttk.Frame(self)
        body.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        columns = ("authors", "year", "shelf", "slot")
        self.tree = ttk.Treeview(
            body, columns=columns, show="headings", selectmode="browse"
        )
        self.tree.heading("authors", text="Author(s)")
        self.tree.heading("year", text="First Published")
        self.tree.heading("shelf", text="Shelf")
        self.tree.heading("slot", text="Slot")
        self.tree.column("authors", width=240, anchor="w")
        self.tree.column("year", width=120, anchor="center")
        self.tree.column("shelf", width=150, anchor="w")
        self.tree.column("slot", width=80, anchor="center")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self._on_select_book)

        tree_scroll = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        tree_scroll.grid(row=0, column=0, sticky="nse")
        self.tree.configure(yscrollcommand=tree_scroll.set)

        detail = ttk.Frame(body, padding=(16, 0))
        detail.grid(row=0, column=1, sticky="nsew")
        detail.columnconfigure(0, weight=1)

        self.cover_label = ttk.Label(detail)
        self.cover_label.grid(row=0, column=0, pady=(0, 12))

        self.info_text = tk.Text(
            detail,
            height=12,
            wrap="word",
            state="disabled",
            background=self.winfo_toplevel().cget("background"),
            relief="flat",
        )
        self.info_text.grid(row=1, column=0, sticky="nsew")

        button_frame = ttk.Frame(detail)
        button_frame.grid(row=2, column=0, sticky="ew", pady=(12, 0))

        self.place_button = ttk.Button(
            button_frame,
            text="Place / Move…",
            command=self._place_selected,
            state="disabled",
        )
        self.place_button.grid(row=0, column=0, padx=(0, 6))

        self.remove_button = ttk.Button(
            button_frame,
            text="Remove Placement",
            command=self._remove_placement,
            state="disabled",
        )
        self.remove_button.grid(row=0, column=1, padx=(0, 6))

        self.delete_button = ttk.Button(
            button_frame,
            text="Delete Book",
            command=self._delete_book,
            state="disabled",
        )
        self.delete_button.grid(row=0, column=2)

    # ------------------------------------------------------------------
    def refresh_books(self) -> None:
        term = self.search_var.get().strip()
        self.books = self.controller.store.list_books(term)

        current_selection = self.tree.selection()
        selected_id = int(current_selection[0]) if current_selection else None

        self.tree.delete(*self.tree.get_children())
        for book in self.books:
            book_id = book["id"]
            authors = book.get("authors") or ""
            shelf = book.get("shelf_name") or ""
            slot = book.get("slot_index") or ""
            year = book.get("first_publish_year") or ""
            self.tree.insert(
                "",
                "end",
                iid=str(book_id),
                values=(authors, year, shelf, slot),
            )

        if selected_id and str(selected_id) in self.tree.get_children(""):
            self.tree.selection_set(str(selected_id))
            self.tree.focus(str(selected_id))
        else:
            self._show_book(None)

    def _on_select_book(self, _event: tk.Event) -> None:
        selection = self.tree.selection()
        if not selection:
            self._show_book(None)
            return
        book_id = int(selection[0])
        book = next((b for b in self.books if b["id"] == book_id), None)
        self._show_book(book)
        if book:
            self.controller.visual_frame.highlight_book(book_id)

    def _show_book(self, book: Optional[Dict]) -> None:
        self.info_text.configure(state="normal")
        self.info_text.delete("1.0", "end")
        self.cover_label.configure(image="", text="")
        self.current_cover_image = None
        self.place_button.configure(state="disabled")
        self.remove_button.configure(state="disabled")
        self.delete_button.configure(state="disabled")

        if not book:
            self.info_text.insert("end", "Select a book to see its details.")
            self.info_text.configure(state="disabled")
            return

        lines = [
            f"Title: {book.get('title')}",
            f"Subtitle: {book.get('subtitle') or '—'}",
            f"Author(s): {book.get('authors') or 'Unknown'}",
        ]
        if book.get("first_publish_year"):
            lines.append(f"First Publish Year: {book.get('first_publish_year')}")
        if book.get("publisher"):
            lines.append(f"Publisher: {book.get('publisher')}")
        if book.get("isbn"):
            lines.append(f"ISBN: {book.get('isbn')}")
        if book.get("subjects"):
            lines.append(f"Subjects: {book.get('subjects')}")
        lines.append(f"Open Library Key: {book.get('openlibrary_key')}")

        placement = self.controller.store.get_placement(book["id"])
        if placement:
            lines.append(
                f"Location: {placement.shelf_name} → {placement.row_name} (Slot {placement.slot_index})"
            )
            self.remove_button.configure(state="normal")
        else:
            lines.append("Location: Not yet placed.")

        self.info_text.insert("end", "\n".join(lines))
        self.info_text.configure(state="disabled")

        cover_path = book.get("cover_path")
        if cover_path:
            image = load_thumbnail(Path(cover_path), size=(180, 250))
            if image:
                self.current_cover_image = image
                self.cover_label.configure(image=image)
        if not self.current_cover_image:
            self.cover_label.configure(text="No cover available", foreground="#888888")

        self.place_button.configure(state="normal")
        self.delete_button.configure(state="normal")

    def _place_selected(self) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        book_id = int(selection[0])
        self.controller.open_placement_dialog(book_id)

    def _remove_placement(self) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        book_id = int(selection[0])
        if not messagebox.askyesno(
            "Remove placement",
            "Remove this book from its shelf placement?",
            parent=self,
        ):
            return
        try:
            self.controller.store.remove_placement(book_id)
        except Exception as error:
            messagebox.showerror("Error", str(error), parent=self)
            return
        self.controller.set_status("Placement removed.")
        self.refresh_books()
        self.controller.visual_frame.refresh()

    def _delete_book(self) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        book_id = int(selection[0])
        book = next((b for b in self.books if b["id"] == book_id), None)
        if not book:
            return
        if not messagebox.askyesno(
            "Delete book",
            f"Delete '{book.get('title')}' from the inventory?",
            parent=self,
        ):
            return
        self.controller.store.delete_book(book_id)
        self.controller.set_status(f"Deleted '{book.get('title')}'.")
        self.refresh_books()
        self.controller.visual_frame.refresh()

    def select_book(self, book_id: int) -> None:
        if str(book_id) in self.tree.get_children(""):
            self.tree.selection_set(str(book_id))
            self.tree.focus(str(book_id))
            self.tree.see(str(book_id))
        else:
            self.refresh_books()
            if str(book_id) in self.tree.get_children(""):
                self.tree.selection_set(str(book_id))
                self.tree.focus(str(book_id))


# --------------------------------------------------------------------------- #
# Shelf management
# --------------------------------------------------------------------------- #
class ShelfFrame(ttk.Frame):
    def __init__(self, master: ttk.Notebook, controller: "MainApplication"):
        super().__init__(master, padding=12)
        self.controller = controller
        self.shelves: List[Dict] = []
        self.rows: List[Dict] = []
        self.selected_shelf_id: Optional[int] = None
        self._build_ui()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        ttk.Label(self, text="Shelves").grid(row=0, column=0, sticky="w")

        shelf_frame = ttk.Frame(self)
        shelf_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        shelf_frame.columnconfigure(0, weight=1)
        shelf_frame.rowconfigure(0, weight=1)

        self.shelf_tree = ttk.Treeview(
            shelf_frame,
            columns=("rows", "capacity"),
            show="headings",
            selectmode="browse",
        )
        self.shelf_tree.heading("rows", text="Rows")
        self.shelf_tree.heading("capacity", text="Capacity")
        self.shelf_tree.column("rows", width=80, anchor="center")
        self.shelf_tree.column("capacity", width=100, anchor="center")
        self.shelf_tree.grid(row=0, column=0, sticky="nsew")
        self.shelf_tree.bind("<<TreeviewSelect>>", self._on_select_shelf)

        shelf_scroll = ttk.Scrollbar(
            shelf_frame, orient="vertical", command=self.shelf_tree.yview
        )
        shelf_scroll.grid(row=0, column=0, sticky="nse")
        self.shelf_tree.configure(yscrollcommand=shelf_scroll.set)

        shelf_buttons = ttk.Frame(shelf_frame)
        shelf_buttons.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(shelf_buttons, text="Add Shelf", command=self._add_shelf).grid(
            row=0, column=0, padx=(0, 6)
        )
        ttk.Button(shelf_buttons, text="Rename Shelf", command=self._rename_shelf).grid(
            row=0, column=1, padx=(0, 6)
        )
        ttk.Button(shelf_buttons, text="Delete Shelf", command=self._delete_shelf).grid(
            row=0, column=2
        )

        ttk.Label(self, text="Rows").grid(row=0, column=1, sticky="w")
        row_frame = ttk.Frame(self)
        row_frame.grid(row=1, column=1, sticky="nsew")
        row_frame.columnconfigure(0, weight=1)
        row_frame.rowconfigure(0, weight=1)

        self.row_tree = ttk.Treeview(
            row_frame,
            columns=("position", "name", "capacity", "used"),
            show="headings",
            selectmode="browse",
        )
        self.row_tree.heading("position", text="#")
        self.row_tree.heading("name", text="Name")
        self.row_tree.heading("capacity", text="Capacity")
        self.row_tree.heading("used", text="Used")
        self.row_tree.column("position", width=50, anchor="center")
        self.row_tree.column("name", width=160, anchor="w")
        self.row_tree.column("capacity", width=90, anchor="center")
        self.row_tree.column("used", width=90, anchor="center")
        self.row_tree.grid(row=0, column=0, sticky="nsew")

        row_scroll = ttk.Scrollbar(
            row_frame, orient="vertical", command=self.row_tree.yview
        )
        row_scroll.grid(row=0, column=0, sticky="nse")
        self.row_tree.configure(yscrollcommand=row_scroll.set)

        row_buttons = ttk.Frame(row_frame)
        row_buttons.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(row_buttons, text="Add Row", command=self._add_row).grid(
            row=0, column=0, padx=(0, 6)
        )
        ttk.Button(row_buttons, text="Edit Row", command=self._edit_row).grid(
            row=0, column=1, padx=(0, 6)
        )
        ttk.Button(row_buttons, text="Delete Row", command=self._delete_row).grid(
            row=0, column=2
        )

    def refresh(self) -> None:
        self.shelves = self.controller.store.list_shelves()
        self.shelf_tree.delete(*self.shelf_tree.get_children())
        for shelf in self.shelves:
            self.shelf_tree.insert(
                "",
                "end",
                iid=str(shelf["id"]),
                values=(shelf["row_count"], shelf["capacity"]),
            )
        if self.shelves:
            first_shelf_id = self.shelves[0]["id"]
            self.shelf_tree.selection_set(str(first_shelf_id))
            self._load_rows(first_shelf_id)
        else:
            self.row_tree.delete(*self.row_tree.get_children())
            self.selected_shelf_id = None

    def _on_select_shelf(self, _event: tk.Event) -> None:
        selection = self.shelf_tree.selection()
        if not selection:
            self.selected_shelf_id = None
            self.row_tree.delete(*self.row_tree.get_children())
            return
        shelf_id = int(selection[0])
        self._load_rows(shelf_id)

    def _load_rows(self, shelf_id: int) -> None:
        self.selected_shelf_id = shelf_id
        self.rows = self.controller.store.list_rows(shelf_id)
        self.row_tree.delete(*self.row_tree.get_children())
        for row in self.rows:
            name = row.get("name") or f"Row {row['position']}"
            self.row_tree.insert(
                "",
                "end",
                iid=str(row["id"]),
                values=(row["position"], name, row["capacity"], row["used"]),
            )

    def _add_shelf(self) -> None:
        name = simpledialog.askstring("Create shelf", "Shelf name:", parent=self)
        if not name:
            return
        description = simpledialog.askstring(
            "Create shelf", "Optional description:", parent=self
        )
        try:
            self.controller.store.create_shelf(name, description or "")
        except Exception as error:
            messagebox.showerror("Error", str(error), parent=self)
            return
        self.refresh()
        self.controller.visual_frame.refresh()
        self.controller.set_status(f"Created shelf '{name}'.")

    def _rename_shelf(self) -> None:
        selection = self.shelf_tree.selection()
        if not selection:
            return
        shelf_id = int(selection[0])
        shelf = next((s for s in self.shelves if s["id"] == shelf_id), None)
        if not shelf:
            return
        name = simpledialog.askstring(
            "Rename shelf", "New name:", initialvalue=shelf["name"], parent=self
        )
        if not name:
            return
        description = simpledialog.askstring(
            "Rename shelf",
            "Description:",
            initialvalue=shelf.get("description") or "",
            parent=self,
        )
        try:
            self.controller.store.update_shelf(shelf_id, name=name, description=description or "")
        except Exception as error:
            messagebox.showerror("Error", str(error), parent=self)
            return
        self.refresh()
        self.controller.visual_frame.refresh()
        self.controller.set_status(f"Renamed shelf to '{name}'.")

    def _delete_shelf(self) -> None:
        selection = self.shelf_tree.selection()
        if not selection:
            return
        shelf_id = int(selection[0])
        shelf = next((s for s in self.shelves if s["id"] == shelf_id), None)
        if not shelf:
            return
        if not messagebox.askyesno(
            "Delete shelf",
            f"Delete the shelf '{shelf['name']}'? Rows must be empty.",
            parent=self,
        ):
            return
        try:
            self.controller.store.delete_shelf(shelf_id)
        except Exception as error:
            messagebox.showerror("Error", str(error), parent=self)
            return
        self.refresh()
        self.controller.visual_frame.refresh()
        self.controller.set_status(f"Deleted shelf '{shelf['name']}'.")

    def _add_row(self) -> None:
        if self.selected_shelf_id is None:
            messagebox.showinfo("Select shelf", "Select a shelf first.", parent=self)
            return
        name = simpledialog.askstring("Row name", "Optional row name:", parent=self)
        capacity = simpledialog.askinteger(
            "Row capacity", "How many books fit on this row?", initialvalue=10, parent=self
        )
        if not capacity:
            return
        try:
            self.controller.store.create_row(
                self.selected_shelf_id, name=name, capacity=capacity
            )
        except Exception as error:
            messagebox.showerror("Error", str(error), parent=self)
            return
        self._load_rows(self.selected_shelf_id)
        self.controller.visual_frame.refresh()
        self.controller.set_status("Row created.")

    def _edit_row(self) -> None:
        selection = self.row_tree.selection()
        if not selection:
            return
        row_id = int(selection[0])
        row = next((r for r in self.rows if r["id"] == row_id), None)
        if not row:
            return
        name = simpledialog.askstring(
            "Row name",
            "Row name:",
            initialvalue=row.get("name") or "",
            parent=self,
        )
        capacity = simpledialog.askinteger(
            "Row capacity",
            "Capacity:",
            initialvalue=row.get("capacity"),
            parent=self,
        )
        if not capacity:
            return
        try:
            self.controller.store.update_row(row_id, name=name, capacity=capacity)
        except Exception as error:
            messagebox.showerror("Error", str(error), parent=self)
            return
        if self.selected_shelf_id:
            self._load_rows(self.selected_shelf_id)
        self.controller.visual_frame.refresh()
        self.controller.set_status("Row updated.")

    def _delete_row(self) -> None:
        selection = self.row_tree.selection()
        if not selection:
            return
        row_id = int(selection[0])
        row = next((r for r in self.rows if r["id"] == row_id), None)
        if not row:
            return
        if not messagebox.askyesno(
            "Delete row",
            "Delete this row? It must have no books.",
            parent=self,
        ):
            return
        try:
            self.controller.store.delete_row(row_id)
        except Exception as error:
            messagebox.showerror("Error", str(error), parent=self)
            return
        if self.selected_shelf_id:
            self._load_rows(self.selected_shelf_id)
        self.controller.visual_frame.refresh()
        self.controller.set_status("Row deleted.")


# --------------------------------------------------------------------------- #
# Visual bookshelf
# --------------------------------------------------------------------------- #
class VisualShelfFrame(ttk.Frame):
    def __init__(self, master: ttk.Notebook, controller: "MainApplication"):
        super().__init__(master, padding=12)
        self.controller = controller
        self.canvas = tk.Canvas(self, background="#f5f3f0")
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.v_scroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.v_scroll.grid(row=0, column=1, sticky="ns")
        self.h_scroll = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        self.h_scroll.grid(row=1, column=0, sticky="ew")

        self.canvas.configure(
            yscrollcommand=self.v_scroll.set, xscrollcommand=self.h_scroll.set
        )

        self.canvas_images: List[tk.PhotoImage] = []
        self.book_rectangles: Dict[int, int] = {}
        self.highlight_rect: Optional[int] = None

        self.canvas.bind("<Button-1>", self._on_click)

    def refresh(self) -> None:
        structure = self.controller.store.get_shelf_structure()
        self.canvas.delete("all")
        self.canvas_images.clear()
        self.book_rectangles.clear()
        self.highlight_rect = None

        x_margin = 40
        y_margin = 40
        slot_width = 90
        slot_height = 130
        gap = 12
        y = y_margin
        max_width = 0

        for block in structure:
            shelf = block["shelf"]
            rows = block["rows"]
            self.canvas.create_text(
                x_margin,
                y,
                anchor="nw",
                text=shelf["name"],
                font=("Helvetica", 14, "bold"),
            )
            y += 30

            for entry in rows:
                row = entry["row"]
                placements = entry["placements"]
                capacity = row["capacity"]

                row_name = row.get("name") or f"Row {row['position']}"
                self.canvas.create_text(
                    x_margin,
                    y,
                    anchor="nw",
                    text=row_name,
                    font=("Helvetica", 11, "italic"),
                )
                y += 22

                row_width = capacity * slot_width + (capacity - 1) * gap
                max_width = max(max_width, row_width + x_margin * 2)

                row_top = y
                row_bottom = y + slot_height + 20
                self.canvas.create_rectangle(
                    x_margin - 10,
                    row_top - 10,
                    x_margin - 10 + row_width + 20,
                    row_bottom,
                    outline="#bfbab0",
                    width=2,
                    fill="#ece7e0",
                )

                placement_map = {p["slot_index"]: p for p in placements}
                for slot in range(1, capacity + 1):
                    slot_x = x_margin + (slot - 1) * (slot_width + gap)
                    slot_rect = self.canvas.create_rectangle(
                        slot_x,
                        row_top,
                        slot_x + slot_width,
                        row_top + slot_height,
                        outline="#d4cec4",
                        width=1,
                        fill="#ffffff",
                    )

                    placement = placement_map.get(slot)
                    if placement:
                        cover_path_value = placement.get("cover_path")
                        image = (
                            load_thumbnail(Path(cover_path_value), (slot_width - 12, slot_height - 20))
                            if cover_path_value
                            else None
                        )
                        if image:
                            image_id = self.canvas.create_image(
                                slot_x + slot_width / 2,
                                row_top + slot_height / 2,
                                image=image,
                            )
                            self.canvas_images.append(image)
                            self.canvas.tag_bind(
                                image_id,
                                "<Button-1>",
                                lambda _event, book_id=placement["book_id"]: self._notify_selection(book_id),
                            )
                            self.book_rectangles[placement["book_id"]] = slot_rect
                        else:
                            title = truncate(placement["title"] or "", 20)
                            self.canvas.create_text(
                                slot_x + slot_width / 2,
                                row_top + slot_height / 2,
                                text=title,
                                width=slot_width - 10,
                            )
                        self.canvas.tag_bind(
                            slot_rect,
                            "<Button-1>",
                            lambda _event, book_id=placement["book_id"]: self._notify_selection(book_id),
                        )
                        self.book_rectangles[placement["book_id"]] = slot_rect
                    else:
                        self.canvas.create_text(
                            slot_x + slot_width / 2,
                            row_top + slot_height / 2,
                            text=str(slot),
                            fill="#b3aea4",
                        )

                y += slot_height + 40

            y += 30

        scroll_height = max(y, self.winfo_height())
        scroll_width = max(max_width, self.winfo_width())
        self.canvas.configure(scrollregion=(0, 0, scroll_width, scroll_height))

    def _on_click(self, event: tk.Event) -> None:
        item = self.canvas.find_closest(event.x, event.y)
        if not item:
            return
        for book_id, rect in self.book_rectangles.items():
            if rect == item[0]:
                self._notify_selection(book_id)
                return

    def _notify_selection(self, book_id: int) -> None:
        self.highlight_book(book_id)
        self.controller.focus_on_book(book_id)

    def highlight_book(self, book_id: Optional[int]) -> None:
        if self.highlight_rect:
            self.canvas.itemconfigure(self.highlight_rect, outline="#d4cec4", width=1)
            self.highlight_rect = None

        if book_id and book_id in self.book_rectangles:
            rect_id = self.book_rectangles[book_id]
            self.canvas.itemconfigure(rect_id, outline="#c32e26", width=3)
            self.highlight_rect = rect_id
            self.canvas.see(rect_id)


# --------------------------------------------------------------------------- #
# Placement dialog
# --------------------------------------------------------------------------- #
class PlacementDialog(tk.Toplevel):
    def __init__(self, controller: "MainApplication", book_id: int, title: str):
        super().__init__(controller)
        self.controller = controller
        self.book_id = book_id
        self.title(f"Place '{truncate(title, 40)}'")
        self.resizable(False, False)
        self.grab_set()

        self.shelves = self.controller.store.list_shelves()
        self.rows = self.controller.store.list_rows_with_shelves()

        ttk.Label(self, text="Shelf:").grid(row=0, column=0, sticky="w", padx=12, pady=(12, 4))
        self.shelf_var = tk.StringVar()
        shelf_names = [s["name"] for s in self.shelves]
        self.shelf_combo = ttk.Combobox(self, values=shelf_names, textvariable=self.shelf_var, state="readonly", width=30)
        self.shelf_combo.grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=(12, 4))
        self.shelf_combo.bind("<<ComboboxSelected>>", lambda *_: self._populate_rows())

        ttk.Label(self, text="Row:").grid(row=1, column=0, sticky="w", padx=12, pady=4)
        self.row_var = tk.StringVar()
        self.row_combo = ttk.Combobox(self, values=[], textvariable=self.row_var, state="readonly", width=30)
        self.row_combo.grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=4)
        self.row_combo.bind("<<ComboboxSelected>>", lambda *_: self._update_slot_range())

        ttk.Label(self, text="Slot number:").grid(row=2, column=0, sticky="w", padx=12, pady=4)
        self.slot_var = tk.IntVar(value=1)
        self.slot_spin = tk.Spinbox(self, from_=1, to=1, textvariable=self.slot_var, width=6)
        self.slot_spin.grid(row=2, column=1, sticky="w", padx=(0, 12), pady=4)

        button_frame = ttk.Frame(self)
        button_frame.grid(row=3, column=0, columnspan=2, pady=(12, 12))
        ttk.Button(button_frame, text="Cancel", command=self.destroy).grid(row=0, column=0, padx=4)
        ttk.Button(button_frame, text="Save Placement", command=self._save).grid(row=0, column=1, padx=4)

        if shelf_names:
            self.shelf_combo.current(0)
            self._populate_rows()
        else:
            messagebox.showinfo(
                "No shelves",
                "Create a shelf and row first from the Shelves tab.",
                parent=self,
            )
            self.destroy()

    def _populate_rows(self) -> None:
        shelf_name = self.shelf_var.get()
        shelf = next((s for s in self.shelves if s["name"] == shelf_name), None)
        if not shelf:
            self.row_combo.configure(values=[])
            return
        rows = self.controller.store.list_rows(shelf["id"])
        self.active_rows = rows
        row_labels = [
            (row.get("name") or f"Row {row['position']}", row["id"]) for row in rows
        ]
        self.row_combo.configure(values=[label for label, _ in row_labels])
        if row_labels:
            self.row_combo.current(0)
        self._update_slot_range()

    def _update_slot_range(self) -> None:
        if not hasattr(self, "active_rows"):
            return
        row_label = self.row_var.get()
        row = next(
            (
                r
                for r in self.active_rows
                if (r.get("name") or f"Row {r['position']}") == row_label
            ),
            self.active_rows[0] if self.active_rows else None,
        )
        if not row:
            return
        capacity = row["capacity"]
        self.slot_spin.configure(to=capacity)
        self.slot_var.set(1)

    def _save(self) -> None:
        shelf_name = self.shelf_var.get()
        row_name = self.row_var.get()
        if not shelf_name or not row_name:
            messagebox.showerror("Placement", "Select shelf and row.", parent=self)
            return
        shelf = next((s for s in self.shelves if s["name"] == shelf_name), None)
        if not shelf:
            messagebox.showerror("Placement", "Invalid shelf selection.", parent=self)
            return
        row = next(
            (
                r
                for r in self.controller.store.list_rows(shelf["id"])
                if (r.get("name") or f"Row {r['position']}") == row_name
            ),
            None,
        )
        if not row:
            messagebox.showerror("Placement", "Row not found.", parent=self)
            return
        slot_index = self.slot_var.get()
        try:
            self.controller.store.set_placement(self.book_id, row["id"], slot_index)
        except Exception as error:
            messagebox.showerror("Placement error", str(error), parent=self)
            return
        self.controller.set_status("Placement saved.")
        self.controller.after(0, self.controller.refresh_all)
        self.destroy()


# --------------------------------------------------------------------------- #
# Main application
# --------------------------------------------------------------------------- #
class MainApplication(tk.Tk):
    def __init__(self, db_path: Optional[Path] = None):
        super().__init__()
        self.title("Mom's Library")
        self.geometry("1280x820")
        self.minsize(1100, 720)

        self.store = InventoryStore(db_path)
        self.status_var = tk.StringVar(value="Ready.")

        self._build_ui()

    def _build_ui(self) -> None:
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)

        self.search_frame = SearchFrame(notebook, self)
        notebook.add(self.search_frame, text="Search & Add")

        self.inventory_frame = InventoryFrame(notebook, self)
        notebook.add(self.inventory_frame, text="Inventory")

        self.shelf_frame = ShelfFrame(notebook, self)
        notebook.add(self.shelf_frame, text="Shelves")

        self.visual_frame = VisualShelfFrame(notebook, self)
        notebook.add(self.visual_frame, text="Virtual Bookshelf")

        status_bar = ttk.Label(self, textvariable=self.status_var, anchor="w", padding=(8, 4))
        status_bar.pack(side="bottom", fill="x")

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.refresh_all()

    # ------------------------------------------------------------------
    def set_status(self, message: str) -> None:
        self.status_var.set(message)

    def refresh_all(self) -> None:
        self.inventory_frame.refresh_books()
        self.shelf_frame.refresh()
        self.visual_frame.refresh()

    def add_book_from_doc(self, doc: Dict) -> None:
        record = build_record(doc)
        identifier = (
            record.get("openlibrary_key")
            or record.get("isbn")
            or record.get("title")
            or "cover"
        )
        cover_path = fetch_and_cache_cover(record.get("cover_url"), identifier)
        book_id, created = self.store.add_or_update_book(
            record, cover_path=Path(cover_path) if cover_path else None
        )
        self.refresh_all()
        if created:
            self.set_status(f"Added '{record['title']}' to the inventory.")
        else:
            self.set_status(f"Updated stored record for '{record['title']}'.")
        should_place = messagebox.askyesno(
            "Place book?",
            "Would you like to place this book on a shelf now?",
            parent=self,
        )
        if should_place:
            self.open_placement_dialog(book_id, record["title"])

    def open_placement_dialog(self, book_id: int, title: Optional[str] = None) -> None:
        book = self.store.get_book(book_id)
        if not book:
            messagebox.showerror("Placement", "Book not found.", parent=self)
            return
        PlacementDialog(self, book_id, title or book["title"])

    def focus_on_book(self, book_id: int) -> None:
        self.inventory_frame.select_book(book_id)

    def on_close(self) -> None:
        try:
            self.store.close()
        finally:
            self.destroy()


if __name__ == "__main__":
    app = MainApplication()
    app.mainloop()

