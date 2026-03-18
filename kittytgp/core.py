from __future__ import annotations

import argparse
import base64
import math
import os
import secrets
import shutil
import struct
import subprocess
import sys
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import BinaryIO

try:
    import fcntl
    import termios
except ImportError:  # pragma: no cover
    fcntl = None
    termios = None

PLACEHOLDER = "\U0010EEEE"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
DEFAULT_CHUNK_SIZE = 4096


@dataclass(frozen=True)
class TerminalGeometry:
    cols: int
    rows: int
    cell_width_px: int
    cell_height_px: int


def _load_diacritics() -> tuple[str, ...]:
    text = resources.files("kittytgp").joinpath("rowcolumn_diacritics.txt").read_text(encoding="utf-8")
    out: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.append(chr(int(line.split(";", 1)[0], 16)))
    if not out:
        raise RuntimeError("Could not load kitty row/column diacritics")
    return tuple(out)


DIACRITICS = _load_diacritics()


def _parse_png_size(data: bytes) -> tuple[int, int]:
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("input is not a PNG file")
    if len(data) < 24:
        raise ValueError("PNG is too short")
    ihdr_len = struct.unpack(">I", data[8:12])[0]
    if ihdr_len != 13 or data[12:16] != b"IHDR":
        raise ValueError("PNG does not start with an IHDR chunk")
    width, height = struct.unpack(">II", data[16:24])
    if width <= 0 or height <= 0:
        raise ValueError("PNG has invalid dimensions")
    return width, height


def _read_png(path_or_bytes: str | os.PathLike[str] | bytes) -> tuple[bytes, int, int]:
    if isinstance(path_or_bytes, bytes):
        data = path_or_bytes
    else:
        data = Path(path_or_bytes).read_bytes()
    width, height = _parse_png_size(data)
    return data, width, height


def _ioctl_winsize(fileno: int) -> tuple[int, int, int, int] | None:
    if fcntl is None or termios is None:
        return None
    try:
        packed = fcntl.ioctl(fileno, termios.TIOCGWINSZ, struct.pack("HHHH", 0, 0, 0, 0))
        rows, cols, xpixel, ypixel = struct.unpack("HHHH", packed)
    except OSError:
        return None
    return rows, cols, xpixel, ypixel


def _tmux_cell_size() -> tuple[int, int] | None:
    if not os.environ.get("TMUX"):
        return None
    try:
        proc = subprocess.run(
            ["tmux", "display-message", "-p", "#{client_cell_width} #{client_cell_height}"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except Exception:
        return None
    parts = proc.stdout.strip().split()
    if len(parts) != 2:
        return None
    try:
        width, height = (int(parts[0]), int(parts[1]))
    except ValueError:
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height


def _geometry_from_fileno(
    fileno: int,
    *,
    cell_width_px: int | None,
    cell_height_px: int | None,
) -> TerminalGeometry | None:
    winsize = _ioctl_winsize(fileno)
    if winsize is None:
        return None
    rows, cols, xpixel, ypixel = winsize
    if cols <= 0 or rows <= 0:
        return None
    if cell_width_px is not None and cell_height_px is not None:
        return TerminalGeometry(cols=cols, rows=rows, cell_width_px=cell_width_px, cell_height_px=cell_height_px)
    if xpixel > 0 and ypixel > 0:
        return TerminalGeometry(
            cols=cols,
            rows=rows,
            cell_width_px=max(1, xpixel // cols),
            cell_height_px=max(1, ypixel // rows),
        )
    tmux_cell = _tmux_cell_size()
    if tmux_cell is not None:
        return TerminalGeometry(cols=cols, rows=rows, cell_width_px=tmux_cell[0], cell_height_px=tmux_cell[1])
    return None


def get_terminal_geometry(
    fileno: int,
    *,
    cell_width_px: int | None = None,
    cell_height_px: int | None = None,
) -> TerminalGeometry:
    geom = _geometry_from_fileno(fileno, cell_width_px=cell_width_px, cell_height_px=cell_height_px)
    if geom is not None:
        return geom
    try:
        with open("/dev/tty", "rb", buffering=0) as tty:
            geom = _geometry_from_fileno(tty.fileno(), cell_width_px=cell_width_px, cell_height_px=cell_height_px)
    except OSError:
        geom = None
    if geom is not None:
        return geom
    size = shutil.get_terminal_size(fallback=(80, 24))
    if cell_width_px is not None and cell_height_px is not None:
        return TerminalGeometry(
            cols=size.columns,
            rows=size.lines,
            cell_width_px=cell_width_px,
            cell_height_px=cell_height_px,
        )
    raise RuntimeError("unable to determine terminal cell size; pass --cell-size, --cols, or --rows")


def _fit_cells(
    image_width_px: int,
    image_height_px: int,
    geometry: TerminalGeometry,
    *,
    cols: int | None,
    rows: int | None,
    newline: bool,
) -> tuple[int, int]:
    if cols is not None and cols <= 0:
        raise ValueError("cols must be positive")
    if rows is not None and rows <= 0:
        raise ValueError("rows must be positive")

    cw = geometry.cell_width_px
    ch = geometry.cell_height_px

    if cols is not None and rows is not None:
        return cols, rows
    if cols is not None:
        rows = math.ceil((image_height_px * cols * cw) / (image_width_px * ch))
        return max(1, cols), max(1, rows)
    if rows is not None:
        cols = math.ceil((image_width_px * rows * ch) / (image_height_px * cw))
        return max(1, cols), max(1, rows)

    avail_cols = max(1, geometry.cols)
    avail_rows = max(1, geometry.rows - (1 if newline else 0))
    scale = min(
        (avail_cols * cw) / image_width_px,
        (avail_rows * ch) / image_height_px,
        1.0,
    )
    width_px = max(1, math.ceil(image_width_px * scale))
    height_px = max(1, math.ceil(image_height_px * scale))
    return max(1, math.ceil(width_px / cw)), max(1, math.ceil(height_px / ch))


def _resolve_passthrough(mode: str) -> str:
    if mode not in {"auto", "none", "tmux"}:
        raise ValueError("passthrough must be 'auto', 'none', or 'tmux'")
    if mode == "auto":
        return "tmux" if os.environ.get("TMUX") else "none"
    return mode


def _wrap_tmux_passthrough(seq: bytes) -> bytes:
    return b"\x1bPtmux;" + seq.replace(b"\x1b", b"\x1b\x1b") + b"\x1b\\"


def _graphics_apc(control: str, payload: bytes, *, passthrough: str) -> bytes:
    seq = b"\x1b_G" + control.encode("ascii") + b";" + payload + b"\x1b\\"
    return _wrap_tmux_passthrough(seq) if passthrough == "tmux" else seq


def _iter_transmit_chunks(
    png_data: bytes,
    *,
    cols: int,
    rows: int,
    image_id: int,
    chunk_size: int,
    passthrough: str,
) -> list[bytes]:
    encoded = base64.standard_b64encode(png_data)
    chunks = [encoded[i : i + chunk_size] for i in range(0, len(encoded), chunk_size)] or [b""]
    out: list[bytes] = []
    for i, chunk in enumerate(chunks):
        more = 1 if i < len(chunks) - 1 else 0
        meta = f"a=T,f=100,q=2,U=1,i={image_id},c={cols},r={rows}," if i == 0 else ""
        out.append(_graphics_apc(f"{meta}m={more}", chunk, passthrough=passthrough))
    return out


def _placeholder_grid(cols: int, rows: int, image_id: int) -> str:
    if rows > len(DIACRITICS):
        raise ValueError(f"too many rows for kitty Unicode placeholders: {rows} > {len(DIACRITICS)}")
    if cols <= 0 or rows <= 0:
        raise ValueError("cols and rows must be positive")
    r = (image_id >> 16) & 255
    g = (image_id >> 8) & 255
    b = image_id & 255
    prefix = f"\x1b[38;2;{r};{g};{b}m"
    line_fill = PLACEHOLDER * max(0, cols - 1)
    lines = [PLACEHOLDER + DIACRITICS[row] + line_fill for row in range(rows)]
    return prefix + "\n".join(lines) + "\x1b[39m"


def normalize_image_id(image_id: int | None) -> int:
    if image_id is None:
        return secrets.randbelow((1 << 24) - 1) + 1
    image_id &= 0xFFFFFFFF
    if image_id == 0:
        raise ValueError("image_id must be non-zero")
    if image_id >= (1 << 24):
        raise ValueError("image_id must fit in 24 bits for this minimal renderer")
    return image_id


def build_render_bytes(
    png: str | os.PathLike[str] | bytes,
    *,
    cols: int | None = None,
    rows: int | None = None,
    image_id: int | None = None,
    passthrough: str = "auto",
    cell_width_px: int | None = None,
    cell_height_px: int | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    newline: bool = True,
    out: BinaryIO | None = None,
) -> bytes:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    png_data, image_width_px, image_height_px = _read_png(png)
    image_id = normalize_image_id(image_id)
    passthrough = _resolve_passthrough(passthrough)

    if cols is None or rows is None:
        stream = out or sys.stdout.buffer
        geometry = get_terminal_geometry(
            stream.fileno(),
            cell_width_px=cell_width_px,
            cell_height_px=cell_height_px,
        )
        cols, rows = _fit_cells(
            image_width_px,
            image_height_px,
            geometry,
            cols=cols,
            rows=rows,
            newline=newline,
        )

    pieces = _iter_transmit_chunks(
        png_data,
        cols=cols,
        rows=rows,
        image_id=image_id,
        chunk_size=chunk_size,
        passthrough=passthrough,
    )
    pieces.append(_placeholder_grid(cols, rows, image_id).encode("utf-8"))
    if newline:
        pieces.append(b"\n")
    return b"".join(pieces)


def render_png(
    png: str | os.PathLike[str] | bytes,
    *,
    cols: int | None = None,
    rows: int | None = None,
    image_id: int | None = None,
    passthrough: str = "auto",
    cell_width_px: int | None = None,
    cell_height_px: int | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    newline: bool = True,
    out: BinaryIO | None = None,
) -> int:
    image_id = normalize_image_id(image_id)
    payload = build_render_bytes(
        png,
        cols=cols,
        rows=rows,
        image_id=image_id,
        passthrough=passthrough,
        cell_width_px=cell_width_px,
        cell_height_px=cell_height_px,
        chunk_size=chunk_size,
        newline=newline,
        out=out,
    )
    stream = out or sys.stdout.buffer
    stream.write(payload)
    stream.flush()
    return image_id


def _parse_cell_size(value: str) -> tuple[int, int]:
    value = value.lower()
    if "x" not in value:
        raise argparse.ArgumentTypeError("cell size must be WIDTHxHEIGHT")
    left, right = value.split("x", 1)
    try:
        width, height = int(left), int(right)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("cell size must be WIDTHxHEIGHT") from exc
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("cell size must use positive integers")
    return width, height


def render_image(
    path_or_bytes: str | os.PathLike[str] | bytes,
    *,
    cols: int | None = None,
    rows: int | None = None,
    image_id: int | None = None,
    passthrough: str = "auto",
    cell_width_px: int | None = None,
    cell_height_px: int | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    newline: bool = True,
    out: BinaryIO | None = None,
) -> int:
    """
    Renders an image in the terminal. Uses Pillow to convert formats if necessary.
    """
    from .formats import load_image
    png_data, _ = load_image(path_or_bytes)
    return render_png(
        png_data,
        cols=cols,
        rows=rows,
        image_id=image_id,
        passthrough=passthrough,
        cell_width_px=cell_width_px,
        cell_height_px=cell_height_px,
        chunk_size=chunk_size,
        newline=newline,
        out=out,
    )
