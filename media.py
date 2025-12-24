from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Optional, Tuple

import requests
from PIL import Image, ImageTk, UnidentifiedImageError

APP_DIR = Path.home() / ".moms_books"
COVERS_DIR = APP_DIR / "covers"
COVERS_DIR.mkdir(parents=True, exist_ok=True)


def _safe_name(identifier: str) -> str:
    return hashlib.sha1(identifier.encode("utf-8")).hexdigest()


def cached_cover_path(identifier: str, max_edge: Optional[int]) -> Path:
    if max_edge:
        safe_name = _safe_name(f"{identifier}:{max_edge}")
    else:
        safe_name = _safe_name(f"{identifier}:orig")
    return COVERS_DIR / f"{safe_name}.jpg"


def fetch_and_cache_cover(
    cover_url: Optional[str],
    identifier: str,
    *,
    max_edge: Optional[int] = None,
) -> Optional[Path]:
    """Download a cover image (if any) and save it to the cache directory."""
    if not cover_url:
        return None

    target_path = cached_cover_path(identifier, max_edge)

    if target_path.exists():
        return target_path

    try:
        response = requests.get(cover_url, timeout=15)
        response.raise_for_status()
    except Exception:
        return None

    if max_edge:
        try:
            image = Image.open(io.BytesIO(response.content))
            image.thumbnail((max_edge, max_edge), Image.LANCZOS)
            image.save(target_path)
        except (UnidentifiedImageError, OSError):
            try:
                with open(target_path, "wb") as handle:
                    handle.write(response.content)
            except OSError:
                return None
    else:
        try:
            with open(target_path, "wb") as handle:
                handle.write(response.content)
        except OSError:
            return None

    return target_path


def load_thumbnail(path: Path, size: Tuple[int, int]) -> Optional[ImageTk.PhotoImage]:
    """Return a resized PhotoImage for Tkinter."""
    if not path.exists():
        return None
    try:
        image = Image.open(path)
    except (UnidentifiedImageError, OSError):
        return None
    image.thumbnail(size, Image.LANCZOS)
    return ImageTk.PhotoImage(image)

