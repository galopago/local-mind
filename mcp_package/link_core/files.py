"""Small filesystem write helpers for Link's local Markdown store."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def _fsync_directory(path: Path) -> None:
    """Best-effort directory fsync so an atomic rename survives local crashes."""
    if os.name == "nt":
        return
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write bytes via temp file + os.replace to avoid partial target files."""
    target = path.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_name = ""
    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        tmp_name = handle.name
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(tmp_name, target)
        _fsync_directory(target.parent)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    atomic_write_bytes(path, text.encode(encoding))


def atomic_write_json(path: Path, payload: Any, *, indent: int = 2, trailing_newline: bool = True) -> None:
    text = json.dumps(payload, indent=indent)
    if trailing_newline:
        text += "\n"
    atomic_write_text(path, text)


def append_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Append one complete text block and fsync it for local audit trails."""
    target = path.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding=encoding) as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
