import io
import os
from contextlib import contextmanager

try:
    from PIL import Image, ImageSequence
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False


def _read_bytes(path_or_bytes: str | os.PathLike[str] | bytes) -> bytes:
    if isinstance(path_or_bytes, bytes):
        return path_or_bytes
    with open(path_or_bytes, "rb") as f:
        return f.read()


def load_image(path_or_bytes: str | os.PathLike[str] | bytes) -> tuple[bytes, bool]:
    """
    Loads an image file or bytes. 
    Returns (png_bytes, is_animated).
    Raises ImportError if Pillow is needed but not installed.
    """
    data = _read_bytes(path_or_bytes)
    
    # Fast path for PNG (starts with 89 50 4E 47 0D 0A 1A 0A)
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return data, False

    if not HAS_PILLOW:
        raise ImportError(
            "Pillow is required to open non-PNG formats. "
            "Install with: pip install kittytgp[all]"
        )

    # Use Pillow to convert to PNG
    with Image.open(io.BytesIO(data)) as img:
        is_animated = getattr(img, "is_animated", False)
        
        # If it's a single image, convert to PNG directly to be fed into the core
        if not is_animated:
            buf = io.BytesIO()
            # Convert to RGBA for consistent rendering
            if img.mode not in ("RGBA", "RGB"):
                img = img.convert("RGBA")
            img.save(buf, format="PNG")
            return buf.getvalue(), False
            
    # If animated, return the original data and let the animation module handle it
    return data, True


@contextmanager
def get_image_sequence(data: bytes):
    """
    Yields an ImageSequence for a GIF/animation data buffer.
    """
    if not HAS_PILLOW:
        raise ImportError(
            "Pillow is required to play animations. "
            "Install with: pip install kittytgp[all]"
        )

    buf = io.BytesIO(data)
    with Image.open(buf) as img:
        yield img, ImageSequence.Iterator(img)
