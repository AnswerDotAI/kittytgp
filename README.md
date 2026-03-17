# kittytgp

`kittytgp` is a small pure-Python package that renders a PNG with kitty's graphics protocol using Unicode placeholders (`U+10EEEE`).

It follows kitty's tmux/editor-friendly placeholder flow:

1. transmit PNG data with kitty graphics protocol
2. create a **virtual** placement with `U=1`
3. print `U+10EEEE` placeholder text colored with the image ID

Because the visible part is ordinary Unicode text, the image moves with the text buffer and works inside hosts such as tmux.

## Install

```bash
pip install kittytgp
```

## CLI

```bash
kittytgp plot.png
```

Useful options:

```bash
kittytgp plot.png --cols 40
kittytgp plot.png --rows 20
kittytgp plot.png --cell-size 10x20
kittytgp plot.png --image-id 0x123456
kittytgp plot.png --no-newline
```

## Python API

```python
from kittytgp import render_png

render_png("plot.png")
```

Or build the bytes yourself:

```python
from kittytgp import build_render_bytes

payload = build_render_bytes("plot.png")
```

## Design notes

This package intentionally stays small:

- PNG input only
- direct transfer (`f=100` PNG payload in APC chunks)
- Unicode placeholders only
- 24-bit image IDs encoded in truecolor foreground color
- tmux passthrough only when needed

By default it fits the image into the current terminal while preserving aspect ratio. If the terminal cannot report cell pixel size, pass `--cell-size`, `--cols`, or `--rows`.

