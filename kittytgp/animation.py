import base64
import io
import sys
import time

from .core import build_render_bytes, get_terminal_geometry, _fit_cells, normalize_image_id, _graphics_apc, _resolve_passthrough
from .formats import get_image_sequence, _read_bytes

def _transmit_frame(png_data: bytes, image_id: int, chunk_size: int, passthrough: str, stream):
    """
    Transmits a replacement PNG to kitty under the same image_id.
    This updates the image in-place without needing new placeholders.
    """
    encoded = base64.standard_b64encode(png_data)
    chunks = [encoded[i : i + chunk_size] for i in range(0, len(encoded), chunk_size)] or [b""]
    for i, chunk in enumerate(chunks):
        more = 1 if i < len(chunks) - 1 else 0
        # a=T (transmit), f=100 (PNG), q=2 (quiet), i={id} (target image)
        meta = f"a=T,f=100,q=2,i={image_id}," if i == 0 else ""
        stream.write(_graphics_apc(f"{meta}m={more}", chunk, passthrough=passthrough))

def play_animation(
    path_or_bytes,
    fps: float = 24.0,
    loop: bool = True,
    cols: int | None = None,
    rows: int | None = None,
    image_id: int | None = None,
    passthrough: str = "auto",
    cell_width_px: int | None = None,
    cell_height_px: int | None = None,
    chunk_size: int = 4096,
    newline: bool = True,
    out = None,
):
    stream = out or sys.stdout.buffer
    data = _read_bytes(path_or_bytes)
    image_id = normalize_image_id(image_id)
    passthrough = _resolve_passthrough(passthrough)
    frame_delay = 1.0 / fps

    geometry = get_terminal_geometry(
        stream.fileno() if hasattr(stream, "fileno") else getattr(sys.stdout, "fileno", lambda: 0)(),
        cell_width_px=cell_width_px,
        cell_height_px=cell_height_px,
    )

    with get_image_sequence(data) as (img, frames):
        image_width_px, image_height_px = img.size
        
        fit_cols, fit_rows = _fit_cells(
            image_width_px,
            image_height_px,
            geometry,
            cols=cols,
            rows=rows,
            newline=newline,
        )

        first_frame = True
        try:
            while True:
                img.seek(0)
                for frame in frames:
                    buf = io.BytesIO()
                    # Convert to RGBA for consistency avoiding palletted issues
                    frame_rgba = frame.convert("RGBA")
                    frame_rgba.save(buf, format="PNG")
                    png_data = buf.getvalue()

                    start_time = time.time()

                    if first_frame:
                        # Render the first frame with full placeholder grid
                        render_payload = build_render_bytes(
                            png_data,
                            cols=fit_cols,
                            rows=fit_rows,
                            image_id=image_id,
                            passthrough=passthrough,
                            chunk_size=chunk_size,
                            newline=False,
                            cell_width_px=cell_width_px,
                            cell_height_px=cell_height_px,
                            out=stream
                        )
                        if render_payload:
                            stream.write(render_payload)
                        stream.flush()
                        first_frame = False
                    else:
                        # For subsequent frames, tell kitty to replace the image data
                        _transmit_frame(png_data, image_id, chunk_size, passthrough, stream)
                        stream.flush()

                    elapsed = time.time() - start_time
                    time.sleep(max(0, frame_delay - elapsed))

                if not loop:
                    break
                    
        except KeyboardInterrupt:
            # Allow users to Ctrl+C to stop the animation gracefully
            pass
        finally:
            if newline:
                stream.write(b"\n")
            stream.flush()
