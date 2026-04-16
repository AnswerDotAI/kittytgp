import argparse
import sys

from .core import _parse_cell_size, DEFAULT_CHUNK_SIZE
from .formats import load_image

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render images and animations with kitty Unicode placeholders")
    parser.add_argument("image", help="Path to an image/animation file, or - to read from stdin")
    parser.add_argument("--cols", type=int, help="target width in terminal cells")
    parser.add_argument("--rows", type=int, help="target height in terminal cells")
    parser.add_argument("--cell-size", type=_parse_cell_size, help="manual terminal cell size in pixels, e.g. 10x20")
    parser.add_argument("--image-id", type=lambda s: int(s, 0), help="24-bit image id (decimal or 0x-prefixed hex)")
    parser.add_argument(
        "--passthrough",
        choices=("auto", "none", "tmux"),
        default="auto",
        help="wrap kitty APC commands for tmux passthrough",
    )
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE, help="base64 bytes per graphics chunk")
    parser.add_argument("--no-newline", action="store_true", help="do not print a trailing newline after the image")
    parser.add_argument("--fps", type=float, default=24.0, help="frames per second for animations")
    parser.add_argument("--loop", action=argparse.BooleanOptionalAction, default=True, help="loop animations")
    return parser

def _load_cli_input(arg: str) -> bytes | str:
    return sys.stdin.buffer.read() if arg == "-" else arg

def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    cell_width_px = cell_height_px = None
    if args.cell_size is not None:
        cell_width_px, cell_height_px = args.cell_size

    input_data = _load_cli_input(args.image)

    try:
        # load_image converts inputs to PNG bytes or detects animations
        png_data, is_animated = load_image(input_data)
        
        if is_animated:
            from .animation import play_animation
            play_animation(
                input_data,
                fps=args.fps,
                loop=args.loop,
                cols=args.cols,
                rows=args.rows,
                image_id=args.image_id,
                passthrough=args.passthrough,
                cell_width_px=cell_width_px,
                cell_height_px=cell_height_px,
                chunk_size=args.chunk_size,
                newline=not args.no_newline,
            )
        else:
            from .core import render_png
            render_png(
                png_data,
                cols=args.cols,
                rows=args.rows,
                image_id=args.image_id,
                passthrough=args.passthrough,
                cell_width_px=cell_width_px,
                cell_height_px=cell_height_px,
                chunk_size=args.chunk_size,
                newline=not args.no_newline,
            )
    except Exception as exc:
        parser.exit(1, f"kittytgp: {exc}\n")
    return 0
