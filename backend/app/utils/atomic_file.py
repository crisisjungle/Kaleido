"""
Atomic file helpers for file-backed state.

These helpers keep the current upload-directory layout, but avoid exposing
partially written JSON/text/CSV files to realtime readers.
"""

from __future__ import annotations

import csv
import json
import os
import tempfile
from typing import Any, Callable, Dict, Iterable, List, Optional, TypeVar


T = TypeVar("T")
_MISSING = object()


class AtomicFileError(Exception):
    """Raised when a state file cannot be read or written safely."""


def _ensure_parent(path: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def _atomic_write(path: str, writer: Callable[[Any], None], *, newline: Optional[str] = None) -> None:
    _ensure_parent(path)
    directory = os.path.dirname(os.path.abspath(path)) or "."
    basename = os.path.basename(path)
    temp_path = ""
    fd = -1
    try:
        fd, temp_path = tempfile.mkstemp(prefix=f".{basename}.", suffix=".tmp", dir=directory, text=True)
        with os.fdopen(fd, "w", encoding="utf-8", newline=newline) as handle:
            fd = -1
            writer(handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception as exc:
        if fd != -1:
            try:
                os.close(fd)
            except OSError:
                pass
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass
        raise AtomicFileError(f"Failed to write file atomically: {path}") from exc


def write_json_file(path: str, payload: Any, *, indent: int = 2) -> None:
    def writer(handle) -> None:
        json.dump(payload, handle, ensure_ascii=False, indent=indent)

    _atomic_write(path, writer)


def read_json_file(path: str, default: Any = _MISSING) -> Any:
    if not os.path.exists(path):
        if default is not _MISSING:
            return default
        raise FileNotFoundError(path)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception as exc:
        if default is not _MISSING:
            return default
        raise AtomicFileError(f"Failed to read JSON file: {path}") from exc


def write_text_file(path: str, text: str) -> None:
    _atomic_write(path, lambda handle: handle.write(text or ""))


def read_text_file(path: str, default: str = "") -> str:
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except Exception:
        return default


def write_csv_file(path: str, rows: Iterable[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> None:
    rows = list(rows)
    if fieldnames is None:
        fieldnames = []
        for row in rows:
            for key in row.keys():
                if key not in fieldnames:
                    fieldnames.append(key)

    def writer(handle) -> None:
        csv_writer = csv.DictWriter(handle, fieldnames=fieldnames)
        csv_writer.writeheader()
        for row in rows:
            csv_writer.writerow(row)

    _atomic_write(path, writer, newline="")
